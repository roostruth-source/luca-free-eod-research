"""Fail-closed gate for one manual V10 observation on the research branch."""

from __future__ import annotations

import argparse
from datetime import datetime, time, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from prospective_outcomes import _known_closed_equity_session

ET = ZoneInfo("America/New_York")
EXPECTED_BRANCH = "research/v10-rabbitstock-eval"
EXPECTED_APPROVAL = "RUN_V10_WATCH_ONLY"
ALLOWED_RESTORE = {"RESTORED", "NO_PREVIOUS_SUCCESSFUL_RUN"}


def _parse_time(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timezone_required")
    return value.astimezone(timezone.utc)


def evaluate(now: datetime, event_name: str, ref_name: str, approval: str,
             restore_status: dict, previous: dict | None = None) -> dict:
    if now.tzinfo is None:
        raise ValueError("now_timezone_required")
    now_et = now.astimezone(ET)
    reasons = []
    if event_name != "workflow_dispatch":
        reasons.append("MANUAL_WORKFLOW_DISPATCH_REQUIRED")
    if ref_name != EXPECTED_BRANCH:
        reasons.append("WRONG_RESEARCH_BRANCH")
    if approval != EXPECTED_APPROVAL:
        reasons.append("APPROVAL_PHRASE_MISMATCH")
    status = restore_status.get("restore_status") if isinstance(restore_status, dict) else None
    if status not in ALLOWED_RESTORE:
        reasons.append("PREVIOUS_LEDGER_RECOVERY_NOT_SAFE")
    if _known_closed_equity_session(now_et.date()):
        reasons.append("NYSE_WEEKEND_OR_FULL_CLOSURE")
    if not time(9, 36) <= now_et.time() < time(10, 30):
        reasons.append("OUTSIDE_0936_1030_NEW_YORK_WINDOW")
    if status == "RESTORED":
        if (not isinstance(previous, dict)
                or previous.get("schema_version") != "LUCA_V10_PROSPECTIVE_LEDGER_1"
                or previous.get("WATCH_ONLY") is not True
                or previous.get("NO_ORDERS") is not True
                or previous.get("validation_status") != "NOT_VALIDATED"):
            reasons.append("RESTORED_LEDGER_INVALID_OR_UNSAFE")
        else:
            prior_date = _parse_time(previous["source_collected_at"]).astimezone(ET).date()
            if prior_date >= now_et.date():
                reasons.append("DUPLICATE_OR_OUT_OF_ORDER_NEW_YORK_DATE")
    elif previous is not None:
        reasons.append("UNEXPECTED_LEDGER_WITHOUT_RESTORE")
    return {
        "schema_version": "LUCA_V10_DAILY_GUARD_1",
        "allowed": not reasons,
        "reasons": reasons,
        "checked_at_utc": now.astimezone(timezone.utc).isoformat(),
        "new_york_time": now_et.isoformat(),
        "branch": ref_name,
        "restore_status": status,
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--now")
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--ref-name", required=True)
    parser.add_argument("--approval", required=True)
    parser.add_argument("--restore-status", type=Path, required=True)
    parser.add_argument("--previous-ledger", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    now = _parse_time(args.now) if args.now else datetime.now(timezone.utc)
    status = json.loads(args.restore_status.read_text())
    previous = None
    if args.previous_ledger and args.previous_ledger.exists():
        previous = json.loads(args.previous_ledger.read_text())
    result = evaluate(now, args.event_name, args.ref_name, args.approval,
                      status, previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
