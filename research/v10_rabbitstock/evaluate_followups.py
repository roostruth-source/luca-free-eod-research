"""Reproducible follow-up evaluator for frozen LUCA V10 signals.

It evaluates completed, split-adjusted daily bars only. Screen entry prices are
reference prices, not assumed fills, so this module never labels them trades.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any


HORIZONS = (1, 3, 5, 10)
ENGINES = ("preview", "signal", "hidden_pick", "best", "burning_up")
ENTRY_RULES = {"SCREEN_REFERENCE_PRICE", "EXPLICIT_FIXED_ENTRY"}
PRICE_BASIS = "SPLIT_ADJUSTED_TO_SIGNAL"


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def _pct(value: float, entry: float) -> float:
    return (value / entry - 1.0) * 100.0


def _engine_names(raw: Any) -> list[str]:
    if isinstance(raw, dict):
        names = list(raw)
    elif isinstance(raw, list):
        names = [str(value) for value in raw]
    else:
        raise ValueError("invalid_engine_hits")
    unknown = set(names) - set(ENGINES)
    if unknown:
        raise ValueError(f"unknown_engines:{','.join(sorted(unknown))}")
    if len(names) != len(set(names)):
        raise ValueError("duplicate_engine_hit")
    return [engine for engine in ENGINES if engine in names]


def _groups(record: dict[str, Any]) -> list[str]:
    engines = set(record["engines"])
    count = len(engines)
    groups = [
        f"engine_count:{'3+' if count >= 3 else count}",
        f"dilution_warning:{'YES' if record['dilution_warning'] else 'NO'}",
        (
            "screen_dilution_warning:"
            f"{'YES' if record['screen_dilution_warning'] else 'NO'}"
        ),
        (
            "official_dilution_warning:"
            f"{'YES' if record['official_dilution_warning'] else 'NO'}"
        ),
    ]
    if {"preview", "signal"}.issubset(engines):
        groups.append("combo:preview+signal")
    if {"signal", "burning_up"}.issubset(engines):
        groups.append("combo:signal+burning_up")
    return groups


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "n": 0,
            "positive_close_rate_pct": None,
            "mean_close_return_pct": None,
            "median_close_return_pct": None,
            "mean_ex_largest_gain_pct": None,
        }
    trimmed = values.copy()
    trimmed.remove(max(trimmed))
    return {
        "n": len(values),
        "positive_close_rate_pct": sum(value > 0 for value in values) / len(values) * 100.0,
        "mean_close_return_pct": mean(values),
        "median_close_return_pct": median(values),
        "mean_ex_largest_gain_pct": mean(trimmed) if trimmed else None,
    }


def evaluate_followups(payload: dict[str, Any]) -> dict[str, Any]:
    """Evaluate frozen signals without treating screen prices as executions."""

    evaluation_asof = _parse_time(payload["evaluation_asof"])
    records: list[dict[str, Any]] = []

    for item in payload.get("signals", []):
        signal_at = _parse_time(item["signal_at"])
        if signal_at > evaluation_asof:
            raise ValueError("future_signal_not_allowed")
        entry = float(item["entry_price"])
        if entry <= 0:
            raise ValueError("entry_price_must_be_positive")
        entry_rule = str(item.get("entry_rule", ""))
        if entry_rule not in ENTRY_RULES:
            raise ValueError("unsupported_entry_rule")
        engines = _engine_names(item.get("engine_hits", []))
        legacy_dilution_warning = bool(item.get("dilution_warning", False))
        screen_dilution_warning = bool(
            item.get("screen_dilution_warning", legacy_dilution_warning)
        )
        official_dilution_warning = bool(
            item.get("official_dilution_warning", legacy_dilution_warning)
        )

        bars: list[dict[str, Any]] = []
        previous_close_at: datetime | None = None
        for bar in item.get("bars", []):
            close_at = _parse_time(bar["session_close_at"])
            if close_at > evaluation_asof:
                raise ValueError("future_bar_not_allowed")
            if close_at <= signal_at:
                raise ValueError("bar_not_after_signal")
            if previous_close_at is not None and close_at <= previous_close_at:
                raise ValueError("bars_not_strictly_ordered")
            previous_close_at = close_at
            if not bool(bar.get("complete", False)):
                raise ValueError("incomplete_bar_not_allowed")
            if bar.get("price_basis") != PRICE_BASIS:
                raise ValueError("split_adjusted_price_basis_required")
            prices = {key: float(bar[key]) for key in ("open", "high", "low", "close")}
            if any(value <= 0 for value in prices.values()):
                raise ValueError("bar_price_must_be_positive")
            if prices["low"] > min(prices["open"], prices["close"]):
                raise ValueError("invalid_bar_low")
            if prices["high"] < max(prices["open"], prices["close"]):
                raise ValueError("invalid_bar_high")
            bars.append({"close_at": close_at, **prices})

        outcomes: dict[str, dict[str, Any]] = {}
        for horizon in HORIZONS:
            if len(bars) < horizon:
                outcomes[str(horizon)] = {
                    "status": "NOT_MATURE",
                    "completed_bars": len(bars),
                }
                continue
            window = bars[:horizon]
            outcomes[str(horizon)] = {
                "status": "MATURE",
                "exit_basis": "HORIZON_CLOSE",
                "close_return_pct": _pct(window[-1]["close"], entry),
                "mfe_pct": _pct(max(bar["high"] for bar in window), entry),
                "mae_pct": _pct(min(bar["low"] for bar in window), entry),
                "exit_at": window[-1]["close_at"].isoformat(),
            }

        record = {
            "ticker": str(item["ticker"]).upper(),
            "signal_at": signal_at.isoformat(),
            "entry_price": entry,
            "entry_rule": entry_rule,
            "reference_only": entry_rule == "SCREEN_REFERENCE_PRICE",
            "engines": engines,
            "engine_count": len(engines),
            "screen_dilution_warning": screen_dilution_warning,
            "official_dilution_warning": official_dilution_warning,
            "dilution_warning": screen_dilution_warning or official_dilution_warning,
            "outcomes": outcomes,
        }
        record["groups"] = _groups(record)
        records.append(record)

    group_values: dict[str, dict[int, list[float]]] = {}
    for record in records:
        for group in record["groups"]:
            horizons = group_values.setdefault(group, {horizon: [] for horizon in HORIZONS})
            for horizon in HORIZONS:
                outcome = record["outcomes"][str(horizon)]
                if outcome["status"] == "MATURE":
                    horizons[horizon].append(float(outcome["close_return_pct"]))

    grouped = {
        group: {str(horizon): _summary(values[horizon]) for horizon in HORIZONS}
        for group, values in sorted(group_values.items())
    }

    return {
        "evaluation_asof": evaluation_asof.isoformat(),
        "signals_evaluated": len(records),
        "records": records,
        "grouped_reference_statistics": grouped,
        "accuracy_not_computed": True,
        "accuracy_reason": (
            "Screen reference prices are not verified fills; positive close rate is not a trade hit rate."
        ),
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_followups(json.loads(args.input.read_text(encoding="utf-8")))
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
