"""Verify second GitHub source-run identity BEFORE comparing two real artifacts.

Pure, offline research-only bridge: no network, trading, alerts or schedules.
The caller must obtain GitHub run JSON and artifact files from the actual run.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from two_session_iex_comparison import compare,FIRST_ID
from first_iex_baseline_integrity import load_verified

SECOND_WORKFLOW="LUCA V03 second future IEX prospective once with provenance"
BRANCH="research/v03-stage24-evidence"
FIRST_AUDIT_RUN_ID=40532482508


def verify_second_run(meta,artifact_meta=None):
    if type(meta) is not dict:
        raise ValueError("MISSING_SECOND_RUN_METADATA")
    run_id=meta.get("databaseId")
    if type(run_id) is not int or run_id<=0 or run_id==FIRST_ID:
        raise ValueError("INVALID_SECOND_RUN_ID")
    if meta.get("name")!=SECOND_WORKFLOW:
        raise ValueError("WRONG_SECOND_WORKFLOW")
    if meta.get("headBranch")!=BRANCH or meta.get("event")!="push":
        raise ValueError("WRONG_SECOND_BRANCH_OR_EVENT")
    if meta.get("status")!="completed" or meta.get("conclusion")!="success":
        raise ValueError("SECOND_RUN_NOT_SUCCESSFUL")
    if artifact_meta is not None:
        if type(artifact_meta) is not dict or artifact_meta.get("name")!=f"luca-v03-second-prospective-{run_id}":
            raise ValueError("WRONG_SECOND_ARTIFACT_NAME")
        if artifact_meta.get("expired") is not False:
            raise ValueError("EXPIRED_SECOND_ARTIFACT")
        if artifact_meta.get("workflow_run",{}).get("id")!=run_id:
            raise ValueError("WRONG_SECOND_ARTIFACT_RUN")
    return run_id


def build_verified_comparison(first_audit,second_meta,second_frozen,
                              second_review,second_provenance,artifact_meta=None):
    rid=verify_second_run(second_meta,artifact_meta)
    result=compare(first_audit,second_frozen,second_review,second_provenance,rid)
    if result["real_trades_allowed"] is not False or result["validation_status"]!="NOT_VALIDATED":
        raise ValueError("UNSAFE_COMPARISON")
    result["second_source_workflow_verified"]=True
    result["second_artifact_metadata_verified"]=artifact_meta is not None
    result["first_audit_source_run_id"]=FIRST_AUDIT_RUN_ID
    result["first_audit_artifact_source_verified_externally"]=False
    result["not_a_prediction_win_rate"]=True
    return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--first-audit",default=None,
                   help="Optional original audit file; default is integrity-checked durable real archive")
    p.add_argument("--second-metadata",required=True)
    p.add_argument("--second-artifact-metadata",required=True)
    p.add_argument("--second-artifact-dir",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    def load(path):
        file=Path(path)
        if not file.is_file() or file.stat().st_size>2_000_000:
            raise ValueError("MISSING_OR_OVERSIZE_EVIDENCE")
        return json.loads(file.read_text(encoding="utf8"))
    root=Path(a.second_artifact_dir)
    result=build_verified_comparison(
        load(a.first_audit) if a.first_audit else load_verified(),load(a.second_metadata),
        load(root/"frozen_t0.json"),load(root/"forward_review.json"),
        load(root/"iex_timestamp_provenance.json"),
        load(a.second_artifact_metadata))
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf8") as file:
        json.dump(result,file,ensure_ascii=False,indent=2)
        file.write("\n")
    print(f"TWO_SESSION_COVERAGE; FIRST=94/168; SECOND={result['second']['observed']}/{result['second']['expected']}; "
          "NOT_VALIDATED; NO_ORDERS")


if __name__=="__main__":
    main()
