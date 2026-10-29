"""Fail-closed approval gate for exactly one third prospective observation.

The trigger file is intentionally absent. This module never creates it, never
contacts a market API and never schedules a workflow. A future approval needs
both a fresh, single-purpose request-file commit and a matching repository
secret hash supplied by the user at approval time.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
from zoneinfo import ZoneInfo


UTC = dt.timezone.utc
NY = ZoneInfo("America/New_York")
HEADER = "LUCA_V03_THIRD_PROSPECTIVE_ONCE"
BRANCH = "refs/heads/research/v03-stage24-evidence"
BASELINE_COMMIT = "6d8ef32fd0de22ed61675cbbccadefed0fe26945"
REQUEST_PATH = "research/v03_stage24/third_prospective_request.txt"
MAX_REQUEST_AGE = dt.timedelta(minutes=10)
MAX_APPROVAL_WINDOW = dt.timedelta(minutes=20)


def approval_sha256(nonce):
    if type(nonce) is not str:
        raise ValueError("BAD_APPROVAL_NONCE")
    return hashlib.sha256(nonce.encode("ascii")).hexdigest()


def _parse_request(text):
    if type(text) is not str or len(text) > 640:
        raise ValueError("BAD_REQUEST_FILE")
    lines = text.splitlines()
    if len(lines) != 8 or lines[0] != HEADER:
        raise ValueError("BAD_REQUEST_FORMAT")
    expected = (
        "session_day_ny=", "expires_at_utc=", "approval_nonce=",
        "baseline_commit=", "approved_code_commit=",
        "research_only=", "orders_allowed=",
    )
    values = {}
    for line, prefix in zip(lines[1:], expected):
        if not line.startswith(prefix):
            raise ValueError("BAD_REQUEST_FORMAT")
        values[prefix[:-1]] = line[len(prefix):]
    if (values["baseline_commit"] != BASELINE_COMMIT or
            values["research_only"] != "true" or
            values["orders_allowed"] != "false"):
        raise ValueError("UNSAFE_REQUEST")
    approved = values["approved_code_commit"]
    if (len(approved) != 40 or
            any(char not in "0123456789abcdef" for char in approved)):
        raise ValueError("BAD_APPROVED_CODE_COMMIT")
    nonce = values["approval_nonce"]
    if len(nonce) != 64 or any(char not in "0123456789abcdef" for char in nonce):
        raise ValueError("BAD_APPROVAL_NONCE")
    try:
        session_day = dt.date.fromisoformat(values["session_day_ny"])
        expires = dt.datetime.fromisoformat(values["expires_at_utc"])
    except ValueError as exc:
        raise ValueError("BAD_REQUEST_TIME") from exc
    if (session_day.isoformat() != values["session_day_ny"] or
            expires.tzinfo is None or expires.utcoffset() != dt.timedelta(0) or
            expires.isoformat() != values["expires_at_utc"]):
        raise ValueError("NONCANONICAL_REQUEST_TIME")
    return values, session_day, expires.astimezone(UTC), nonce


def validate(text, now, event_name, ref, run_attempt,
             request_history_commits, request_commit_at,
             approval_secret_hash, existing_archive_count,
             request_parent_commit):
    if type(now) is not dt.datetime or now.tzinfo is None:
        raise ValueError("AWARE_NOW_REQUIRED")
    now = now.astimezone(UTC)
    if event_name != "push" or ref != BRANCH:
        raise ValueError("WRONG_TRIGGER_OR_BRANCH")
    if str(run_attempt) != "1":
        raise ValueError("RE_RUN_BLOCKED")
    if type(request_history_commits) is not int or request_history_commits != 1:
        raise ValueError("REPEATED_REQUEST_COMMIT_BLOCKED")
    if type(existing_archive_count) is not int or existing_archive_count != 0:
        raise ValueError("THIRD_ARCHIVE_ALREADY_EXISTS")
    if type(request_commit_at) is not dt.datetime or request_commit_at.tzinfo is None:
        raise ValueError("AWARE_REQUEST_COMMIT_TIME_REQUIRED")
    age = now - request_commit_at.astimezone(UTC)
    if age < dt.timedelta(0) or age > MAX_REQUEST_AGE:
        raise ValueError("STALE_OR_FUTURE_REQUEST_COMMIT")
    values, session_day, expires, nonce = _parse_request(text)
    if values["approved_code_commit"] != request_parent_commit:
        raise ValueError("APPROVED_CODE_COMMIT_MISMATCH")
    if not (now < expires <= now + MAX_APPROVAL_WINDOW):
        raise ValueError("EXPIRED_OR_OVERSIZED_APPROVAL_WINDOW")
    if (type(approval_secret_hash) is not str or len(approval_secret_hash) != 64 or
            not hmac.compare_digest(approval_sha256(nonce), approval_secret_hash)):
        raise ValueError("USER_APPROVAL_SECRET_MISMATCH")
    local = now.astimezone(NY)
    if local.date() != session_day or local.weekday() >= 5:
        raise ValueError("NOT_REQUESTED_US_WEEKDAY")
    if not (dt.time(9, 40) <= local.time().replace(tzinfo=None) <= dt.time(11, 20)):
        raise ValueError("OUTSIDE_RESEARCH_MORNING")
    return {
        "schema": "LUCA_V03_THIRD_TRIAL_GATE_V1",
        "session_day_ny": values["session_day_ny"],
        "baseline_commit": BASELINE_COMMIT,
        "approved_code_commit": values["approved_code_commit"],
        "checked_at_utc": now.isoformat(),
        "request_age_seconds": int(age.total_seconds()),
        "two_key_user_approval_verified": True,
        "allowed": True,
        "nyse_holiday_calendar_verified": False,
        "research_only": True,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "real_trades_allowed": False,
        "orders_allowed": False,
    }


def main():
    import json
    import os
    from pathlib import Path
    import subprocess

    count_text = subprocess.check_output(
        ["git", "rev-list", "--count", "HEAD", "--", REQUEST_PATH],
        text=True, timeout=15).strip()
    if not count_text.isdecimal():
        raise ValueError("INVALID_REQUEST_HISTORY")
    changed = subprocess.check_output(
        ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", "HEAD"],
        text=True, timeout=15).splitlines()
    if changed != ["A\t" + REQUEST_PATH]:
        raise ValueError("REQUEST_COMMIT_NOT_SINGLE_PURPOSE_CREATION")
    subprocess.check_call(
        ["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"],
        timeout=15)
    commit_time_text = subprocess.check_output(
        ["git", "log", "-1", "--format=%cI", "--", REQUEST_PATH],
        text=True, timeout=15).strip()
    commit_time = dt.datetime.fromisoformat(commit_time_text)
    parent_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD^"], text=True, timeout=15).strip()
    archive_root = Path("research/v03_stage24/third_archives")
    archives = [path for path in archive_root.iterdir() if path.is_dir()] if archive_root.exists() else []
    result = validate(
        Path(REQUEST_PATH).read_text(encoding="utf8"), dt.datetime.now(UTC),
        os.getenv("GITHUB_EVENT_NAME", ""), os.getenv("GITHUB_REF", ""),
        os.getenv("GITHUB_RUN_ATTEMPT", ""), int(count_text), commit_time,
        os.getenv("LUCA_V03_THIRD_APPROVAL_SHA256", ""), len(archives),
        parent_commit)
    print("THIRD_TRIAL_GATE: " + json.dumps(result, sort_keys=True))
    print("RESEARCH_ONLY; NOT_VALIDATED; SEC_UNVERIFIED; D; NO_ORDERS")


if __name__ == "__main__":
    main()
