"""Resolve the one-session ambiguity in share-combination reset dates.

The tool deliberately separates the calendar from the legal interpretation.
It always reports both mechanical candidates.  A single date is selected only
when the filed contract supplies an explicit counting anchor.  Ambiguous text
is WATCH_ONLY and cannot be passed to a return evaluator as a unique event.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _official_url(value: str) -> None:
    if not value.startswith("https://www.sec.gov/"):
        raise ValueError("official_sec_anchor_source_required")


def resolve_reset_session_anchor(payload: dict[str, Any]) -> dict[str, Any]:
    evaluation_asof = _time(payload["evaluation_asof"])
    reference_at = _time(payload["reference_at"])
    if reference_at > evaluation_asof:
        raise ValueError("future_reference_not_allowed")

    evidence = payload["anchor_evidence"]
    evidence_at = _time(evidence["evidence_available_at"])
    if evidence_at > reference_at:
        raise ValueError("future_anchor_evidence_not_allowed")
    _official_url(str(evidence.get("source_url", "")))

    event_date = _date(payload["share_combination_event_date"])
    sessions = [_date(value) for value in payload["trading_sessions_after_event"]]
    if not sessions or sessions != sorted(set(sessions)):
        raise ValueError("trading_sessions_must_be_unique_and_ordered")
    if any(session <= event_date for session in sessions):
        raise ValueError("trading_session_must_follow_event")

    reset_after = int(payload["reset_after_trading_sessions"])
    if reset_after <= 1 or len(sessions) < reset_after:
        raise ValueError("insufficient_sessions_to_resolve_anchor")

    after_candidate = sessions[reset_after - 1]
    including_candidate = sessions[reset_after - 2]
    policy = str(evidence["anchor_policy"])
    if policy not in {"AFTER_EVENT_DATE", "INCLUDING_EVENT_DATE", "AMBIGUOUS"}:
        raise ValueError("invalid_anchor_policy")

    quote = str(evidence.get("contract_quote", "")).strip()
    quote_lower = quote.lower()
    if policy == "AFTER_EVENT_DATE" and not (
        "after such" in quote_lower or "following such" in quote_lower
    ):
        raise ValueError("after_event_date_language_required")
    if policy == "INCLUDING_EVENT_DATE" and "including" not in quote_lower:
        raise ValueError("including_event_date_language_required")

    selected = None
    status = "RESET_DATE_ONE_SESSION_AMBIGUITY"
    reasons = ["RESET_DATE_ANCHOR_AMBIGUOUS"]
    if policy == "AFTER_EVENT_DATE":
        selected = after_candidate
        status = "CONTRACT_ANCHOR_VERIFIED"
        reasons = []
    elif policy == "INCLUDING_EVENT_DATE":
        selected = including_candidate
        status = "CONTRACT_ANCHOR_VERIFIED"
        reasons = []

    return {
        "evaluation_asof": evaluation_asof.isoformat(),
        "reference_at": reference_at.isoformat(),
        "ticker": payload["ticker"],
        "share_combination_event_date": event_date.isoformat(),
        "reset_after_trading_sessions": reset_after,
        "anchor_policy": policy,
        "after_event_date_candidate": after_candidate.isoformat(),
        "including_event_date_candidate": including_candidate.isoformat(),
        "selected_reset_date": selected.isoformat() if selected else None,
        "resolution_status": status,
        "eligible_for_return_evaluation": selected is not None,
        "block_reasons": reasons,
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input_json.read_text())
    print(json.dumps(resolve_reset_session_anchor(payload), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
