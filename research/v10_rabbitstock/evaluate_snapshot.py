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
DILUTION_FLAGS = ("atm", "eloc", "toxic_financing", "cb", "warrant")
FLOAT_MISMATCH_TOLERANCE = 0.02


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
    dilution_present = any(bool(warnings.get(flag, False)) for flag in DILUTION_FLAGS)
    float_ratio = None
    if len(engine_floats) >= 2:
        float_ratio = max(engine_floats.values()) / min(engine_floats.values())
    float_mismatch = bool(
        float_ratio is not None and float_ratio > 1.0 + FLOAT_MISMATCH_TOLERANCE
    )
    split_factors = [float(value) for value in payload.get("reverse_split_factors", [])]
    float_mismatch_matches_split_factor = bool(
        float_mismatch
        and any(abs(float_ratio - factor) / factor <= FLOAT_MISMATCH_TOLERANCE for factor in split_factors)
    )
    float_basis_reconciled = bool(payload.get("float_basis_reconciled", False))
    unit_blocked = (
        not bool(payload.get("split_basis_verified", False))
        or bool(warnings.get("reverse_split", False))
        or bool(warnings.get("dilution_unit_mismatch", False))
        or not bool(payload.get("float_verified", False))
        or (float_mismatch and not float_basis_reconciled)
    )
    scope_partial = bool(payload.get("scope_partial", False))

    engine_count = len(ranks)
    target_median = median(targets) if targets else None
    target_range = [min(targets), max(targets)] if targets else None
    upside = None if target_median is None else (target_median / entry - 1.0) * 100.0

    if unit_blocked or scope_partial:
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
        "engine_count": engine_count,
        "engine_ranks": ranks,
        "engine_floats": engine_floats,
        "cross_engine_float_mismatch": float_mismatch,
        "float_ratio": float_ratio,
        "float_mismatch_matches_split_factor": float_mismatch_matches_split_factor,
        "float_basis_reconciled": float_basis_reconciled,
        "target_median": target_median,
        "target_range": target_range,
        "upside_pct": upside,
        "dilution_warning": dilution_present,
        "scope_partial": scope_partial,
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
