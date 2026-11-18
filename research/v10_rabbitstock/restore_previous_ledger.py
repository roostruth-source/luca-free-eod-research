"""Restore only the previous research ledger artifact from this GitHub workflow."""

from __future__ import annotations

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import re
import urllib.parse
import urllib.request
from zipfile import ZipFile, BadZipFile

DEFAULT_WORKFLOW = "luca-v10-research-build-ci.yml"
DEFAULT_BRANCH = "research/v10-rabbitstock-eval"
ARTIFACT = "luca-v10-executable-research-build"
MAX_BYTES = 12_000_000


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            redirected.remove_header("Authorization")
        return redirected


def _request(url: str, token: str, opener=None) -> bytes:
    if not url.startswith("https://api.github.com/repos/"):
        raise ValueError("github_api_url_required")
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "LUCA-Research-Ledger/1.0",
    }, method="GET")
    safe_opener = opener or urllib.request.build_opener(_SafeRedirect()).open
    with safe_opener(req, timeout=20) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("github_artifact_too_large")
    return data


def restore(repo: str, current_run_id: int, token: str, opener=None,
            workflow: str = DEFAULT_WORKFLOW, branch: str = DEFAULT_BRANCH) -> dict | None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not token:
        raise ValueError("github_repo_and_token_required")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.ya?ml", workflow):
        raise ValueError("github_workflow_name_invalid")
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", branch) or ".." in branch:
        raise ValueError("github_branch_name_invalid")
    root = "https://api.github.com/repos/" + repo
    query = urllib.parse.urlencode({"branch": branch,
                                    "status": "success", "per_page": 10})
    runs = json.loads(_request(f"{root}/actions/workflows/{workflow}/runs?{query}", token, opener))
    for run in runs.get("workflow_runs", []):
        run_id = int(run["id"])
        if run_id == current_run_id:
            continue
        artifacts = json.loads(_request(f"{root}/actions/runs/{run_id}/artifacts", token, opener))
        for artifact in artifacts.get("artifacts", []):
            if artifact.get("name") != ARTIFACT or artifact.get("expired"):
                continue
            archive = _request(f"{root}/actions/artifacts/{int(artifact['id'])}/zip", token, opener)
            with ZipFile(BytesIO(archive)) as zf:
                names = [name for name in zf.namelist() if name == "prospective_ledger.json"]
                if not names:
                    continue
                if zf.getinfo(names[0]).file_size > MAX_BYTES:
                    raise ValueError("ledger_entry_too_large")
                ledger = json.loads(zf.read(names[0]))
                if ledger.get("schema_version") == "LUCA_V10_PROSPECTIVE_LEDGER_1":
                    return ledger
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        ledger = restore(os.getenv("GITHUB_REPOSITORY", ""),
                         int(os.getenv("GITHUB_RUN_ID", "0")), os.getenv("GITHUB_TOKEN", ""),
                         workflow=os.getenv("LUCA_LEDGER_WORKFLOW", DEFAULT_WORKFLOW),
                         branch=os.getenv("LUCA_LEDGER_BRANCH", DEFAULT_BRANCH))
    except (OSError, ValueError, KeyError, BadZipFile) as exc:
        print(json.dumps({"restore_status": "UNAVAILABLE", "reason": type(exc).__name__}))
        return 0
    if ledger is None:
        print(json.dumps({"restore_status": "NO_PREVIOUS_LEDGER"}))
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"restore_status": "RESTORED", "events": ledger["event_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
