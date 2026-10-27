"""LUCA: strict one-time GitHub prospective run artifact provenance checks.

Standalone offline gate used by a research-only followup workflow. Never upgrades
SEC, trading grade, validation status or modifies existing code/site/schedules.
"""
from __future__ import annotations
import json
import pathlib
import re


RUN_WORKFLOW = "LUCA V03 forward IEX once on isolated request file"
RESEARCH_BRANCH = "research/v03-stage24-evidence"


def read_run_id(path):
    text = pathlib.Path(path).read_text(encoding="utf8").strip()
    if not re.fullmatch(r"[1-9][0-9]{7,14}", text):
        raise ValueError("INVALID_RUN_ID")
    return int(text)


def validate_github_run(payload, requested_id):
    if not isinstance(payload, dict):
        raise ValueError("INVALID_GITHUB_RESPONSE")
    if payload.get("databaseId") != requested_id:
        raise ValueError("WRONG_RUN_ID")
    if payload.get("name") != RUN_WORKFLOW:
        raise ValueError("WRONG_WORKFLOW")
    if payload.get("headBranch") != RESEARCH_BRANCH or payload.get("event") != "push":
        raise ValueError("WRONG_BRANCH_OR_EVENT")
    if payload.get("status") != "completed" or payload.get("conclusion") != "success":
        raise ValueError("PROSPECTIVE_RUN_NOT_SUCCESSFUL")
    # gh run JSON omits artifacts; check those separately after gh run download.
    return {"approved_source_run_id": requested_id,
            "approved_source_workflow": RUN_WORKFLOW,
            "branch": RESEARCH_BRANCH,
            "research_only": True, "real_trades_allowed": False}


def verify_downloaded_files(folder):
    from forward_outcomes_iex import validate_origins
    folder=pathlib.Path(folder)
    required=("frozen_t0.json","forward_review.json")
    if any(not (folder/name).is_file() for name in required):
        raise ValueError("MISSING_OR_INCOMPLETE_PROSPECTIVE_ARTIFACT")
    frozen=json.loads((folder/required[0]).read_text(encoding="utf8"))
    review=json.loads((folder/required[1]).read_text(encoding="utf8"))
    _t0,_observed,entries=validate_origins(frozen,review)
    return {"frozen_symbols": len(frozen["candidates"]),
            "forward_signal_symbols": len(entries),
            "hash_verified": True,"source_verified": True,
            "real_trades_allowed": False,"validation_status": "NOT_VALIDATED"}


if __name__ == "__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--request",required=True)
    p.add_argument("--metadata-json",required=True)
    p.add_argument("--artifact-dir",required=True)
    args=p.parse_args()
    run_id=read_run_id(args.request)
    meta=json.loads(pathlib.Path(args.metadata_json).read_text(encoding="utf8"))
    source=validate_github_run(meta,run_id)
    artifact=verify_downloaded_files(args.artifact_dir)
    print("SOURCE_APPROVED_RESEARCH_ONLY",json.dumps({"run":source,"artifact":artifact},sort_keys=True))
