"""LUCA V0.3 first-real-session IEX minute coverage audit (read only).

Summarizes availability of one-minute IEX bars. Missing IEX bars are NOT proof
of API failure: a minute may have no IEX trades. Not SIP or market-wide coverage.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from evidence_quality_gate import summarize
from followup_bridge import validate_github_run

HORIZONS=(5,15,30,60)

def audit(meta, frozen, review, reference):
    if type(meta) is not dict or type(meta.get("databaseId")) is not int:
        raise ValueError("BAD_SOURCE_METADATA")
    validate_github_run(meta,meta["databaseId"])
    quality=summarize(frozen,review,None,reference)
    if quality["validation_status"]!="NOT_VALIDATED" or quality["real_trades_allowed"] is not False:
        raise ValueError("UNSAFE_QUALITY")
    if reference is None or reference.get("schema")!="LUCA_V03_FROZEN_FIXED_CLOCK_REFERENCE_V1":
        raise ValueError("MISSING_FIXED_CLOCK_REFERENCE")
    frozen_names=frozen["candidates"]
    reviewed=review["results"]
    refs=reference["rows"]
    if not frozen_names or len(frozen_names)!=len(reviewed) or len(frozen_names)!=len(refs):
        raise ValueError("UNIVERSE_COUNT_MISMATCH")
    if [r.get("symbol") for r in reviewed]!=frozen_names or [r.get("symbol") for r in refs]!=frozen_names:
        raise ValueError("UNIVERSE_ORDER_MISMATCH")
    if any(x.get("grade")!="D" or x.get("buy_allowed") is not False for x in reviewed):
        raise ValueError("UNSAFE_GRADE")
    rows=[]
    for observed,ref in zip(reviewed,refs):
        n=observed["observed_iex_bars"]
        if type(n) is not int or not 0<=n<=14:
            raise ValueError("INVALID_FIRST_WINDOW_COUNT")
        if len(ref.get("horizons",[]))!=4:
            raise ValueError("INVALID_REFERENCE_HORIZONS")
        item={"symbol":observed["symbol"],"initial_iex_minutes":n,
              "initial_expected_minutes":14,"initial_complete":n==14,
              "reference":[]}
        for h,expected in zip(ref["horizons"],HORIZONS):
            if h.get("horizon_minutes")!=expected or h.get("expected_bars")!=expected:
                raise ValueError("HORIZON_MISMATCH")
            count=h.get("observed_bars")
            if type(count) is not int or not 0<=count<=expected:
                raise ValueError("INVALID_REFERENCE_BAR_COUNT")
            complete=h.get("status")=="COMPLETE_IEX_PRICES_ONLY"
            if complete!=(count==expected):
                raise ValueError("INCONSISTENT_COMPLETENESS")
            item["reference"].append({"minutes":expected,"iex_bars":count,
                                       "expected":expected,"complete":complete})
        rows.append(item)
    total_initial=sum(r["initial_iex_minutes"] for r in rows)
    if total_initial!=review["observed_iex_bars"]:
        raise ValueError("INITIAL_BAR_SUM_MISMATCH")
    if sum(r["initial_complete"] for r in rows)!=quality["first_window_complete_symbols"]:
        raise ValueError("INITIAL_QUALITY_MISMATCH")
    horizon_summary=[]
    for idx,minutes in enumerate(HORIZONS):
        observed=sum(r["reference"][idx]["iex_bars"] for r in rows)
        complete=sum(r["reference"][idx]["complete"] for r in rows)
        horizon_summary.append({"minutes":minutes,"observed_iex_bars":observed,
                                "expected_symbol_minutes":len(rows)*minutes,
                                "iex_minute_presence_pct":round(100*observed/(len(rows)*minutes),2),
                                "fully_observed_symbols":complete})
    return {
        "schema":"LUCA_V03_IEX_COVERAGE_AUDIT_V1",
        "source_run_id":meta["databaseId"],"frozen_t0_sha256":quality["frozen_t0_sha256"],
        "frozen_symbols":len(rows),
        "initial":{"observed_iex_bars":total_initial,"expected_symbol_minutes":len(rows)*14,
                   "iex_minute_presence_pct":round(100*total_initial/(len(rows)*14),2),
                   "fully_observed_symbols":quality["first_window_complete_symbols"],
                   "sparse_symbols":quality["first_window_sparse_symbols"]},
        "fixed_clock_reference":horizon_summary,
        "rows":rows,
        "not_full_us_market_coverage":True,
        "missing_bar_cause_unknown":True,
        "missing_bar_is_not_proven_api_failure":True,
        "missing_bar_is_not_zero_return":True,
        "raw_bar_timestamps_not_in_source_artifact":True,
        "cannot_diagnose_gap_timing_or_iex_trade_absence":True,
        "no_signal_outcomes_because_no_pattern":quality["pattern_observed_symbols"]==0,
        "no_trading_signal":True,
        "prediction_accuracy_verified":False,
        "sec_status":"SEC_UNVERIFIED","validation_status":"NOT_VALIDATED",
        "real_trades_allowed":False,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--source-dir",required=True)
    p.add_argument("--metadata",required=True)
    p.add_argument("--reference",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    def load(path):
        p=Path(path)
        if p.stat().st_size>2_000_000:
            raise ValueError("FILE_TOO_LARGE")
        return json.loads(p.read_text(encoding="utf8"))
    root=Path(a.source_dir)
    result=audit(load(a.metadata),load(root/"frozen_t0.json"),
                 load(root/"forward_review.json"),load(a.reference))
    target=Path(a.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("x",encoding="utf8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print("IEX_COVERAGE_AUDIT; INITIAL="+str(result["initial"]["observed_iex_bars"])+
          "/"+str(result["initial"]["expected_symbol_minutes"])+
          "; SPARSE="+str(result["initial"]["sparse_symbols"])+
          "; CAUSE_UNKNOWN; NOT_VALIDATED; NO_ORDERS")

if __name__=="__main__":
    main()
