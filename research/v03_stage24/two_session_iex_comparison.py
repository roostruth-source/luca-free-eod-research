"""Strict first-versus-second IEX data coverage comparison, NOT a hit-rate.

First source is the verified counts-only 14-minute gap audit. Second source
requires original T0, original review and observed timestamp provenance.
No HTTP, orders, market predictions, alerts, or invented gap causes.
"""
from __future__ import annotations

import datetime as dt
from forward_outcomes_iex import validate_origins,parse_utc

FIRST_ID=40517830351
EXPECTED_FIRST={"observed_iex_bars":94,"expected_symbol_minutes":168,
                "fully_observed_symbols":1,"sparse_symbols":11}
EXPECTED_FIRST_SYMBOLS=12
EXPECTED_FIRST_PATTERNS=0


def compare(first,frozen,review,provenance,second_run_id):
    if type(second_run_id) is not int or second_run_id<=0 or second_run_id==FIRST_ID:
        raise ValueError("INVALID_SECOND_RUN_ID")
    if first.get("schema")!="LUCA_V03_IEX_COVERAGE_AUDIT_V1" or first.get("source_run_id")!=FIRST_ID:
        raise ValueError("UNVERIFIED_FIRST_AUDIT")
    if first.get("initial")!=dict(EXPECTED_FIRST,iex_minute_presence_pct=55.95):
        raise ValueError("FIRST_REAL_BASELINE_MISMATCH")
    if first.get("frozen_symbols")!=EXPECTED_FIRST_SYMBOLS or first.get("no_signal_outcomes_because_no_pattern") is not True:
        raise ValueError("FIRST_REAL_BASELINE_MISMATCH")
    if first.get("validation_status")!="NOT_VALIDATED" or first.get("real_trades_allowed") is not False:
        raise ValueError("UNSAFE_FIRST_EVIDENCE")
    t0,reviewed,_=validate_origins(frozen,review)
    if provenance.get("schema")!="LUCA_V03_IEX_TIMESTAMP_PROVENANCE_V1":
        raise ValueError("MISSING_SECOND_TIMESTAMP_EVIDENCE")
    if provenance.get("frozen_t0_sha256")!=frozen["sha256"]:
        raise ValueError("SECOND_T0_HASH_MISMATCH")
    if provenance.get("validation_status")!="NOT_VALIDATED" or provenance.get("real_trades_allowed") is not False:
        raise ValueError("UNSAFE_SECOND_EVIDENCE")
    if provenance.get("feed")!="IEX_SINGLE_EXCHANGE_NOT_SIP" or provenance.get("missing_iex_bar_cause_unknown") is not True:
        raise ValueError("MISLEADING_IEX_COVERAGE")
    if parse_utc(provenance["frozen_at_utc"])!=t0 or parse_utc(provenance["reviewed_at_utc"])!=reviewed:
        raise ValueError("SECOND_PROVENANCE_TIME_MISMATCH")
    if t0.date()==dt.date(2026,10,27):
        raise ValueError("SAME_FIRST_SESSION_DATE")
    if provenance.get("api_fetch",{}).get("captured") is not True:
        raise ValueError("SECOND_HTTP_EVIDENCE_MISSING")
    api=provenance["api_fetch"]
    if api.get("get_only_confirmed") is not True or api.get("all_pages_successful") is not True or api.get("final_page_token_absent") is not True or type(api.get("page_count")) is not int or not 1<=api["page_count"]<=6:
        raise ValueError("SECOND_HTTP_INCOMPLETE")
    rows=provenance.get("rows")
    names=frozen["candidates"]
    if type(rows) is not list or len(rows)!=len(names) or not names or len(names)>12:
        raise ValueError("SECOND_UNIVERSE_MISMATCH")
    if [x.get("symbol") for x in rows]!=names or [x.get("symbol") for x in review["results"]]!=names:
        raise ValueError("SECOND_UNIVERSE_ORDER_MISMATCH")
    start=parse_utc(review["first_allowed_bar_start_utc"])
    end=parse_utc(review["last_allowed_bar_start_utc"])
    n=int((end-start).total_seconds()/60)+1
    if provenance.get("expected_minutes_per_symbol")!=n or not 1<=n<=35:
        raise ValueError("SECOND_WINDOW_MISMATCH")
    grid={start+dt.timedelta(minutes=i) for i in range(n)}
    total=complete=0
    for row,review_row in zip(rows,review["results"]):
        observed=row.get("observed_bar_start_utc")
        missing=row.get("missing_iex_bar_start_utc")
        if type(observed) is not list or type(missing) is not list:
            raise ValueError("BAD_TIMESTAMP_LIST")
        a=[parse_utc(s) for s in observed]
        b=[parse_utc(s) for s in missing]
        if (len(a)!=len(set(a)) or len(b)!=len(set(b)) or
            set(a)&set(b) or set(a)|set(b)!=grid):
            raise ValueError("INCONSISTENT_TIMESTAMP_GRID")
        if (row.get("expected_minutes")!=n or row.get("observed_minutes")!=len(a)
            or review_row.get("observed_iex_bars")!=len(a)
            or row.get("complete") is not (len(b)==0)):
            raise ValueError("SECOND_REVIEW_COUNT_MISMATCH")
        if row.get("missing_cause")!="UNKNOWN_NO_IEX_BAR_OR_DATA_ISSUE":
            raise ValueError("UNJUSTIFIED_GAP_CAUSE")
        total+=len(a)
        complete+=len(b)==0
    if total!=review["observed_iex_bars"]:
        raise ValueError("SECOND_TOTAL_MISMATCH")
    first_rate=100*94/168
    second_rate=100*total/(len(names)*n)
    return {
        "schema":"LUCA_V03_TWO_SESSION_IEX_COVERAGE_COMPARISON_V1",
        "first_source_run_id":FIRST_ID,"second_source_run_id":second_run_id,
        "first":{"symbols":12,"expected_minutes_per_symbol":14,"observed":94,
                 "expected":168,"complete_symbols":1,"pattern_symbols":0,
                 "presence_pct":round(first_rate,2)},
        "second":{"symbols":len(names),"expected_minutes_per_symbol":n,
                  "observed":total,"expected":len(names)*n,
                  "complete_symbols":complete,
                  "pattern_symbols":review["forward_pattern_symbols"],
                  "presence_pct":round(second_rate,2),
                  "http_get_recorded":True},
        "presence_change_percentage_points":round(second_rate-first_rate,2),
        "not_same_symbols_or_identical_time_windows":True,
        "not_evidence_of_improved_api_or_prediction_accuracy":True,
        "missing_iex_minute_cause_unknown":True,
        "not_full_us_market_coverage":True,
        "two_sessions_insufficient_for_predictive_validation":True,
        "sec_status":"SEC_UNVERIFIED",
        "validation_status":"NOT_VALIDATED",
        "real_trades_allowed":False,
    }
