"""Independent one-time observation authorization for the recovery research branch.

Does not generate approval, touch market APIs, or place orders. Invoke only
from a push workflow whose HEAD adds exactly the new request file.
"""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import subprocess

from third_trial_gate import BASELINE_COMMIT, UTC, validate_with_official_calendar

REF = "refs/heads/research/v03-recovery-preflight"
REQUEST = "research/v03_stage24/recovery_observation_request.txt"
ARCHIVES = Path("research/v03_stage24/recovery_archives")

def _git(*args):
    return subprocess.check_output(["git", *args], text=True, timeout=15).strip()

def main():
    # Only an isolated, fresh, single-purpose addition can authorize a run.
    if os.getenv("GITHUB_EVENT_NAME") != "push" or os.getenv("GITHUB_REF") != REF:
        raise ValueError("WRONG_TRIGGER_OR_BRANCH")
    if os.getenv("GITHUB_RUN_ATTEMPT") != "1":
        raise ValueError("RE_RUN_BLOCKED")
    if _git("diff-tree", "--no-commit-id", "--name-status", "-r", "HEAD") != "A\\t" + REQUEST:
        raise ValueError("REQUEST_COMMIT_NOT_SINGLE_PURPOSE_CREATION")
    if _git("rev-list", "--count", "HEAD", "--", REQUEST) != "1":
        raise ValueError("REQUEST_MUST_BE_NEW_ONCE")
    subprocess.check_call(["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"], timeout=15)
    request_time = dt.datetime.fromisoformat(_git("log", "-1", "--format=%cI", "--", REQUEST))
    parent = _git("rev-parse", "HEAD^")
    count = len([p for p in ARCHIVES.iterdir() if p.is_dir()]) if ARCHIVES.exists() else 0
    result = validate_with_official_calendar(
        Path(REQUEST).read_text(encoding="utf-8"), dt.datetime.now(UTC),
        os.getenv("GITHUB_EVENT_NAME", ""), os.getenv("GITHUB_REF", ""),
        os.getenv("GITHUB_RUN_ATTEMPT", ""), 1, request_time,
        os.getenv("LUCA_V03_RECOVERY_APPROVAL_SHA256", ""), count, parent,
        expected_ref=REF)
    print("RECOVERY_AUTHORIZED_READ_ONLY: " + json.dumps(result, sort_keys=True))
    print("NOT_VALIDATED; SEC_UNVERIFIED; D; NO_ORDERS")

if __name__ == "__main__":
    main()
