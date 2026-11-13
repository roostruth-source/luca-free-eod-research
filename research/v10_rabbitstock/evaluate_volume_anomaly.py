"""Evaluate a completed-session volume anomaly without calling it a buy signal."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from statistics import median
from typing import Any


VOLUME_AVERAGE_MULTIPLE_THRESHOLD = 5.0
PRIOR_SURGE_THRESHOLD_PCT = 20.0
PROVIDER_TOLERANCE_PCT = 1.0


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _volume(bar: dict[str, Any], evaluation_asof: datetime) -> float:
    if not bool(bar.get("session_complete")):
        raise ValueError("incomplete_bar_not_allowed")
    if _time(bar["available_at"]) > evaluation_asof:
        raise ValueError("future_bar_not_allowed")
    observations = bar.get("volume_observations", [])
    providers = [str(item["provider_id"]) for item in observations]
    urls = [str(item["source_url"]) for item in observations]
    if len(set(providers)) < 2:
        raise ValueError("two_independent_volume_providers_required")
    if len(set(urls)) < 2 or any(not url.startswith("https://") for url in urls):
        raise ValueError("two_https_volume_sources_required")
    values = [float(item["volume"]) for item in observations]
    if min(values) <= 0:
        raise ValueError("volume_must_be_positive")
    disagreement = (max(values) / min(values) - 1.0) * 100.0
    if disagreement > PROVIDER_TOLERANCE_PCT:
        raise ValueError("volume_source_conflict")
    return median(values)


def evaluate_volume_anomaly(payload: dict[str, Any]) -> dict[str, Any]:
    evaluation_asof = _time(payload["evaluation_asof"])
    prior = payload["prior_bars"]
    if len(prior) != 10:
        raise ValueError("exactly_ten_prior_sessions_required")
    current = payload["current_bar"]
    current_date = _date(current["date"])
    dates = [_date(bar["date"]) for bar in prior]
    if dates != sorted(set(dates)) or any(value >= current_date for value in dates):
        raise ValueError("prior_sessions_must_be_unique_ordered_and_earlier")
    if payload.get("price_volume_basis") != "SPLIT_ADJUSTED_TO_EVENT":
        raise ValueError("split_adjusted_event_basis_required")

    current_volume = _volume(current, evaluation_asof)
    prior_volumes = [_volume(bar, evaluation_asof) for bar in prior]
    prior_average = sum(prior_volumes) / len(prior_volumes)
    prior_sum = sum(prior_volumes)
    volume_avg_multiple = current_volume / prior_average
    volume_sum_multiple = current_volume / prior_sum

    prior_close = float(prior[-1]["close"])
    current_close = float(current["close"])
    if prior_close <= 0 or current_close <= 0:
        raise ValueError("close_must_be_positive")
    close_return_pct = (current_close / prior_close - 1.0) * 100.0
    prior_session_return_pct = float(prior[-1]["return_pct"])

    anomaly = volume_avg_multiple >= VOLUME_AVERAGE_MULTIPLE_THRESHOLD
    already_surged = prior_session_return_pct >= PRIOR_SURGE_THRESHOLD_PCT
    float_verified = bool(payload.get("float_verified", False))
    turnover = None
    if float_verified:
        float_shares = float(payload["float_shares"])
        if float_shares <= 0:
            raise ValueError("float_must_be_positive")
        turnover = current_volume / float_shares

    block_reasons: list[str] = []
    if not anomaly:
        block_reasons.append("VOLUME_ANOMALY_THRESHOLD_NOT_MET")
    if already_surged:
        block_reasons.append("ALREADY_SURGED_PREVIOUS_SESSION")
    if not float_verified:
        block_reasons.append("FLOAT_TURNOVER_UNVERIFIED")

    return {
        "ticker": str(payload["ticker"]).upper(),
        "event_date": current_date.isoformat(),
        "evaluation_asof": evaluation_asof.isoformat(),
        "current_volume": round(current_volume, 2),
        "prior_10_average_volume": round(prior_average, 2),
        "prior_10_sum_volume": round(prior_sum, 2),
        "volume_vs_average_multiple": round(volume_avg_multiple, 8),
        "volume_vs_sum_multiple": round(volume_sum_multiple, 8),
        "close_return_pct": round(close_return_pct, 8),
        "prior_session_return_pct": prior_session_return_pct,
        "volume_anomaly_confirmed": anomaly,
        "already_surged_previous_session": already_surged,
        "float_turnover_multiple": None if turnover is None else round(turnover, 8),
        "early_volume_candidate": anomaly and not already_surged and float_verified,
        "state": "WATCH_ONLY_BLOCKED" if block_reasons else "WATCH_ONLY_VOLUME_FIRST",
        "block_reasons": block_reasons,
        "thresholds_are_predeclared_not_optimized": True,
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python evaluate_volume_anomaly.py INPUT.json", file=sys.stderr)
        return 2
    with open(sys.argv[1], encoding="utf-8") as handle:
        payload = json.load(handle)
    print(json.dumps(evaluate_volume_anomaly(payload), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
