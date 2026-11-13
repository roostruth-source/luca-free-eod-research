"""Normalize financing terms without assuming every term follows stock splits.

Research only.  Contractual price floors can explicitly remain unchanged after
reverse splits, while share counts and exercise prices often adjust.  Treating
all numeric terms like market prices can create very large false dilution
estimates.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERM_TYPES = {"PRICE_TERM", "SHARE_COUNT"}
SPLIT_CONTRACTS = {"ADJUSTS", "DOES_NOT_ADJUST", "UNKNOWN"}


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def normalize_financing_terms(payload: dict[str, Any]) -> dict[str, Any]:
    evaluation_asof = _parse_time(payload["evaluation_asof"])
    reference_at = _parse_time(payload["reference_at"])
    if reference_at > evaluation_asof:
        raise ValueError("future_reference_not_allowed")

    actions: list[dict[str, Any]] = []
    previous_effective_at: datetime | None = None
    action_ids: set[str] = set()
    for raw in payload.get("reverse_splits", []):
        action_id = str(raw.get("action_id", "")).strip()
        if not action_id:
            raise ValueError("action_id_required")
        if action_id in action_ids:
            raise ValueError("duplicate_action_id")
        action_ids.add(action_id)
        effective_at = _parse_time(raw["effective_at"])
        evidence_at = _parse_time(raw["evidence_available_at"])
        if previous_effective_at is not None and effective_at <= previous_effective_at:
            raise ValueError("reverse_splits_not_strictly_ordered")
        previous_effective_at = effective_at
        if effective_at > reference_at:
            raise ValueError("post_reference_split_not_allowed")
        if evidence_at > reference_at or evidence_at > evaluation_asof:
            raise ValueError("future_split_evidence_not_allowed")
        source_url = str(raw.get("source_url", ""))
        if not source_url.startswith("https://"):
            raise ValueError("https_split_source_required")
        factor = float(raw["shares_before_per_after"])
        if factor <= 1:
            raise ValueError("reverse_split_factor_must_exceed_one")
        actions.append(
            {
                "action_id": action_id,
                "effective_at": effective_at,
                "evidence_available_at": evidence_at,
                "shares_before_per_after": factor,
                "source_url": source_url,
            }
        )

    normalized: list[dict[str, Any]] = []
    for raw in payload.get("terms", []):
        observed_at = _parse_time(raw["observed_at"])
        evidence_at = _parse_time(raw["evidence_available_at"])
        if observed_at > reference_at:
            raise ValueError("term_after_reference_not_allowed")
        if evidence_at > reference_at or evidence_at > evaluation_asof:
            raise ValueError("future_term_evidence_not_allowed")
        source_url = str(raw.get("source_url", ""))
        if not source_url.startswith("https://"):
            raise ValueError("https_term_source_required")
        term_type = str(raw.get("term_type", ""))
        if term_type not in TERM_TYPES:
            raise ValueError("unsupported_term_type")
        contract = str(raw.get("split_adjustment_contract", "UNKNOWN"))
        if contract not in SPLIT_CONTRACTS:
            raise ValueError("unsupported_split_adjustment_contract")
        value = float(raw["value"])
        if value <= 0:
            raise ValueError("term_value_must_be_positive")

        applicable = [a for a in actions if observed_at < a["effective_at"] <= reference_at]
        cumulative_factor = 1.0
        for action in applicable:
            cumulative_factor *= action["shares_before_per_after"]

        naive_mechanical_value = (
            value * cumulative_factor
            if term_type == "PRICE_TERM"
            else value / cumulative_factor
        )
        block_reasons: list[str] = []
        normalized_value: float | None
        if contract == "UNKNOWN":
            normalized_value = None
            block_reasons.append("SPLIT_ADJUSTMENT_CONTRACT_UNKNOWN")
        elif contract == "DOES_NOT_ADJUST":
            normalized_value = value
        else:
            normalized_value = naive_mechanical_value

        comparison = raw.get("official_comparison_value")
        comparison_difference_pct: float | None = None
        if comparison is not None:
            comparison = float(comparison)
            if comparison <= 0:
                raise ValueError("comparison_value_must_be_positive")
            comparison_source = str(raw.get("official_comparison_source_url", ""))
            comparison_evidence_raw = raw.get("official_comparison_evidence_available_at")
            if not comparison_source.startswith("https://"):
                raise ValueError("https_comparison_source_required")
            if not comparison_evidence_raw:
                raise ValueError("comparison_evidence_available_at_required")
            comparison_evidence_at = _parse_time(str(comparison_evidence_raw))
            if comparison_evidence_at > reference_at or comparison_evidence_at > evaluation_asof:
                raise ValueError("future_comparison_evidence_not_allowed")
            if normalized_value is not None:
                comparison_difference_pct = round(
                    (comparison - normalized_value) / normalized_value * 100.0, 8
                )
                tolerance_pct = float(raw.get("comparison_tolerance_pct", 0.01))
                if abs(comparison_difference_pct) > tolerance_pct:
                    block_reasons.append("TERM_BASIS_CONFLICT")

        normalized.append(
            {
                "term_id": str(raw["term_id"]),
                "instrument_type": str(raw["instrument_type"]),
                "term_type": term_type,
                "observed_at": observed_at.isoformat(),
                "raw_value": value,
                "split_adjustment_contract": contract,
                "applicable_split_ids": [a["action_id"] for a in applicable],
                "cumulative_split_factor": cumulative_factor,
                "naive_mechanical_value": naive_mechanical_value,
                "normalized_value": normalized_value,
                "official_comparison_value": comparison,
                "comparison_difference_pct": comparison_difference_pct,
                "block_reasons": block_reasons,
                "source_url": source_url,
                "evidence_available_at": evidence_at.isoformat(),
            }
        )

    return {
        "evaluation_asof": evaluation_asof.isoformat(),
        "reference_at": reference_at.isoformat(),
        "reverse_split_count": len(actions),
        "normalized_terms": normalized,
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input_json.read_text())
    print(json.dumps(normalize_financing_terms(payload), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
