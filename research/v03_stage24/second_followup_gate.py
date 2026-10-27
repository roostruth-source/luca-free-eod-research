"""Fail-closed, future-only second-session 60-minute outcome followup gate.

The caller must supply real GitHub run metadata and original downloaded
artifacts. Never dispatches workflows or makes network requests itself.
"""
from __future__ import annotations
import datetime as dt
from zoneinfo import ZoneInfo

from second_trial_artifact_bridge import verify_second_run
from forward_outcomes_iex import validate_origins,parse_utc

NY=ZoneInfo("America/New_York")
UTC=dt.timezone.utc
BRANCH="refs/heads/research/v03-stage24-evidence"
REQUEST_PATH="research/v03_stage24/second_followup_request.txt"
SESSION_DAY=dt.date(2026,10,28)


def gate(run_id_text,meta,frozen,review,provenance,now,event,ref,attempt,history):
    if event!="push" or ref!=BRANCH or str(attempt)!="1":
        raise ValueError("WRONG_FOLLOWUP_TRIGGER")
    if type(history) is not int or history!=1:
        raise ValueError("DUPLICATE_FOLLOWUP_REQUEST")
    if type(run_id_text) is not str or len(run_id_text)>20:
        raise ValueError("INVALID_FOLLOWUP_REQUEST")
    requested=run_id_text.strip()
    if not requested.isdecimal() or requested.startswith("0") or len(requested)<8 or len(requested)>15:
        raise ValueError("INVALID_FOLLOWUP_REQUEST")
    rid=verify_second_run(meta)
    if int(requested)!=rid:
        raise ValueError("SECOND_SOURCE_RUN_ID_MISMATCH")
    t0,reviewed,signals=validate_origins(frozen,review)
    if t0.astimezone(NY).date()!=SESSION_DAY:
        raise ValueError("WRONG_SECOND_SOURCE_SESSION_DAY")
    if provenance.get("schema")!="LUCA_V03_IEX_TIMESTAMP_PROVENANCE_V1" or provenance.get("frozen_t0_sha256")!=frozen["sha256"]:
        raise ValueError("MISSING_SECOND_IEX_PROVENANCE")
    if provenance.get("validation_status")!="NOT_VALIDATED" or provenance.get("real_trades_allowed") is not False:
        raise ValueError("UNSAFE_PROVENANCE")
    if provenance.get("api_fetch",{}).get("all_pages_successful") is not True:
        raise ValueError("UNVERIFIED_IEX_HTTP")
    if (parse_utc(provenance.get("frozen_at_utc"))!=t0 or
        parse_utc(provenance.get("reviewed_at_utc"))!=reviewed or
        [r.get("symbol") for r in provenance.get("rows",[])]!=frozen["candidates"]):
        raise ValueError("SECOND_PROVENANCE_ORIGIN_MISMATCH")
    if (sum(r.get("observed_minutes",0) for r in provenance["rows"])!=review["observed_iex_bars"] or
        any(r.get("observed_minutes")!=x.get("observed_iex_bars")
            for r,x in zip(provenance["rows"],review["results"]))):
        raise ValueError("SECOND_PROVENANCE_COUNTS_MISMATCH")
    if type(now) is not dt.datetime or now.tzinfo is None:
        raise ValueError("AWARE_NOW_REQUIRED")
    checked=now.astimezone(UTC)
    if checked<t0+dt.timedelta(minutes=82):
        raise ValueError("FOLLOWUP_NOT_YET_MATURE")
    if checked>t0+dt.timedelta(hours=8):
        raise ValueError("FOLLOWUP_TOO_LATE")
    return {
        "schema":"LUCA_V03_SECOND_FOLLOWUP_GATE_V1",
        "verified_second_run_id":rid,
        "frozen_t0_sha256":frozen["sha256"],
        "source_frozen_at_utc":t0.isoformat(),
        "source_reviewed_at_utc":reviewed.isoformat(),
        "checked_at_utc":checked.isoformat(),
        "signals_at_t0":len(signals),
        "ready_for_fixed_clock_60min":True,
        "research_only":True,
        "validation_status":"NOT_VALIDATED",
        "sec_status":"SEC_UNVERIFIED",
        "real_trades_allowed":False,
    }
