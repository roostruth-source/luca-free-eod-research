"""Fail-closed gate for ONE future prospective US morning research trial.

This module NEVER schedules or triggers a market request. The request file is
deliberately absent until Work/user chooses a future NY session. No orders.
"""
from __future__ import annotations
import datetime as dt
from zoneinfo import ZoneInfo

UTC=dt.timezone.utc
NY=ZoneInfo("America/New_York")
HEADER="LUCA_V03_SECOND_PROSPECTIVE_ONCE"
BRANCH="refs/heads/research/v03-stage24-evidence"
REQUEST_PATH="research/v03_stage24/second_prospective_request.txt"


def validate(text,now,event_name,ref,run_attempt,request_history_commits):
    if type(text) is not str or len(text)>256:
        raise ValueError("BAD_REQUEST_FILE")
    if type(now) is not dt.datetime or now.tzinfo is None:
        raise ValueError("AWARE_NOW_REQUIRED")
    if event_name!="push" or ref!=BRANCH:
        raise ValueError("WRONG_TRIGGER_OR_BRANCH")
    if str(run_attempt)!="1":
        raise ValueError("RE_RUN_BLOCKED")
    if type(request_history_commits) is not int or request_history_commits!=1:
        raise ValueError("REPEATED_REQUEST_COMMIT_BLOCKED")
    lines=text.splitlines()
    if len(lines)!=3 or lines[0]!=HEADER or lines[2]!="research_only=true":
        raise ValueError("BAD_REQUEST_FORMAT")
    key="session_day_ny="
    if not lines[1].startswith(key):
        raise ValueError("MISSING_SESSION_DAY")
    date_string=lines[1][len(key):]
    try:
        requested=dt.date.fromisoformat(date_string)
    except ValueError as exc:
        raise ValueError("BAD_SESSION_DAY") from exc
    if requested.isoformat()!=date_string:
        raise ValueError("NONCANONICAL_SESSION_DAY")
    local=now.astimezone(NY)
    if local.date()!=requested or local.weekday()>=5:
        raise ValueError("NOT_REQUESTED_US_WEEKDAY")
    # Conservative research-only morning window, no NYSE holiday guarantee.
    if not (dt.time(9,40)<=local.time().replace(tzinfo=None)<=dt.time(11,20)):
        raise ValueError("OUTSIDE_RESEARCH_MORNING")
    return {
        "schema":"LUCA_V03_SECOND_TRIAL_GATE_V1",
        "session_day_ny":date_string,
        "checked_at_utc":now.astimezone(UTC).isoformat(),
        "allowed":True,
        "not_nyse_holiday_verified":True,
        "research_only":True,
        "validation_status":"NOT_VALIDATED",
        "sec_status":"SEC_UNVERIFIED",
        "real_trades_allowed":False,
    }


def main():
    import json
    import os
    from pathlib import Path
    import subprocess
    count=subprocess.check_output(
        ["git","rev-list","--count","HEAD","--",REQUEST_PATH],
        text=True,timeout=15).strip()
    if not count.isdecimal():
        raise ValueError("INVALID_REQUEST_HISTORY")
    request=Path(REQUEST_PATH).read_text(encoding="utf8")
    result=validate(
        request,dt.datetime.now(UTC),
        os.getenv("GITHUB_EVENT_NAME",""),
        os.getenv("GITHUB_REF",""),
        os.getenv("GITHUB_RUN_ATTEMPT",""),
        int(count))
    print("SECOND_TRIAL_GATE: "+json.dumps(result,sort_keys=True))
    print("RESEARCH_ONLY; NOT_VALIDATED; NO_ORDERS")


if __name__=="__main__":
    main()
