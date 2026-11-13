"""Audit revisions from the same public price source without double-counting it.

Repeated snapshots from one URL remain one source. Pre-close snapshots may be
revised, but only observations whose own data timestamp reaches the session
close can become final candidates for later cross-source reconciliation.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FIELDS = ("open", "high", "low", "close", "volume")


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def _change_pct(old: float, new: float) -> float:
    return (new / old - 1.0) * 100.0


def audit_revisions(payload: dict[str, Any]) -> dict[str, Any]:
    evaluation_asof = _parse_time(payload["evaluation_asof"])
    session_close_at = _parse_time(payload["session_close_at"])
    if session_close_at > evaluation_asof:
        raise ValueError("future_session_not_allowed")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for raw in payload.get("observations", []):
        source_name = str(raw.get("source_name", "")).strip()
        source_url = str(raw.get("source_url", "")).strip()
        if not source_name:
            raise ValueError("source_name_required")
        if not source_url.startswith("https://"):
            raise ValueError("https_source_url_required")
        retrieved_at = _parse_time(raw["retrieved_at"])
        source_data_asof = _parse_time(raw["source_data_asof"])
        if retrieved_at > evaluation_asof:
            raise ValueError("future_source_retrieval_not_allowed")
        if source_data_asof > retrieved_at:
            raise ValueError("source_data_asof_after_retrieval")

        values = {
            field: float(raw[field])
            for field in FIELDS
            if raw.get(field) is not None
        }
        if not values:
            raise ValueError("at_least_one_price_field_required")
        if any(value <= 0 for value in values.values()):
            raise ValueError("price_fields_must_be_positive")
        grouped.setdefault(source_url, []).append(
            {
                "source_name": source_name,
                "source_url": source_url,
                "retrieved_at": retrieved_at,
                "source_data_asof": source_data_asof,
                **values,
            }
        )

    revisions: list[dict[str, Any]] = []
    final_candidates: list[dict[str, Any]] = []
    for source_url, observations in sorted(grouped.items()):
        observations.sort(key=lambda item: (item["retrieved_at"], item["source_data_asof"]))
        for old, new in zip(observations, observations[1:]):
            changes = {
                field: {
                    "old": old[field],
                    "new": new[field],
                    "change_pct": _change_pct(old[field], new[field]),
                }
                for field in FIELDS
                if field in old and field in new and old[field] != new[field]
            }
            if changes:
                revisions.append(
                    {
                        "source_name": new["source_name"],
                        "source_url": source_url,
                        "old_source_data_asof": old["source_data_asof"].isoformat(),
                        "new_source_data_asof": new["source_data_asof"].isoformat(),
                        "old_was_pre_close": old["source_data_asof"] < session_close_at,
                        "changes": changes,
                    }
                )

        eligible = [
            item for item in observations if item["source_data_asof"] >= session_close_at
        ]
        if eligible:
            latest = eligible[-1]
            final_candidates.append(
                {
                    key: (value.isoformat() if isinstance(value, datetime) else value)
                    for key, value in latest.items()
                }
            )

    return {
        "ticker": str(payload["ticker"]).upper(),
        "session_close_at": session_close_at.isoformat(),
        "evaluation_asof": evaluation_asof.isoformat(),
        "unique_source_count": len(grouped),
        "revision_count": len(revisions),
        "revisions": revisions,
        "final_candidate_count": len(final_candidates),
        "final_candidates": final_candidates,
        "status": (
            "FINAL_SOURCE_SNAPSHOT_AVAILABLE"
            if final_candidates
            else "NO_FINAL_SOURCE_SNAPSHOT"
        ),
        "cross_source_verification_required": True,
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    result = audit_revisions(json.loads(args.input.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
