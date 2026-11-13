"""Reconcile point-in-time outstanding-share checkpoints across reverse splits.

The observation date and the evidence-available timestamp are deliberately
separate.  A historical signal may use a checkpoint only after the filing
that disclosed it became public.  Changes are net outstanding-share changes,
not gross issuance, because cancellations and fractional-share treatment can
also affect the total.
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


def _validate_source_url(value: str, error: str) -> None:
    if not value.startswith("https://www.sec.gov/"):
        raise ValueError(error)


def reconcile_os_timeline(payload: dict[str, Any]) -> dict[str, Any]:
    evaluation_asof = _time(payload["evaluation_asof"])
    reference_at = _time(payload["reference_at"])
    if reference_at > evaluation_asof:
        raise ValueError("future_reference_not_allowed")

    checkpoints = payload.get("checkpoints", [])
    if len(checkpoints) < 2:
        raise ValueError("at_least_two_checkpoints_required")

    ids: set[str] = set()
    previous_date: date | None = None
    for checkpoint in checkpoints:
        checkpoint_id = str(checkpoint.get("checkpoint_id", ""))
        if not checkpoint_id:
            raise ValueError("checkpoint_id_required")
        if checkpoint_id in ids:
            raise ValueError("duplicate_checkpoint_id")
        ids.add(checkpoint_id)
        observed = _date(checkpoint["observation_date"])
        if previous_date is not None and observed <= previous_date:
            raise ValueError("checkpoints_not_strictly_ordered")
        previous_date = observed
        evidence_at = _time(checkpoint["evidence_available_at"])
        if evidence_at > reference_at:
            raise ValueError("future_checkpoint_evidence_not_allowed")
        if evidence_at.date() < observed:
            raise ValueError("evidence_precedes_observation")
        if float(checkpoint["shares_outstanding"]) <= 0:
            raise ValueError("shares_outstanding_must_be_positive")
        _validate_source_url(
            str(checkpoint.get("source_url", "")),
            "official_sec_checkpoint_source_required",
        )

    reverse_splits = payload.get("reverse_splits", [])
    previous_effective: datetime | None = None
    for split in reverse_splits:
        effective_at = _time(split["effective_at"])
        evidence_at = _time(split["evidence_available_at"])
        if previous_effective is not None and effective_at <= previous_effective:
            raise ValueError("reverse_splits_not_strictly_ordered")
        previous_effective = effective_at
        if evidence_at > reference_at:
            raise ValueError("future_split_evidence_not_allowed")
        if float(split["shares_before_per_after"]) <= 1:
            raise ValueError("reverse_split_factor_must_exceed_one")
        _validate_source_url(
            str(split.get("source_url", "")),
            "official_sec_split_source_required",
        )

    rapid_threshold = float(payload.get("rapid_expansion_threshold_pct", 25.0))
    if rapid_threshold <= 0:
        raise ValueError("rapid_expansion_threshold_must_be_positive")

    intervals: list[dict[str, Any]] = []
    overall_reasons: list[str] = []
    for before, after in zip(checkpoints, checkpoints[1:]):
        before_date = _date(before["observation_date"])
        after_date = _date(after["observation_date"])
        factor = 1.0
        split_ids: list[str] = []
        evidence_times = [_time(after["evidence_available_at"])]
        for split in reverse_splits:
            effective_at = _time(split["effective_at"])
            if before_date < effective_at.date() <= after_date:
                factor *= float(split["shares_before_per_after"])
                split_ids.append(str(split["action_id"]))
                evidence_times.append(_time(split["evidence_available_at"]))

        before_shares = float(before["shares_outstanding"])
        after_shares = float(after["shares_outstanding"])
        before_on_after_basis = before_shares / factor
        net_change = after_shares - before_on_after_basis
        net_change_pct = net_change / before_on_after_basis * 100.0
        multiple = after_shares / before_on_after_basis
        reasons: list[str] = []
        if net_change_pct >= rapid_threshold:
            reasons.append("RAPID_OS_EXPANSION")
        if multiple >= 2.0:
            reasons.append("OS_MORE_THAN_DOUBLED")
        for reason in reasons:
            if reason not in overall_reasons:
                overall_reasons.append(reason)

        usable_from = max(evidence_times)
        intervals.append(
            {
                "from_checkpoint_id": before["checkpoint_id"],
                "to_checkpoint_id": after["checkpoint_id"],
                "from_observation_date": before["observation_date"],
                "to_observation_date": after["observation_date"],
                "applied_split_ids": split_ids,
                "cumulative_split_factor": factor,
                "from_shares_reported": before_shares,
                "from_shares_on_to_basis": round(before_on_after_basis, 8),
                "to_shares_reported": after_shares,
                "net_os_change": round(net_change, 8),
                "net_os_change_pct": round(net_change_pct, 8),
                "os_multiple": round(multiple, 8),
                "usable_for_signals_from": usable_from.isoformat(),
                "reasons": reasons,
                "not_gross_issuance": True,
            }
        )

    return {
        "evaluation_asof": evaluation_asof.isoformat(),
        "reference_at": reference_at.isoformat(),
        "ticker": payload["ticker"],
        "rapid_expansion_threshold_pct": rapid_threshold,
        "threshold_status": "RESEARCH_SAFETY_GATE_NOT_PERFORMANCE_OPTIMIZED",
        "intervals": intervals,
        "block_reasons": overall_reasons,
        "point_in_time_rule": (
            "checkpoint_unusable_before_its_evidence_available_at"
        ),
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input_json.read_text())
    print(json.dumps(reconcile_os_timeline(payload), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
