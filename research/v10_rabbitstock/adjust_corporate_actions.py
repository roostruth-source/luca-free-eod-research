"""Adjust historical values through verified corporate-action chains.

Research only. Corporate actions filed after the frozen reference time are
rejected so later knowledge cannot leak into an earlier signal evaluation.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


METRIC_TYPES = {"PRICE", "SHARE_COUNT"}
ACTION_TYPES = {"REVERSE_SPLIT", "TICKER_CHANGE"}


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def adjust_corporate_actions(payload: dict[str, Any]) -> dict[str, Any]:
    evaluation_asof = _parse_time(payload["evaluation_asof"])
    reference_at = _parse_time(payload["reference_at"])
    if reference_at > evaluation_asof:
        raise ValueError("future_reference_not_allowed")

    reference_ticker = str(payload["reference_ticker"]).upper()
    actions: list[dict[str, Any]] = []
    previous_effective_at: datetime | None = None
    action_ids: set[str] = set()

    for raw in payload.get("actions", []):
        action_id = str(raw.get("action_id", "")).strip()
        if not action_id:
            raise ValueError("action_id_required")
        if action_id in action_ids:
            raise ValueError("duplicate_action_id")
        action_ids.add(action_id)

        action_type = str(raw.get("action_type", ""))
        if action_type not in ACTION_TYPES:
            raise ValueError("unsupported_action_type")
        effective_at = _parse_time(raw["effective_at"])
        evidence_available_at = _parse_time(raw["evidence_available_at"])
        if evidence_available_at > evaluation_asof:
            raise ValueError("future_action_evidence_not_allowed")
        if evidence_available_at > reference_at:
            raise ValueError("post_reference_action_evidence_not_allowed")
        if effective_at > reference_at:
            raise ValueError("post_reference_action_not_allowed")
        if previous_effective_at is not None and effective_at <= previous_effective_at:
            raise ValueError("actions_not_strictly_ordered")
        previous_effective_at = effective_at

        source_url = str(raw.get("source_url", ""))
        if not source_url.startswith("https://"):
            raise ValueError("https_source_url_required")

        action: dict[str, Any] = {
            "action_id": action_id,
            "action_type": action_type,
            "effective_at": effective_at,
            "evidence_available_at": evidence_available_at,
            "source_url": source_url,
        }
        if action_type == "REVERSE_SPLIT":
            factor = float(raw["shares_before_per_after"])
            if factor <= 1:
                raise ValueError("reverse_split_factor_must_exceed_one")
            action.update(
                {
                    "ticker": str(raw["ticker"]).upper(),
                    "shares_before_per_after": factor,
                }
            )
        else:
            if not bool(raw.get("same_security", False)):
                raise ValueError("ticker_change_same_security_required")
            action.update(
                {
                    "from_ticker": str(raw["from_ticker"]).upper(),
                    "to_ticker": str(raw["to_ticker"]).upper(),
                    "same_security": True,
                }
            )
        actions.append(action)

    adjusted: list[dict[str, Any]] = []
    for raw in payload.get("observations", []):
        observed_at = _parse_time(raw["observed_at"])
        if observed_at > reference_at:
            raise ValueError("observation_after_reference_not_allowed")
        legacy_basis_raw = raw.get("basis_effective_through")
        split_basis_raw = raw.get("split_basis_effective_through")
        if legacy_basis_raw and split_basis_raw:
            if _parse_time(legacy_basis_raw) != _parse_time(split_basis_raw):
                raise ValueError("conflicting_split_basis_fields")
        selected_basis_raw = split_basis_raw or legacy_basis_raw
        split_basis_effective_through = (
            _parse_time(selected_basis_raw) if selected_basis_raw else observed_at
        )
        if split_basis_effective_through < observed_at:
            raise ValueError("basis_before_observation_not_allowed")
        if split_basis_effective_through > reference_at:
            raise ValueError("future_basis_not_allowed")

        split_basis_provenance: dict[str, str] | None = None
        if split_basis_effective_through > observed_at:
            scope = str(raw.get("split_basis_scope", ""))
            if scope != "RETROACTIVE_SPLIT_ADJUSTED":
                raise ValueError("split_basis_scope_required")
            source_url = str(raw.get("split_basis_source_url", ""))
            if not source_url.startswith("https://"):
                raise ValueError("split_basis_https_source_required")
            evidence_raw = raw.get("split_basis_evidence_available_at")
            if not evidence_raw:
                raise ValueError("split_basis_evidence_available_at_required")
            evidence_available_at = _parse_time(str(evidence_raw))
            if evidence_available_at > evaluation_asof:
                raise ValueError("future_split_basis_evidence_not_allowed")
            if evidence_available_at > reference_at:
                raise ValueError("post_reference_split_basis_evidence_not_allowed")
            verified_split_times = {
                action["effective_at"]
                for action in actions
                if action["action_type"] == "REVERSE_SPLIT"
            }
            if split_basis_effective_through not in verified_split_times:
                raise ValueError("split_basis_action_not_found")
            split_basis_provenance = {
                "scope": scope,
                "source_url": source_url,
                "evidence_available_at": evidence_available_at.isoformat(),
            }
        metric_type = str(raw["metric_type"])
        if metric_type not in METRIC_TYPES:
            raise ValueError("unsupported_metric_type")
        value = float(raw["value"])
        if value <= 0:
            raise ValueError("observation_value_must_be_positive")

        current_ticker = str(raw["ticker"]).upper()
        factor = 1.0
        applied: list[str] = []
        for action in actions:
            if action["action_type"] == "REVERSE_SPLIT":
                if not (
                    split_basis_effective_through
                    < action["effective_at"]
                    <= reference_at
                ):
                    continue
                if current_ticker == action["ticker"]:
                    factor *= action["shares_before_per_after"]
                    applied.append(action["action_id"])
            elif not (observed_at < action["effective_at"] <= reference_at):
                continue
            elif current_ticker == action["from_ticker"]:
                current_ticker = action["to_ticker"]
                applied.append(action["action_id"])

        if current_ticker != reference_ticker:
            raise ValueError("ticker_lineage_not_resolved")
        mechanical_adjusted_value = (
            value * factor if metric_type == "PRICE" else value / factor
        )
        adjusted_value = mechanical_adjusted_value
        official_restatement = None
        restatement_difference = None
        restatement_difference_pct = None
        if raw.get("official_restated_value") is not None:
            if metric_type != "SHARE_COUNT":
                raise ValueError("official_restatement_share_count_only")
            official_value = float(raw["official_restated_value"])
            if official_value <= 0:
                raise ValueError("official_restatement_value_must_be_positive")
            restatement_scope = str(raw.get("official_restatement_scope", ""))
            if restatement_scope != "OFFICIAL_POST_SPLIT_RESTATEMENT":
                raise ValueError("official_restatement_scope_required")
            restatement_source_url = str(
                raw.get("official_restatement_source_url", "")
            )
            if not restatement_source_url.startswith("https://"):
                raise ValueError("official_restatement_https_source_required")
            restatement_evidence_raw = raw.get(
                "official_restatement_evidence_available_at"
            )
            if not restatement_evidence_raw:
                raise ValueError("official_restatement_evidence_at_required")
            restatement_evidence_at = _parse_time(str(restatement_evidence_raw))
            if restatement_evidence_at > evaluation_asof:
                raise ValueError("future_official_restatement_evidence_not_allowed")
            if restatement_evidence_at > reference_at:
                raise ValueError("post_reference_official_restatement_not_allowed")
            restatement_basis_raw = raw.get(
                "official_restatement_basis_effective_through"
            )
            if not restatement_basis_raw:
                raise ValueError("official_restatement_basis_required")
            restatement_basis = _parse_time(str(restatement_basis_raw))
            verified_split_times = [
                action["effective_at"]
                for action in actions
                if action["action_type"] == "REVERSE_SPLIT"
                and action["effective_at"] <= reference_at
            ]
            latest_verified_split = max(verified_split_times, default=None)
            if restatement_basis != latest_verified_split:
                raise ValueError("official_restatement_latest_split_required")
            restatement_difference = round(
                official_value - mechanical_adjusted_value, 8
            )
            restatement_difference_pct = round(
                restatement_difference / mechanical_adjusted_value * 100.0, 8
            )
            adjusted_value = official_value
            official_restatement = {
                "scope": restatement_scope,
                "value": official_value,
                "basis_effective_through": restatement_basis.isoformat(),
                "source_url": restatement_source_url,
                "evidence_available_at": restatement_evidence_at.isoformat(),
            }
        adjusted.append(
            {
                "observation_id": str(raw["observation_id"]),
                "metric_type": metric_type,
                "original_ticker": str(raw["ticker"]).upper(),
                "reference_ticker": reference_ticker,
                "observed_at": observed_at.isoformat(),
                "basis_effective_through": split_basis_effective_through.isoformat(),
                "split_basis_effective_through": (
                    split_basis_effective_through.isoformat()
                ),
                "split_basis_provenance": split_basis_provenance,
                "raw_value": value,
                "cumulative_split_factor": factor,
                "mechanical_adjusted_value": mechanical_adjusted_value,
                "adjusted_value": adjusted_value,
                "official_restatement": official_restatement,
                "restatement_difference": restatement_difference,
                "restatement_difference_pct": restatement_difference_pct,
                "applied_action_ids": applied,
            }
        )

    return {
        "evaluation_asof": evaluation_asof.isoformat(),
        "reference_at": reference_at.isoformat(),
        "reference_ticker": reference_ticker,
        "actions_count": len(actions),
        "adjusted_observations": adjusted,
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = adjust_corporate_actions(json.loads(args.input.read_text(encoding="utf-8")))
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
