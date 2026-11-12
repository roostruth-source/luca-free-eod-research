"""Reconcile independent public OHLC sources before follow-up evaluation.

No canonical bar is emitted unless at least two independent sources agree.
This is a research-only data-quality gate and never creates orders.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


OHLC_FIELDS = ("open", "high", "low", "close")
PRICE_BASIS = "SPLIT_ADJUSTED_TO_SIGNAL"


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def _spread_pct(values: list[float]) -> float:
    return (max(values) / min(values) - 1.0) * 100.0


def reconcile_bar(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a canonical bar only when independent sources agree."""

    evaluation_asof = _parse_time(payload["evaluation_asof"])
    signal_at = _parse_time(payload["signal_at"])
    if signal_at > evaluation_asof:
        raise ValueError("future_signal_not_allowed")

    tolerance_pct = float(payload.get("ohlc_tolerance_pct", 1.0))
    if tolerance_pct < 0:
        raise ValueError("negative_tolerance_not_allowed")

    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError("sources_must_be_list")

    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    urls: set[str] = set()
    session_close_at: datetime | None = None
    for source in sources:
        name = str(source.get("source_name", "")).strip()
        if not name:
            raise ValueError("source_name_required")
        if name in names:
            raise ValueError("duplicate_source_not_independent")
        names.add(name)

        source_url = str(source.get("source_url", "")).strip()
        if not source_url.startswith("https://"):
            raise ValueError("https_source_url_required")
        if source_url in urls:
            raise ValueError("duplicate_source_url_not_independent")
        urls.add(source_url)

        retrieved_at = _parse_time(source["retrieved_at"])
        if retrieved_at > evaluation_asof:
            raise ValueError("future_source_retrieval_not_allowed")
        close_at = _parse_time(source["session_close_at"])
        if close_at > evaluation_asof:
            raise ValueError("future_bar_not_allowed")
        if close_at <= signal_at:
            raise ValueError("bar_not_after_signal")
        if session_close_at is None:
            session_close_at = close_at
        elif close_at != session_close_at:
            raise ValueError("source_session_mismatch")
        if not bool(source.get("complete", False)):
            raise ValueError("incomplete_bar_not_allowed")
        if source.get("price_basis") != PRICE_BASIS:
            raise ValueError("split_adjusted_price_basis_required")

        prices = {
            field: float(source[field])
            for field in OHLC_FIELDS
            if source.get(field) is not None
        }
        if not prices:
            raise ValueError("at_least_one_ohlc_field_required")
        if any(value <= 0 for value in prices.values()):
            raise ValueError("bar_price_must_be_positive")
        if set(prices) == set(OHLC_FIELDS):
            if prices["low"] > min(prices["open"], prices["close"]):
                raise ValueError("invalid_bar_low")
            if prices["high"] < max(prices["open"], prices["close"]):
                raise ValueError("invalid_bar_high")
        normalized.append(
            {
                "source_name": name,
                "source_url": source_url,
                "retrieved_at": retrieved_at.isoformat(),
                **prices,
            }
        )

    base = {
        "ticker": str(payload["ticker"]).upper(),
        "evaluation_asof": evaluation_asof.isoformat(),
        "signal_at": signal_at.isoformat(),
        "source_count": len(normalized),
        "source_names": sorted(names),
        "source_observations": sorted(normalized, key=lambda item: item["source_name"]),
        "ohlc_tolerance_pct": tolerance_pct,
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }
    if len(normalized) < 2:
        return {
            **base,
            "reconciliation_status": "SINGLE_SOURCE_UNVERIFIED",
            "canonical_bar": None,
            "block_reasons": ["AT_LEAST_TWO_INDEPENDENT_SOURCES_REQUIRED"],
        }

    field_values = {
        field: [source[field] for source in normalized if field in source]
        for field in OHLC_FIELDS
    }
    field_source_count = {field: len(values) for field, values in field_values.items()}
    spreads = {
        field: _spread_pct(values)
        for field, values in field_values.items()
        if len(values) >= 2
    }
    conflicts = [field for field, spread in spreads.items() if spread > tolerance_pct]
    if conflicts:
        return {
            **base,
            "reconciliation_status": "SOURCE_CONFLICT",
            "field_spread_pct": spreads,
            "field_source_count": field_source_count,
            "conflicting_fields": conflicts,
            "canonical_bar": None,
            "block_reasons": ["PUBLIC_PRICE_SOURCES_DISAGREE"],
        }

    insufficient = [field for field, count in field_source_count.items() if count < 2]
    if insufficient:
        return {
            **base,
            "reconciliation_status": "INSUFFICIENT_FIELD_COVERAGE",
            "field_spread_pct": spreads,
            "field_source_count": field_source_count,
            "insufficient_fields": insufficient,
            "conflicting_fields": [],
            "canonical_bar": None,
            "block_reasons": ["TWO_SOURCES_REQUIRED_FOR_EACH_OHLC_FIELD"],
        }

    canonical = {field: median(field_values[field]) for field in OHLC_FIELDS}
    canonical.update(
        {
            "session_close_at": session_close_at.isoformat(),
            "complete": True,
            "price_basis": PRICE_BASIS,
            "source_count": len(normalized),
        }
    )
    return {
        **base,
        "reconciliation_status": "VERIFIED",
        "field_spread_pct": spreads,
        "field_source_count": field_source_count,
        "conflicting_fields": [],
        "canonical_bar": canonical,
        "block_reasons": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = reconcile_bar(json.loads(args.input.read_text(encoding="utf-8")))
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
