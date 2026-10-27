"""LUCA V0.3: fail-closed research evidence scorecard, not a trading model.

Merge only SAME-T0 frozen universe, prospective IEX 16min review, and optional
60min signal outcomes / fixed-clock all-candidate benchmark. No order endpoints.
No SEC clearance, cap/float verification, predictive hit-rate or causal claim.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
from pathlib import Path

from forward_outcomes_iex import validate_origins, parse_utc, HORIZONS
from prospective_iex_research import next_bar_start

UTC=dt.timezone.utc
VALID_STATUSES={"COMPLETE_IEX_PRICES_ONLY","MISSING_IEX_MINUTES"}


def check_horizons(horizons):
    """Validate presentation integrity only; original market bars remain the evidence."""
    if type(horizons) is not list or len(horizons)!=len(HORIZONS):
        raise ValueError("INVALID_HORIZON_TABLE")
    totals=0
    for n,x in zip(HORIZONS,horizons):
        if type(x) is not dict or x.get("horizon_minutes")!=n or x.get("status") not in VALID_STATUSES:
            raise ValueError("INVALID_HORIZON_ROW")
        observed=x.get("observed_bars")
        expected=x.get("expected_bars")
        if type(observed) is not int or type(expected) is not int or expected!=n or not 0<=observed<=n:
            raise ValueError("INVALID_HORIZON_COVERAGE")
        value=x.get("theoretical_iex_open_to_close_pct")
        if x["status"]=="COMPLETE_IEX_PRICES_ONLY":
            if observed!=n or type(value) not in (int,float) or not math.isfinite(value):
                raise ValueError("BAD_COMPLETE_HORIZON")
            if x.get("real_fill_verified") is not False or x.get("slippage_and_spread_included") is not False:
                raise ValueError("UNSAFE_FILL_CLAIM")
            totals+=1
        elif value is not None or observed==n:
            raise ValueError("MISSING_HORIZON_HAS_RESULT")
    return totals


def summarize(frozen, review, outcomes=None, reference=None):
    t0,reviewed,entries=validate_origins(frozen,review)
    universe=frozen["candidates"]
    start=parse_utc(review["first_allowed_bar_start_utc"])
    last=parse_utc(review["last_allowed_bar_start_utc"])
    expected=int((last-start).total_seconds()/60)+1
    if expected<1 or expected>35:
        raise ValueError("INVALID_REVIEW_WINDOW_LENGTH")

    candidates=[]
    for item in review["results"]:
        obs=item.get("observed_iex_bars")
        patterns=item.get("pattern_count")
        if type(obs) is not int or not 0<=obs<=expected:
            raise ValueError("INVALID_OBSERVED_BAR_COUNT")
        if type(patterns) is not int or patterns<0 or patterns>obs:
            raise ValueError("INVALID_PATTERN_COUNT")
        status=("PATTERN_RECORDED" if patterns>0 else
                "NO_IEX_BARS" if obs==0 else
                "NO_PATTERN_WITH_GAPS" if obs<expected else "NO_PATTERN_OBSERVED")
        candidates.append({
            "symbol":item["symbol"],
            "first_window_minutes_expected":expected,
            "first_window_bars_observed":obs,
            "initial_pattern_status":status,
            "pattern_count":patterns,
            "signal_horizons_complete":None,
            "reference_horizons_complete":None,
            "sec_status":"SEC_UNVERIFIED",
            "grade":"D","buy_allowed":False,
        })
    bysym={x["symbol"]:x for x in candidates}
    observed_signals=set(entries)
    if observed_signals!={x["symbol"] for x in candidates if x["pattern_count"]>0}:
        raise ValueError("PATTERN_UNIVERSE_DRIFT")

    outcome_status="AWAITING_OR_UNAVAILABLE"
    if outcomes is not None:
        if type(outcomes) is not dict or outcomes.get("schema")!="LUCA_V03_PROSPECTIVE_IEX_OUTCOMES_V1":
            raise ValueError("INVALID_OUTCOMES_REPORT")
        if outcomes.get("frozen_t0_sha256")!=frozen["sha256"] or outcomes.get("frozen_at_utc")!=t0.isoformat():
            raise ValueError("OUTCOMES_FROM_ANOTHER_T0")
        if outcomes.get("validation_status")!="NOT_VALIDATED" or outcomes.get("real_trades_allowed") is not False:
            raise ValueError("UNSAFE_OUTCOMES")
        if outcomes.get("not_real_fills") is not True or outcomes.get("fees_slippage_or_spread_included") is not False:
            raise ValueError("UNSAFE_PROFIT_CLAIMS")
        if outcomes.get("same_exchange_limit")!="IEX_ONLY_NOT_CONSOLIDATED_SIP":
            raise ValueError("MIXED_MARKET_FEED")
        if outcomes.get("initial_reviewed_at_utc")!=review.get("reviewed_at_utc"):
            raise ValueError("WRONG_FIRST_REVIEW")
        if outcomes.get("horizon_minutes")!=list(HORIZONS):
            raise ValueError("INVALID_HORIZON_SET")
        rows=outcomes.get("signals")
        if type(rows) is not list or len(rows)!=len(entries) or len(rows)!=outcomes.get("evaluated_signals"):
            raise ValueError("OUTCOME_SIGNAL_COUNT_DRIFT")
        if set(x.get("symbol") for x in rows if isinstance(x,dict))!=observed_signals:
            raise ValueError("OUTCOME_SIGNAL_UNIVERSE_DRIFT")
        checked=parse_utc(outcomes.get("outcomes_checked_at_utc"))
        if checked<max(entries.values())+dt.timedelta(minutes=62):
            raise ValueError("OUTCOMES_NOT_MATURE")
        complete=0
        for row in rows:
            symbol=row["symbol"]
            if row.get("grade")!="D" or row.get("buy_allowed") is not False or row.get("sec_status")!="SEC_UNVERIFIED":
                raise ValueError("UNSAFE_OUTCOME_ROW")
            if parse_utc(row.get("known_at_utc"))!=entries[symbol]:
                raise ValueError("OUTCOME_SIGNAL_TIMESTAMP_DRIFT")
            number=check_horizons(row.get("horizons"))
            bysym[symbol]["signal_horizons_complete"]=number
            complete+=number
        if complete!=outcomes.get("complete_horizons"):
            raise ValueError("OUTCOME_COMPLETENESS_DRIFT")
        outcome_status="OBSERVED_PARTIAL_IEX" if complete<len(entries)*len(HORIZONS) else "OBSERVED_COMPLETE_IEX_ONLY"

    reference_status="AWAITING_OR_UNAVAILABLE"
    if reference is not None:
        if type(reference) is not dict or reference.get("schema")!="LUCA_V03_FROZEN_FIXED_CLOCK_REFERENCE_V1":
            raise ValueError("INVALID_REFERENCE_REPORT")
        if reference.get("freeze_sha256")!=frozen["sha256"] or reference.get("selected_at_utc")!=t0.isoformat():
            raise ValueError("REFERENCE_FROM_ANOTHER_T0")
        if reference.get("validation_status")!="NOT_VALIDATED" or reference.get("real_trades_allowed") is not False:
            raise ValueError("UNSAFE_REFERENCE")
        if reference.get("feed")!="ALPACA_IEX_SINGLE_EXCHANGE" or reference.get("not_randomized_control") is not True:
            raise ValueError("FAKE_REFERENCE_CONTROL")
        expected_clock=next_bar_start(t0)+dt.timedelta(minutes=6)
        if parse_utc(reference.get("reference_utc"))!=expected_clock:
            raise ValueError("REFERENCE_CLOCK_CHANGED_AFTER_T0")
        if reference.get("original_reviewed_at_utc")!=reviewed.isoformat():
            raise ValueError("REFERENCE_FROM_ANOTHER_REVIEW")
        rr=reference.get("rows")
        if type(rr) is not list or [x.get("symbol") for x in rr if isinstance(x,dict)]!=universe or len(rr)!=len(universe):
            raise ValueError("REFERENCE_UNIVERSE_DRIFT")
        checked=parse_utc(reference.get("checked_at_utc"))
        if checked<expected_clock+dt.timedelta(minutes=62):
            raise ValueError("REFERENCE_NOT_MATURE")
        complete=0
        for row in rr:
            symbol=row["symbol"]
            if row.get("grade")!="D" or row.get("buy_allowed") is not False or row.get("sec_status")!="SEC_UNVERIFIED":
                raise ValueError("UNSAFE_REFERENCE_ROW")
            if parse_utc(row.get("control_entry_utc"))!=expected_clock:
                raise ValueError("REFERENCE_CLOCK_DRIFT")
            if row.get("initial_16min_pattern_observed")!=(bysym[symbol]["pattern_count"]>0) or row.get("absence_of_pattern_proven") is not False:
                raise ValueError("REFERENCE_SIGNAL_LABEL_DRIFT")
            n=check_horizons(row.get("horizons"))
            bysym[symbol]["reference_horizons_complete"]=n
            complete+=n
        if complete!=reference.get("observed_iex_prices_complete"):
            raise ValueError("REFERENCE_COMPLETENESS_DRIFT")
        if reference.get("frozen_symbols")!=len(universe):
            raise ValueError("REFERENCE_SYMBOL_COUNT_DRIFT")
        reference_status="OBSERVED_PARTIAL_IEX" if complete<len(universe)*len(HORIZONS) else "OBSERVED_COMPLETE_IEX_ONLY"

    all_observed=sum(x["first_window_bars_observed"] for x in candidates)
    patterns=sum(x["pattern_count"]>0 for x in candidates)
    sparse=sum(x["first_window_bars_observed"]<expected for x in candidates)
    return {
        "schema":"LUCA_V03_RESEARCH_EVIDENCE_QUALITY_V1",
        "frozen_t0_sha256":frozen["sha256"],
        "frozen_at_utc":t0.isoformat(),
        "quality":"INSUFFICIENT_FOR_PREDICTION",
        "candidates_frozen":len(universe),
        "forward_iex_bars_observed":all_observed,
        "first_window_complete_symbols":len(universe)-sparse,
        "first_window_sparse_symbols":sparse,
        "pattern_observed_symbols":patterns,
        "no_pattern_observed_symbols":len(universe)-patterns,
        "signal_outcome_evidence":outcome_status,
        "fixed_clock_reference_evidence":reference_status,
        "separate_reference_is_not_randomized_control":True,
        "no_pattern_is_not_proof_of_no_signal":True,
        "all_grades":{"A":0,"B":0,"C":0,"D":len(universe)},
        "rows":candidates,
        "prediction_accuracy_verified":False,
        "market_cap_verified":False,"float_verified":False,
        "sec_status":"SEC_UNVERIFIED",
        "validation_status":"NOT_VALIDATED","real_trades_allowed":False,
        "note":"Missing IEX minutes and unverified SEC/float/liquidity block any trading approval; statistics describe this one T0 only.",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source",default="luca_v03_forward")
    p.add_argument("--outcomes",default="luca_v03_followup/outcomes.json")
    p.add_argument("--reference",default="luca_v03_reference/fixed_clock_reference.json")
    p.add_argument("--dest",default="luca_v03_quality/quality.json")
    args=p.parse_args()
    root=Path(args.source)
    frozen=json.loads((root/"frozen_t0.json").read_text(encoding="utf8"))
    review=json.loads((root/"forward_review.json").read_text(encoding="utf8"))
    def optional_json(path):
        p=Path(path)
        return json.loads(p.read_text(encoding="utf8")) if p.is_file() else None
    report=summarize(frozen,review,optional_json(args.outcomes),optional_json(args.reference))
    file=Path(args.dest)
    file.parent.mkdir(parents=True,exist_ok=True)
    with file.open("x",encoding="utf8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print("EVIDENCE_QUALITY: FROZEN="+str(report["candidates_frozen"])+
          "; PATTERNS="+str(report["pattern_observed_symbols"])+
          "; SPARSE="+str(report["first_window_sparse_symbols"])+
          "; SIGNAL_OUTCOMES="+report["signal_outcome_evidence"]+
          "; REFERENCE="+report["fixed_clock_reference_evidence"]+
          "; NOT_VALIDATED; NO_ORDERS")


if __name__=="__main__":
    main()
