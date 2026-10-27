"""LUCA: source GitHub run inventory including failed, cancelled and pending attempts.

Read-only GitHub Actions metadata audit. Distinguishes pipeline attempts from
market predictions. NEVER computes success rate, trading return or A/B grades.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path

SOURCE_WORKFLOW="LUCA V03 forward IEX once on isolated request file"
SOURCE_PATH=".github/workflows/luca-v03-prospective-live-once.yml"
SOURCE_BRANCH="research/v03-stage24-evidence"
FINAL_CONCLUSIONS={"success","failure","cancelled","timed_out","skipped","neutral","action_required","stale"}
ACTIVE_STATES={"queued","in_progress","waiting","pending","requested"}


def utc_timestamp(value):
    if not isinstance(value,str):
        raise ValueError("MISSING_TIMESTAMP")
    try:
        date=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
    except (ValueError,OverflowError) as e:
        raise ValueError("BAD_TIMESTAMP") from e
    if date.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return date.astimezone(dt.timezone.utc).isoformat()


def build_inventory(api_payload):
    if type(api_payload) is not dict or type(api_payload.get("workflow_runs")) is not list:
        raise ValueError("BAD_GITHUB_RUN_LIST")
    runs=api_payload["workflow_runs"]
    total=api_payload.get("total_count")
    if type(total) is not int or total<0 or total<len(runs):
        raise ValueError("INVALID_TOTAL_COUNT")
    # Never mistake the first 100 runs for all runs.
    if total!=len(runs):
        raise ValueError("PAGINATED_RUNS_INCOMPLETE")
    rows=[]
    ids=set()
    for raw in runs:
        if not isinstance(raw,dict):
            raise ValueError("BAD_RUN")
        if raw.get("name")!=SOURCE_WORKFLOW:
            raise ValueError("WRONG_WORKFLOW_IN_API_RESPONSE")
        if str(raw.get("path","")).split("@",1)[0]!=SOURCE_PATH:
            raise ValueError("WRONG_WORKFLOW_FILE")
        if raw.get("head_branch")!=SOURCE_BRANCH or raw.get("event")!="push":
            raise ValueError("WRONG_BRANCH_OR_EVENT")
        rid=raw.get("id")
        if type(rid) is not int or rid<=0 or rid in ids:
            raise ValueError("DUPLICATE_OR_BAD_RUN_ID")
        ids.add(rid)
        status=raw.get("status")
        conclusion=raw.get("conclusion")
        if status=="completed":
            if conclusion not in FINAL_CONCLUSIONS:
                raise ValueError("UNKNOWN_COMPLETED_CONCLUSION")
            outcome=("GITHUB_SUCCESS_EVIDENCE_NOT_YET_VERIFIED" if conclusion=="success"
                     else "GITHUB_"+conclusion.upper())
        elif status in ACTIVE_STATES:
            if conclusion is not None:
                raise ValueError("ACTIVE_RUN_HAS_CONCLUSION")
            outcome="GITHUB_PENDING_NOT_FAILURE"
        else:
            raise ValueError("UNKNOWN_RUN_STATUS")
        created=utc_timestamp(raw.get("created_at"))
        started=utc_timestamp(raw.get("run_started_at") or raw.get("created_at"))
        if started<created:
            raise ValueError("RUN_START_BEFORE_CREATION")
        rows.append({
            "source_run_id":rid,
            "created_at_utc":created,
            "started_at_utc":started,
            "github_status":status,
            "github_conclusion":conclusion,
            "study_status":outcome,
            "source_workflow":SOURCE_WORKFLOW,
            "source_branch":SOURCE_BRANCH,
            "artifact_integrity_verified":False,
            "actual_pattern_success_verified":False,
            "real_trades_allowed":False,
        })
    rows.sort(key=lambda x:(x["created_at_utc"],x["source_run_id"]))
    return {
        "schema":"LUCA_V03_SOURCE_GITHUB_ATTEMPT_INVENTORY_V1",
        "source_workflow":SOURCE_WORKFLOW,
        "source_branch":SOURCE_BRANCH,
        "runs_listed":len(rows),
        "github_success_count":sum(x["github_conclusion"]=="success" for x in rows),
        "github_failed_or_cancelled_count":sum(x["github_status"]=="completed" and x["github_conclusion"]!="success" for x in rows),
        "github_pending_count":sum(x["github_status"]!="completed" for x in rows),
        "runs":rows,
        "github_run_coverage_complete_at_snapshot":True,
        "automation_attempts_before_github_trigger_not_observable":True,
        "github_success_is_not_market_success":True,
        "failed_or_cancelled_runs_not_dropped":True,
        "prediction_accuracy_verified":False,
        "sec_status":"SEC_UNVERIFIED",
        "validation_status":"NOT_VALIDATED",
        "real_trades_allowed":False,
        "note":"Counts GitHub workflow attempts only, including failed and pending. A GitHub success is NOT a validated T0 artifact or successful stock signal. No profit/hit-rate denominator is established.",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    source=Path(args.input)
    if source.stat().st_size>5_000_000:
        raise ValueError("GITHUB_RUN_LIST_TOO_LARGE")
    report=build_inventory(json.loads(source.read_text(encoding="utf8")))
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x",encoding="utf8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print("GITHUB_ATTEMPTS="+str(report["runs_listed"])+
          "; GITHUB_FAILED_OR_CANCELLED="+str(report["github_failed_or_cancelled_count"])+
          "; PENDING="+str(report["github_pending_count"])+
          "; NO_MARKET_WIN_RATE; NOT_VALIDATED; NO_ORDERS")


if __name__=="__main__":
    main()
