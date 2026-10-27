"""Optional FUTURE-session IEX bar timestamp provenance, no API access.

Run at review time with original in-memory bars BEFORE discarding them.
Does not infer why a minute lacks an IEX trade bar, nor alter signal logic.
Never reconstruct timestamps from the old counts-only session.
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
from forward_outcomes_iex import validate_origins,parse_utc
from iex_1min_research import valid_bar

MAX_NAMES=12
MAX_MINUTES=35
UTC=dt.timezone.utc


def build_minute_provenance(frozen,review,bars,recorded_at,api_evidence=None):
    t0,reviewed,_=validate_origins(frozen,review)
    at=recorded_at
    if not isinstance(at,dt.datetime) or at.tzinfo is None:
        raise ValueError("AWARE_RECORDING_TIME_REQUIRED")
    at=at.astimezone(UTC)
    if at<reviewed or at>reviewed+dt.timedelta(minutes=5):
        raise ValueError("INVALID_RECORDING_TIME")
    names=frozen["candidates"]
    if len(names)>MAX_NAMES or type(bars) is not dict or set(bars)!=set(names):
        raise ValueError("BAR_UNIVERSE_DRIFT")
    start=parse_utc(review["first_allowed_bar_start_utc"])
    end=parse_utc(review["last_allowed_bar_start_utc"])
    minutes=int((end-start).total_seconds()//60)+1
    if not 1<=minutes<=MAX_MINUTES or start+dt.timedelta(minutes=minutes-1)!=end:
        raise ValueError("INVALID_WINDOW")
    if type(api_evidence) is not dict and api_evidence is not None:
        raise ValueError("INVALID_API_EVIDENCE")
    # Optional actual HTTP/pagination provenance, NOT invented if not captured.
    api={"captured":False,"get_only_confirmed":False,
         "all_pages_successful":None,"final_page_token_absent":None,
         "page_count":None}
    if api_evidence is not None:
        if set(api_evidence)!={"get_only","http_statuses","final_page_token_absent"}:
            raise ValueError("INVALID_API_EVIDENCE_KEYS")
        codes=api_evidence["http_statuses"]
        if (api_evidence["get_only"] is not True or type(codes) is not list
            or not 1<=len(codes)<=6 or any(type(x) is not int or x!=200 for x in codes)
            or api_evidence["final_page_token_absent"] is not True):
            raise ValueError("INCOMPLETE_API_FETCH_EVIDENCE")
        api={"captured":True,"get_only_confirmed":True,
             "all_pages_successful":True,"final_page_token_absent":True,
             "page_count":len(codes)}
    rows=[]
    for sym,expected in zip(names,review["results"]):
        data=bars[sym]
        if type(data) is not list or len(data)>MAX_MINUTES:
            raise ValueError("BAD_BAR_LIST")
        observed=set()
        for item in data:
            clean=valid_bar(item,start,end)
            when=parse_utc(clean["t"])
            if when.second or when.microsecond or when in observed:
                raise ValueError("DUPLICATE_OR_NONMINUTE_BAR")
            observed.add(when)
        if len(observed)!=expected.get("observed_iex_bars"):
            raise ValueError("REVIEW_BAR_COUNT_MISMATCH")
        grid=[start+dt.timedelta(minutes=i) for i in range(minutes)]
        missing=[t.isoformat() for t in grid if t not in observed]
        rows.append({"symbol":sym,"observed_bar_start_utc":[t.isoformat() for t in sorted(observed)],
                     "missing_iex_bar_start_utc":missing,
                     "expected_minutes":minutes,"observed_minutes":len(observed),
                     "complete":not missing,
                     "missing_cause":"UNKNOWN_NO_IEX_BAR_OR_DATA_ISSUE"})
    if sum(x["observed_minutes"] for x in rows)!=review["observed_iex_bars"]:
        raise ValueError("REVIEW_TOTAL_MISMATCH")
    return {
        "schema":"LUCA_V03_IEX_TIMESTAMP_PROVENANCE_V1",
        "frozen_t0_sha256":frozen["sha256"],
        "frozen_at_utc":t0.isoformat(),
        "reviewed_at_utc":reviewed.isoformat(),
        "recorded_at_utc":at.isoformat(),
        "feed":"IEX_SINGLE_EXCHANGE_NOT_SIP",
        "expected_minutes_per_symbol":minutes,
        "api_fetch":api,"rows":rows,
        "raw_ohlcv_archived":False,
        "timestamps_are_observed_not_backfilled":True,
        "missing_iex_bar_cause_unknown":True,
        "not_full_market_coverage":True,
        "validation_status":"NOT_VALIDATED","sec_status":"SEC_UNVERIFIED",
        "prediction_accuracy_verified":False,"real_trades_allowed":False,
    }


def write_new(path,doc):
    dest=Path(path)
    if dest.exists():
        raise FileExistsError("IMMUTABLE_OUTPUT_EXISTS")
    if len(json.dumps(doc,ensure_ascii=False))>100_000:
        raise ValueError("PROVENANCE_TOO_LARGE")
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open("x",encoding="utf8") as f:
        json.dump(doc,f,ensure_ascii=False,indent=2)
        f.write("\n")
