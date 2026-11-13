"""Reconcile financing-program share counts across restated split bases.

The same filing can move shares between ATM, ELOC, conversion, and other
captions.  Component counts are not interchangeable with the aggregate.  This
module preserves both and refuses to call a component conflict when coverage
periods or classification scopes differ.
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


def _validate_snapshot(snapshot: dict[str, Any], reference_at: datetime) -> None:
    evidence_at = _time(snapshot["evidence_available_at"])
    basis_at = _time(snapshot["split_basis_effective_through"])
    if evidence_at > reference_at:
        raise ValueError("future_snapshot_evidence_not_allowed")
    if basis_at > reference_at:
        raise ValueError("future_split_basis_not_allowed")
    if not str(snapshot.get("source_url", "")).startswith("https://"):
        raise ValueError("https_snapshot_source_required")
    ids: set[str] = set()
    for component in snapshot.get("components", []):
        component_id = str(component.get("component_id", ""))
        if not component_id:
            raise ValueError("component_id_required")
        if component_id in ids:
            raise ValueError("duplicate_component_id")
        ids.add(component_id)
        if float(component["share_count"]) <= 0:
            raise ValueError("share_count_must_be_positive")
        if _date(component["coverage_start"]) > _date(component["coverage_end"]):
            raise ValueError("invalid_component_coverage")


def reconcile_supply_bundles(payload: dict[str, Any]) -> dict[str, Any]:
    evaluation_asof = _time(payload["evaluation_asof"])
    reference_at = _time(payload["reference_at"])
    if reference_at > evaluation_asof:
        raise ValueError("future_reference_not_allowed")

    before = payload["before_snapshot"]
    after = payload["after_snapshot"]
    if before["bundle_id"] != after["bundle_id"]:
        raise ValueError("bundle_id_mismatch")
    _validate_snapshot(before, reference_at)
    _validate_snapshot(after, reference_at)
    before_basis = _time(before["split_basis_effective_through"])
    after_basis = _time(after["split_basis_effective_through"])
    if after_basis < before_basis:
        raise ValueError("after_basis_precedes_before_basis")

    factor = 1.0
    applied_splits: list[str] = []
    previous_effective: datetime | None = None
    for split in payload.get("reverse_splits", []):
        effective_at = _time(split["effective_at"])
        evidence_at = _time(split["evidence_available_at"])
        if previous_effective is not None and effective_at <= previous_effective:
            raise ValueError("reverse_splits_not_strictly_ordered")
        previous_effective = effective_at
        if evidence_at > reference_at:
            raise ValueError("future_split_evidence_not_allowed")
        if not str(split.get("source_url", "")).startswith("https://"):
            raise ValueError("https_split_source_required")
        if before_basis < effective_at <= after_basis:
            split_factor = float(split["shares_before_per_after"])
            if split_factor <= 1:
                raise ValueError("reverse_split_factor_must_exceed_one")
            factor *= split_factor
            applied_splits.append(str(split["action_id"]))

    tolerance_pct = float(payload.get("tolerance_pct", 0.01))
    before_by_id = {c["component_id"]: c for c in before["components"]}
    after_by_id = {c["component_id"]: c for c in after["components"]}
    all_ids = sorted(set(before_by_id) | set(after_by_id))
    components: list[dict[str, Any]] = []
    component_conflicts: list[str] = []
    scope_mismatches: list[str] = []
    for component_id in all_ids:
        old = before_by_id.get(component_id)
        new = after_by_id.get(component_id)
        if old is None or new is None:
            scope_mismatches.append(component_id)
            components.append(
                {
                    "component_id": component_id,
                    "scope_comparable": False,
                    "reason": "COMPONENT_MISSING_FROM_ONE_SNAPSHOT",
                }
            )
            continue
        scope_comparable = (
            old["coverage_start"] == new["coverage_start"]
            and old["coverage_end"] == new["coverage_end"]
            and old.get("scope_label") == new.get("scope_label")
        )
        adjusted_old = float(old["share_count"]) / factor
        new_value = float(new["share_count"])
        difference = new_value - adjusted_old
        difference_pct = difference / adjusted_old * 100.0
        reasons: list[str] = []
        if not scope_comparable:
            reasons.append("COMPONENT_SCOPE_MISMATCH")
            scope_mismatches.append(component_id)
        elif abs(difference_pct) > tolerance_pct:
            reasons.append("COMPONENT_BASIS_CONFLICT")
            component_conflicts.append(component_id)
        components.append(
            {
                "component_id": component_id,
                "scope_comparable": scope_comparable,
                "before_share_count": float(old["share_count"]),
                "mechanical_adjusted_before": adjusted_old,
                "after_share_count": new_value,
                "difference": round(difference, 8),
                "difference_pct": round(difference_pct, 8),
                "reasons": reasons,
            }
        )

    before_total = sum(float(c["share_count"]) for c in before["components"]) / factor
    after_total = sum(float(c["share_count"]) for c in after["components"])
    aggregate_difference = after_total - before_total
    aggregate_difference_pct = aggregate_difference / before_total * 100.0
    aggregate_close = abs(aggregate_difference_pct) <= tolerance_pct

    block_reasons: list[str] = []
    if scope_mismatches:
        block_reasons.append("BUNDLE_SCOPE_NOT_COMPARABLE")
    if component_conflicts:
        block_reasons.append("COMPONENT_BASIS_CONFLICT")
    classification_shift_possible = bool(
        aggregate_close and (component_conflicts or scope_mismatches)
    )
    if classification_shift_possible:
        block_reasons.append("COMPONENT_CLASSIFICATION_SHIFT_POSSIBLE")

    return {
        "evaluation_asof": evaluation_asof.isoformat(),
        "reference_at": reference_at.isoformat(),
        "bundle_id": before["bundle_id"],
        "applied_split_ids": applied_splits,
        "cumulative_split_factor": factor,
        "components": components,
        "aggregate_diagnostic": {
            "mechanical_adjusted_before_total": before_total,
            "after_total": after_total,
            "difference": round(aggregate_difference, 8),
            "difference_pct": round(aggregate_difference_pct, 8),
            "within_tolerance": aggregate_close,
            "classification_shift_possible": classification_shift_possible,
            "not_a_settled_supply_ledger": bool(block_reasons),
        },
        "block_reasons": block_reasons,
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input_json.read_text())
    print(json.dumps(reconcile_supply_bundles(payload), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
