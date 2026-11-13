"""LUCA V10 RabbitStock snapshot evaluator.

Research-only gate. It never places or prepares orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


ENGINES = ("preview", "signal", "hidden_pick", "best", "burning_up")
DILUTION_FLAGS = ("atm", "eloc", "toxic_financing", "cb", "warrant", "shelf")
SUPPLY_CHECKS = (
    "atm",
    "eloc",
    "toxic_financing",
    "cb",
    "warrant",
    "lockup",
    "reverse_split",
    "shelf",
)
SUPPLY_STATES = {"CLEAR", "PRESENT", "UNKNOWN"}
FLOAT_MISMATCH_TOLERANCE = 0.02
HIGH_DILUTION_MULTIPLE = 2.0
SIGNIFICANT_DILUTION_PCT = 25.0
EXTREME_SPLIT_FACTOR = 250.0
EXCHANGE_STATUSES = {"TRADING", "SUSPENDED", "DELISTED", "OTC", "UNKNOWN"}


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def evaluate_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    """Evaluate one frozen snapshot without using later information."""

    snapshot_at = _parse_time(payload["snapshot_at"])
    data_asof = _parse_time(payload["data_asof"])
    if data_asof > snapshot_at:
        raise ValueError("future_data_not_allowed")

    source_type = payload.get("source_type")
    if source_type not in {"RABBITSTOCK_AUTHORIZED_SCREEN", "COMPLETED_DAILY_BARS"}:
        raise ValueError("unsupported_source_type")

    exchange_status_record = payload.get("exchange_status")
    exchange_status = "UNKNOWN"
    exchange_status_effective_at = None
    exchange_status_evidence_at = None
    exchange_status_source_url = None
    if exchange_status_record is not None:
        if not isinstance(exchange_status_record, dict):
            raise ValueError("exchange_status_object_required")
        exchange_status = str(exchange_status_record.get("status", "UNKNOWN")).upper()
        if exchange_status not in EXCHANGE_STATUSES:
            raise ValueError("invalid_exchange_status")
        if exchange_status != "UNKNOWN":
            effective_raw = exchange_status_record.get("effective_at")
            evidence_raw = exchange_status_record.get("evidence_available_at")
            if not effective_raw:
                raise ValueError("exchange_status_effective_at_required")
            if not evidence_raw:
                raise ValueError("exchange_status_evidence_at_required")
            exchange_status_effective_at = _parse_time(str(effective_raw))
            exchange_status_evidence_at = _parse_time(str(evidence_raw))
            if exchange_status_evidence_at > snapshot_at:
                raise ValueError("future_exchange_status_evidence_not_allowed")
            exchange_status_source_url = str(
                exchange_status_record.get("source_url", "")
            )
            if not exchange_status_source_url.startswith("https://"):
                raise ValueError("exchange_status_https_source_required")
            if exchange_status == "TRADING" and exchange_status_effective_at > snapshot_at:
                raise ValueError("future_trading_status_not_allowed")

    exchange_status_verified = exchange_status != "UNKNOWN"
    restricted_exchange_status = exchange_status in {
        "SUSPENDED",
        "DELISTED",
        "OTC",
    }
    exchange_restriction_active = bool(
        restricted_exchange_status
        and exchange_status_effective_at is not None
        and exchange_status_effective_at <= snapshot_at
    )
    exchange_restriction_pending = bool(
        restricted_exchange_status
        and exchange_status_effective_at is not None
        and exchange_status_effective_at > snapshot_at
    )

    engine_hits = payload.get("engine_hits", {})
    unknown = set(engine_hits) - set(ENGINES)
    if unknown:
        raise ValueError(f"unknown_engines:{','.join(sorted(unknown))}")

    targets: list[float] = []
    engine_floats: dict[str, float] = {}
    ranks: dict[str, int] = {}
    for engine, hit in engine_hits.items():
        if not isinstance(hit, dict) or int(hit["rank"]) < 1:
            raise ValueError(f"invalid_engine_hit:{engine}")
        ranks[engine] = int(hit["rank"])
        if hit.get("target") is not None:
            targets.append(float(hit["target"]))
        if hit.get("float") is not None:
            float_value = float(hit["float"])
            if float_value <= 0:
                raise ValueError(f"invalid_engine_float:{engine}")
            engine_floats[engine] = float_value

    entry = float(payload["entry"])
    if entry <= 0:
        raise ValueError("entry_must_be_positive")

    warnings = payload.get("warnings", {})
    screen_dilution_present = any(bool(warnings.get(flag, False)) for flag in DILUTION_FLAGS)

    official_supply_checks = payload.get("official_supply_checks", {})
    unknown_supply_checks: list[str] = []
    present_supply_checks: list[str] = []
    for check in SUPPLY_CHECKS:
        state = str(official_supply_checks.get(check, "UNKNOWN")).upper()
        if state not in SUPPLY_STATES:
            raise ValueError(f"invalid_supply_state:{check}")
        if state == "UNKNOWN":
            unknown_supply_checks.append(check)
        elif state == "PRESENT":
            present_supply_checks.append(check)

    supply_evidence_at = None
    if payload.get("supply_evidence_asof"):
        supply_evidence_at = _parse_time(payload["supply_evidence_asof"])
        if supply_evidence_at > snapshot_at:
            raise ValueError("future_supply_evidence_not_allowed")
    elif official_supply_checks:
        raise ValueError("supply_evidence_timestamp_required")

    supply_evidence_complete = not unknown_supply_checks and supply_evidence_at is not None
    official_dilution_present = any(
        check in present_supply_checks for check in DILUTION_FLAGS
    )
    screen_supply_unreconciled = [
        flag
        for flag in DILUTION_FLAGS
        if bool(warnings.get(flag, False))
        and str(official_supply_checks.get(flag, "UNKNOWN")).upper() != "PRESENT"
    ]
    dilution_present = screen_dilution_present or official_dilution_present
    float_ratio = None
    if len(engine_floats) >= 2:
        float_ratio = max(engine_floats.values()) / min(engine_floats.values())
    float_mismatch = bool(
        float_ratio is not None and float_ratio > 1.0 + FLOAT_MISMATCH_TOLERANCE
    )
    split_factors = [float(value) for value in payload.get("reverse_split_factors", [])]
    if any(factor <= 1.0 for factor in split_factors):
        raise ValueError("invalid_reverse_split_factor")
    cumulative_reverse_split_factor = 1.0
    for factor in split_factors:
        cumulative_reverse_split_factor *= factor
    serial_reverse_split_extreme = bool(
        len(split_factors) >= 2
        and cumulative_reverse_split_factor >= EXTREME_SPLIT_FACTOR
    )
    float_mismatch_matches_split_factor = bool(
        float_mismatch
        and any(abs(float_ratio - factor) / factor <= FLOAT_MISMATCH_TOLERANCE for factor in split_factors)
    )
    float_basis_reconciled = bool(payload.get("float_basis_reconciled", False))

    official_os_baseline = payload.get("official_os_baseline")
    official_fully_diluted_shares = payload.get("official_fully_diluted_shares")
    if (official_os_baseline is None) != (official_fully_diluted_shares is None):
        raise ValueError("dilution_share_pair_required")
    fully_diluted_multiple = None
    if official_os_baseline is not None:
        official_os_baseline = float(official_os_baseline)
        official_fully_diluted_shares = float(official_fully_diluted_shares)
        if official_os_baseline <= 0 or official_fully_diluted_shares < official_os_baseline:
            raise ValueError("invalid_dilution_share_counts")
        fully_diluted_multiple = official_fully_diluted_shares / official_os_baseline
    high_dilution_multiple = bool(
        fully_diluted_multiple is not None
        and fully_diluted_multiple >= HIGH_DILUTION_MULTIPLE
    )
    potential_dilution_pct = None
    if fully_diluted_multiple is not None:
        potential_dilution_pct = (fully_diluted_multiple - 1.0) * 100.0
    significant_potential_dilution = bool(
        potential_dilution_pct is not None
        and potential_dilution_pct >= SIGNIFICANT_DILUTION_PCT
    )

    prefunded_warrants_unexercised_estimate = payload.get(
        "prefunded_warrants_unexercised_estimate"
    )
    if prefunded_warrants_unexercised_estimate is not None:
        prefunded_warrants_unexercised_estimate = float(
            prefunded_warrants_unexercised_estimate
        )
        if prefunded_warrants_unexercised_estimate < 0:
            raise ValueError("invalid_prefunded_warrant_estimate")
        if official_os_baseline is None:
            raise ValueError("prefunded_warrant_os_baseline_required")
    prefunded_share_equivalent = bool(
        prefunded_warrants_unexercised_estimate is not None
        and prefunded_warrants_unexercised_estimate > 0
    )
    economic_share_count = None
    economic_share_uplift_pct = None
    if prefunded_share_equivalent:
        economic_share_count = (
            official_os_baseline + prefunded_warrants_unexercised_estimate
        )
        economic_share_uplift_pct = (
            prefunded_warrants_unexercised_estimate / official_os_baseline * 100.0
        )

    scope_partial = bool(payload.get("scope_partial", False))

    block_reasons: list[str] = []
    if not exchange_status_verified:
        block_reasons.append("TRADING_STATUS_UNVERIFIED")
    elif exchange_restriction_active:
        block_reasons.append("TRADING_UNAVAILABLE")
    elif exchange_restriction_pending:
        block_reasons.append("TRADING_RESTRICTION_PENDING")
    if not bool(payload.get("split_basis_verified", False)):
        block_reasons.append("SPLIT_BASIS_UNVERIFIED")
    if bool(warnings.get("reverse_split", False)):
        block_reasons.append("SCREEN_REVERSE_SPLIT_WARNING")
    if bool(warnings.get("dilution_unit_mismatch", False)):
        block_reasons.append("DILUTION_UNIT_MISMATCH")
    if not bool(payload.get("float_verified", False)):
        block_reasons.append("FLOAT_UNVERIFIED")
    if float_mismatch and not float_basis_reconciled:
        block_reasons.append("CROSS_ENGINE_FLOAT_MISMATCH")
    if scope_partial:
        block_reasons.append("SCOPE_PARTIAL")
    if not supply_evidence_complete:
        block_reasons.append("SUPPLY_EVIDENCE_INCOMPLETE")
    if high_dilution_multiple:
        block_reasons.append("HIGH_FULLY_DILUTED_MULTIPLE")
    if significant_potential_dilution:
        block_reasons.append("SIGNIFICANT_POTENTIAL_DILUTION")
    if serial_reverse_split_extreme:
        block_reasons.append("SERIAL_REVERSE_SPLIT_EXTREME")
    if prefunded_share_equivalent:
        block_reasons.append("PREFUNDED_WARRANT_SHARE_EQUIVALENT")
    if screen_supply_unreconciled:
        block_reasons.append("SCREEN_SUPPLY_LABEL_UNRECONCILED")

    engine_count = len(ranks)
    target_median = median(targets) if targets else None
    target_range = [min(targets), max(targets)] if targets else None
    upside = None if target_median is None else (target_median / entry - 1.0) * 100.0

    if block_reasons:
        state = "WATCH_ONLY_BLOCKED"
    elif engine_count >= 3 and not dilution_present:
        state = "WATCH_ONLY_STRONG"
    elif engine_count >= 2:
        state = "WATCH_ONLY"
    else:
        state = "OBSERVE_ONLY"

    return {
        "ticker": str(payload["ticker"]).upper(),
        "snapshot_at": snapshot_at.isoformat(),
        "data_asof": data_asof.isoformat(),
        "source_type": source_type,
        "exchange_status": exchange_status,
        "exchange_status_verified": exchange_status_verified,
        "exchange_status_effective_at": (
            None
            if exchange_status_effective_at is None
            else exchange_status_effective_at.isoformat()
        ),
        "exchange_status_evidence_at": (
            None
            if exchange_status_evidence_at is None
            else exchange_status_evidence_at.isoformat()
        ),
        "exchange_status_source_url": exchange_status_source_url,
        "exchange_restriction_active": exchange_restriction_active,
        "exchange_restriction_pending": exchange_restriction_pending,
        "engine_count": engine_count,
        "engine_ranks": ranks,
        "engine_floats": engine_floats,
        "cross_engine_float_mismatch": float_mismatch,
        "float_ratio": float_ratio,
        "float_mismatch_matches_split_factor": float_mismatch_matches_split_factor,
        "float_basis_reconciled": float_basis_reconciled,
        "reverse_split_factors": split_factors,
        "cumulative_reverse_split_factor": cumulative_reverse_split_factor,
        "serial_reverse_split_extreme": serial_reverse_split_extreme,
        "official_os_baseline": official_os_baseline,
        "official_fully_diluted_shares": official_fully_diluted_shares,
        "fully_diluted_multiple": fully_diluted_multiple,
        "potential_dilution_pct": potential_dilution_pct,
        "significant_potential_dilution": significant_potential_dilution,
        "high_dilution_multiple": high_dilution_multiple,
        "prefunded_warrants_unexercised_estimate": prefunded_warrants_unexercised_estimate,
        "prefunded_share_equivalent": prefunded_share_equivalent,
        "economic_share_count": economic_share_count,
        "economic_share_uplift_pct": economic_share_uplift_pct,
        "target_median": target_median,
        "target_range": target_range,
        "upside_pct": upside,
        "dilution_warning": dilution_present,
        "screen_dilution_warning": screen_dilution_present,
        "official_dilution_warning": official_dilution_present,
        "screen_supply_unreconciled": screen_supply_unreconciled,
        "official_supply_checks": {
            check: str(official_supply_checks.get(check, "UNKNOWN")).upper()
            for check in SUPPLY_CHECKS
        },
        "unknown_supply_checks": unknown_supply_checks,
        "present_supply_checks": present_supply_checks,
        "supply_evidence_complete": supply_evidence_complete,
        "supply_evidence_asof": None if supply_evidence_at is None else supply_evidence_at.isoformat(),
        "scope_partial": scope_partial,
        "block_reasons": block_reasons,
        "state": state,
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_snapshot(json.loads(args.input.read_text(encoding="utf-8")))
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
