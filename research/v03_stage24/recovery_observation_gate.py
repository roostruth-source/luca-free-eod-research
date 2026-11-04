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
import urllib.request

from third_trial_gate import BASELINE_COMMIT, UTC, validate_with_official_calendar

REF = "refs/heads/research/v03-recovery-preflight"
REQUEST = "research/v03_stage24/recovery_observation_request.txt"
ARCHIVES = Path("research/v03_stage24/recovery_archives")

def _git(*args):
    return subprocess.check_output(["git", *args], text=True, timeout=15).strip()

def verify_no_prior_workflow_run(opener=None):
    """Fail closed if this request commit has any earlier observation workflow run."""
    token = os.getenv("GITHUB_TOKEN", "")
    repo = os.getenv("GITHUB_REPOSITORY", "")
    run_id = os.getenv("GITHUB_RUN_ID", "")
    head = os.getenv("GITHUB_SHA", "")
    if (not token or repo != "roostruth-source/luca-free-eod-research"
            or not run_id.isdecimal() or len(head) != 40
            or any(c not in "0123456789abcdef" for c in head)):
        raise ValueError("RUN_HISTORY_CHECK_UNAVAILABLE")
    url = ("https://api.github.com/repos/" + repo
           + "/actions/workflows/luca-v03-recovery-observation-once.yml/runs"
           + "?head_sha=" + head + "&per_page=100")
    request = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with (opener or urllib.request.urlopen)(request, timeout=15) as response:
        payload = json.load(response)
    runs = payload.get("workflow_runs")
    if (not isinstance(runs, list) or not isinstance(payload.get("total_count"), int)
            or payload["total_count"] >= 100):
        raise ValueError("RUN_HISTORY_INCOMPLETE")
    current = [r for r in runs if str(r.get("id")) == run_id]
    if len(current) != 1 or any(str(r.get("id")) != run_id for r in runs):
        raise ValueError("PREVIOUS_OBSERVATION_RUN_BLOCKED")


def main():
    # Only an isolated, fresh, single-purpose addition can authorize a run.
    if os.getenv("GITHUB_EVENT_NAME") != "push" or os.getenv("GITHUB_REF") != REF:
        raise ValueError("WRONG_TRIGGER_OR_BRANCH")
    if os.getenv("GITHUB_RUN_ATTEMPT") != "1":
        raise ValueError("RE_RUN_BLOCKED")
    if _git("diff-tree", "--no-commit-id", "--name-status", "-r", "HEAD") != "A\t" + REQUEST:
        raise ValueError("REQUEST_COMMIT_NOT_SINGLE_PURPOSE_CREATION")
    if _git("rev-list", "--count", "HEAD", "--", REQUEST) != "1":
        raise ValueError("REQUEST_MUST_BE_NEW_ONCE")
    subprocess.check_call(["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"], timeout=15)
    request_time = dt.datetime.fromisoformat(_git("log", "-1", "--format=%cI", "--", REQUEST))
    parent = _git("rev-parse", "HEAD^")
    count = len([p for p in ARCHIVES.iterdir() if p.is_dir()]) if ARCHIVES.exists() else 0
    verify_no_prior_workflow_run()
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
