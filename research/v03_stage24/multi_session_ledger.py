"""LUCA V0.3: multi-session, forward-only evidence ledger.

Input: one directory per successful source GitHub prospective run, assembled from
original source artifacts plus its followup results. Does NOT fetch market data,
write GitHub, schedule jobs, send alerts, or calculate an unvalidated win rate.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import pathlib
import re
from zoneinfo import ZoneInfo

from evidence_quality_gate import summarize
from followup_bridge import validate_github_run

NY=ZoneInfo("America/New_York")
RUN_PATTERN=re.compile(r"[1-9][0-9]{7,14}\Z")
HORIZONS=(5,15,30,60)


def load_json(path, required=True):
    path=pathlib.Path(path)
    if not path.is_file():
        if required:
            raise ValueError("MISSING_REQUIRED_EVIDENCE:"+path.name)
        return None
    if path.stat().st_size>2_000_000:
        raise ValueError("EVIDENCE_FILE_TOO_LARGE")
    return json.loads(path.read_text(encoding="utf8"))


def one_session(directory):
    root=pathlib.Path(directory)
    if not root.is_dir() or not RUN_PATTERN.fullmatch(root.name):
        raise ValueError("RUN_DIRECTORY_MUST_BE_SOURCE_ID")
    run_id=int(root.name)
    source=validate_github_run(load_json(root/"followup_source_metadata.json"),run_id)
    frozen=load_json(root/"frozen_t0.json")
    review=load_json(root/"forward_review.json")
    outcomes=load_json(root/"outcomes.json",required=False)
    reference=load_json(root/"fixed_clock_reference.json",required=False)
    # Recalculate from raw evidence: never trust a copied quality summary.
    quality=summarize(frozen,review,outcomes,reference)
    if quality["quality"]!="INSUFFICIENT_FOR_PREDICTION" or quality["real_trades_allowed"] is not False:
        raise ValueError("UNSAFE_RESEARCH_LEDGER")
    t0=dt.datetime.fromisoformat(quality["frozen_at_utc"])
    if t0.tzinfo is None:
        raise ValueError("NAIVE_T0")
    local=t0.astimezone(NY)
    if local.weekday()>4:
        raise ValueError("NON_WEEKDAY_T0")
    # This is a day bucket only; holidays require an independent market calendar.
    if not (9<=local.hour<=12):
        raise ValueError("UNEXPECTED_T0_NY_HOUR")
    return {
        "source_run_id":source["approved_source_run_id"],
        "source_branch":source["branch"],
        "session_date_ny":local.date().isoformat(),
        "frozen_at_utc":quality["frozen_at_utc"],
        "freeze_sha256":quality["frozen_t0_sha256"],
        "candidates":quality["candidates_frozen"],
        "initial_pattern_symbols":quality["pattern_observed_symbols"],
        "initial_no_pattern_symbols":quality["no_pattern_observed_symbols"],
        "first_window_complete_symbols":quality["first_window_complete_symbols"],
        "first_window_sparse_symbols":quality["first_window_sparse_symbols"],
        "no_iex_bars_symbols":sum(x["initial_pattern_status"]=="NO_IEX_BARS" for x in quality["rows"]),
        "signal_outcomes_status":quality["signal_outcome_evidence"],
        "reference_status":quality["fixed_clock_reference_evidence"],
        "signal_horizons_complete":{str(h):0 for h in HORIZONS},
        "reference_horizons_complete":{str(h):0 for h in HORIZONS},
        "signal_horizons_missing":{str(h):0 for h in HORIZONS},
        "reference_horizons_missing":{str(h):0 for h in HORIZONS},
        "outcome_records_present":outcomes is not None,
        "reference_records_present":reference is not None,
        "grade":"D",
        "validation_status":"NOT_VALIDATED",
        "real_trades_allowed":False,
        "_raw_outcomes":outcomes,
        "_raw_reference":reference,
    }


def build_ledger(sessions):
    if type(sessions) is not list:
        raise ValueError("BAD_SESSIONS")
    ids=set()
    hashes=set()
    dates=set()
    clean=[]
    for row in sessions:
        if not isinstance(row,dict) or row.get("validation_status")!="NOT_VALIDATED" or row.get("real_trades_allowed") is not False or row.get("grade")!="D":
            raise ValueError("UNSAFE_OR_INVALID_SESSION")
        rid=row.get("source_run_id")
        if type(rid) is not int or rid<=0 or rid in ids:
            raise ValueError("DUPLICATE_OR_INVALID_RUN_ID")
        sha=row.get("freeze_sha256")
        if type(sha) is not str or not re.fullmatch(r"[a-f0-9]{64}",sha) or sha in hashes:
            raise ValueError("DUPLICATE_OR_INVALID_T0_FREEZE")
        day=row.get("session_date_ny")
        if type(day) is not str or day in dates:
            raise ValueError("DUPLICATE_NY_SESSION_DATE")
        ids.add(rid)
        hashes.add(sha)
        dates.add(day)
        r=dict(row)
        outcome=r.pop("_raw_outcomes",None)
        reference=r.pop("_raw_reference",None)
        for group,raw in (("signal",outcome),("reference",reference)):
            records=(raw.get("signals",[]) if group=="signal" else raw.get("rows",[])) if raw is not None else []
            if type(records) is not list:
                raise ValueError("INVALID_RAW_RECORDS")
            for item in records:
                for horizon in item["horizons"]:
                    n=str(horizon["horizon_minutes"])
                    k=group+"_horizons_"+("complete" if horizon["status"]=="COMPLETE_IEX_PRICES_ONLY" else "missing")
                    if n not in r[k]:
                        raise ValueError("INVALID_HORIZON")
                    r[k][n]+=1
        clean.append(r)
    clean.sort(key=lambda r:(r["session_date_ny"],r["source_run_id"]))
    counts={
        "sessions":len(clean),
        "frozen_candidates":sum(x["candidates"] for x in clean),
        "initial_pattern_symbols":sum(x["initial_pattern_symbols"] for x in clean),
        "initial_no_pattern_symbols":sum(x["initial_no_pattern_symbols"] for x in clean),
        "first_window_complete_symbols":sum(x["first_window_complete_symbols"] for x in clean),
        "first_window_sparse_symbols":sum(x["first_window_sparse_symbols"] for x in clean),
        "no_iex_bars_symbols":sum(x["no_iex_bars_symbols"] for x in clean),
        "sessions_with_signal_outcomes":sum(x["outcome_records_present"] for x in clean),
        "sessions_with_reference":sum(x["reference_records_present"] for x in clean),
        "signal_horizons_complete":{str(h):sum(x["signal_horizons_complete"][str(h)] for x in clean) for h in HORIZONS},
        "signal_horizons_missing":{str(h):sum(x["signal_horizons_missing"][str(h)] for x in clean) for h in HORIZONS},
        "reference_horizons_complete":{str(h):sum(x["reference_horizons_complete"][str(h)] for x in clean) for h in HORIZONS},
        "reference_horizons_missing":{str(h):sum(x["reference_horizons_missing"][str(h)] for x in clean) for h in HORIZONS},
    }
    return {
        "schema":"LUCA_V03_PROSPECTIVE_MULTI_SESSION_LEDGER_V1",
        "source":"SUCCESSFUL_SOURCE_RUNS_WITH_T0_HASH_REVALIDATION",
        "research_sessions":clean,
        "totals":counts,
        "includes_failed_github_runs":False,
        "failed_run_counts_not_available":True,
        "not_a_complete_universe_or_randomized_control":True,
        "no_market_holidays_verified":True,
        "no_profit_or_win_rate_claim":True,
        "predictive_accuracy_verified":False,
        "market_cap_verified":False,
        "float_verified":False,
        "sec_status":"SEC_UNVERIFIED",
        "validation_status":"NOT_VALIDATED",
        "real_trades_allowed":False,
        "note":"Counts only successful GitHub source runs supplied as artifacts. Failed GitHub runs require a separate failure register; do not interpret as success rate. Missing IEX minutes are not zero returns.",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input-root",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    root=pathlib.Path(args.input_root)
    if not root.is_dir():
        raise ValueError("NO_SOURCE_ARTIFACT_DIRECTORY")
    children=sorted(p for p in root.iterdir() if p.is_dir())
    if not children:
        raise ValueError("NO_REAL_RUN_ARTIFACTS")
    ledger=build_ledger([one_session(p) for p in children])
    output=pathlib.Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x",encoding="utf8") as f:
        json.dump(ledger,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print("PROSPECTIVE_LEDGER; SESSIONS="+str(ledger["totals"]["sessions"])+
          "; SIGNALS="+str(ledger["totals"]["initial_pattern_symbols"])+
          "; SPARSE="+str(ledger["totals"]["first_window_sparse_symbols"])+
          "; NOT_VALIDATED; NO_ORDERS")


if __name__=="__main__":
    main()
