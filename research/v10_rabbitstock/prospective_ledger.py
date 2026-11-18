"""Append-only prospective observations; no hindsight labels or order signals."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ZERO = "0" * 64
MAX_EVENTS = 5000


def _time(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timezone_required")
    return value.astimezone(timezone.utc)


def _hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def append_observations(report: dict, built_at: str, previous: dict | None = None) -> dict:
    now = _time(built_at)
    observed_at = _time(report["collected_at"])
    if observed_at > now:
        raise ValueError("future_watchlist_not_allowed")
    if report.get("NO_ORDERS") is not True or report.get("validation_status") != "NOT_VALIDATED":
        raise ValueError("unsafe_watchlist")
    events = list(previous.get("events", [])) if previous else []
    chain = previous.get("last_chain_hash", ZERO) if previous else ZERO
    if previous:
        if previous.get("schema_version") != "LUCA_V10_PROSPECTIVE_LEDGER_1":
            raise ValueError("previous_ledger_schema_mismatch")
        if previous.get("NO_ORDERS") is not True or _time(previous["built_at"]) > now:
            raise ValueError("previous_ledger_invalid_or_future")
        expected = ZERO
        for event in events:
            actual = event.get("chain_hash")
            item = {key: value for key, value in event.items() if key != "chain_hash"}
            expected = hashlib.sha256((expected + _hash(item)).encode()).hexdigest()
            if actual != expected:
                raise ValueError("previous_ledger_chain_invalid")
        if chain != expected:
            raise ValueError("previous_ledger_head_invalid")
        if events and observed_at < _time(events[-1]["observed_at"]):
            raise ValueError("out_of_order_watchlist")
        if (observed_at == _time(previous["source_collected_at"])
                and _hash(report) != previous["input_report_hash"]):
            raise ValueError("same_time_report_revision_not_allowed")
    if len(events) + len(report["rows"]) > MAX_EVENTS:
        raise ValueError("prospective_ledger_capacity_exceeded")
    known = {(e["ticker"], e["observed_at"]) for e in events}
    new_count = 0
    for row in report["rows"]:
        identity = (row["ticker"], observed_at.isoformat())
        if identity in known:
            continue
        known.add(identity)
        item = {
            "ticker": row["ticker"],
            "observed_at": observed_at.isoformat(),
            "iex_reference_price": row.get("iex_price"),
            "iex_status": row["iex_status"],
            "sec_status": row["sec_status"],
            "observation_status": "FRESH_WATCH_ONLY" if row["iex_status"] == "WATCH_ONLY_FRESH_IEX"
                                  else "STALE_OR_MISSING_PRICE_BLOCKED",
            "outcome_status": "PENDING_NOT_MATURE",
            "predicted_spike": False,
            "NO_ORDERS": True,
        }
        chain = hashlib.sha256((chain + _hash(item)).encode()).hexdigest()
        events.append({**item, "chain_hash": chain})
        new_count += 1
    return {
        "schema_version": "LUCA_V10_PROSPECTIVE_LEDGER_1",
        "built_at": now.isoformat(),
        "source_collected_at": observed_at.isoformat(),
        "input_report_hash": _hash(report),
        "previous_event_count": len(events) - new_count,
        "new_event_count": new_count,
        "event_count": len(events),
        "continuity_status": "CHAIN_CONTINUED" if previous else "NEW_SERIES_PREVIOUS_UNAVAILABLE",
        "last_chain_hash": chain,
        "events": events,
        "WATCH_ONLY": True, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("watchlist", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--built-at", required=True)
    args = parser.parse_args()
    report = json.loads(args.watchlist.read_text(encoding="utf-8"))
    previous = json.loads(args.previous.read_text(encoding="utf-8")) if args.previous else None
    result = append_observations(report, args.built_at, previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"new": result["new_event_count"], "total": result["event_count"],
                      "NO_ORDERS": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
