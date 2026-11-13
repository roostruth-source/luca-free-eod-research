"""Evaluate a convertible-note reset event without turning it into a signal claim.

The contract date, price-measurement window, and later market bars are kept
separate.  A reset price that requires VWAP cannot be reconstructed from OHLC
bars.  Post-event results are descriptive WATCH_ONLY observations, not proof
that a reset causes a pump.
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


def _official_url(value: str) -> None:
    if not value.startswith("https://www.sec.gov/"):
        raise ValueError("official_sec_contract_source_required")


def _validate_bar(bar: dict[str, Any], evaluation_asof: datetime) -> None:
    if bar.get("verification_status") != "TWO_PROVIDER_RECONCILED":
        raise ValueError("two_provider_reconciled_bar_required")
    providers = bar.get("provider_ids", [])
    if len(set(providers)) < 2:
        raise ValueError("two_independent_providers_required")
    urls = bar.get("source_urls", [])
    if len(set(urls)) < 2 or any(not str(url).startswith("https://") for url in urls):
        raise ValueError("two_https_source_urls_required")
    if float(bar.get("max_field_disagreement_pct", 100.0)) > 1.0:
        raise ValueError("bar_source_conflict")
    if _time(bar["available_at"]) > evaluation_asof:
        raise ValueError("future_bar_not_allowed")
    if not bool(bar.get("session_complete")):
        raise ValueError("incomplete_bar_not_allowed")
    o, h, low, c = (float(bar[key]) for key in ("open", "high", "low", "close"))
    if min(o, h, low, c) <= 0 or h < max(o, c) or low > min(o, c):
        raise ValueError("invalid_ohlc")


def evaluate_cb_reset_event(payload: dict[str, Any]) -> dict[str, Any]:
    evaluation_asof = _time(payload["evaluation_asof"])
    reference_at = _time(payload["reference_at"])
    if reference_at > evaluation_asof:
        raise ValueError("future_reference_not_allowed")

    contract = payload["contract"]
    evidence_at = _time(contract["evidence_available_at"])
    if evidence_at > reference_at:
        raise ValueError("future_contract_evidence_not_allowed")
    _official_url(str(contract.get("source_url", "")))
    if not bool(contract.get("reduction_only")):
        raise ValueError("reset_direction_must_be_explicit")

    event_date = _date(contract["share_combination_event_date"])
    sessions = [_date(value) for value in payload["trading_sessions_after_event"]]
    if not sessions or sessions != sorted(set(sessions)):
        raise ValueError("trading_sessions_must_be_unique_and_ordered")
    if any(session <= event_date for session in sessions):
        raise ValueError("trading_session_must_follow_event")
    reset_after = int(contract["reset_after_trading_sessions"])
    if reset_after <= 0 or len(sessions) < reset_after:
        raise ValueError("insufficient_sessions_to_locate_reset")
    reset_date = sessions[reset_after - 1]

    measurement_window = int(contract["event_market_price_window_sessions"])
    lowest_count = int(contract["lowest_vwap_count"])
    if measurement_window <= 0 or lowest_count <= 0 or lowest_count > measurement_window:
        raise ValueError("invalid_vwap_window_definition")
    vwap_values = payload.get("pre_reset_vwap_values", [])
    reset_price_status = "VERIFIED" if len(vwap_values) == measurement_window else "UNVERIFIED"
    reset_price = None
    reset_reasons: list[str] = []
    if reset_price_status == "VERIFIED":
        values = [float(value) for value in vwap_values]
        if min(values) <= 0:
            raise ValueError("vwap_must_be_positive")
        reset_price = sum(sorted(values)[:lowest_count]) / lowest_count
    else:
        reset_reasons.append("RESET_PRICE_UNVERIFIED_VWAP_MISSING")

    bars = payload["bars"]
    bar_dates = [_date(bar["date"]) for bar in bars]
    if bar_dates != sorted(set(bar_dates)):
        raise ValueError("bars_must_be_unique_and_ordered")
    for bar in bars:
        _validate_bar(bar, evaluation_asof)
    by_date = {_date(bar["date"]): bar for bar in bars}
    if reset_date not in by_date:
        raise ValueError("reset_date_bar_required")

    baseline = float(by_date[reset_date]["close"])
    post_bars = [bar for bar in bars if _date(bar["date"]) > reset_date]
    horizons: dict[str, Any] = {}
    for horizon in payload.get("horizons", [1, 3, 5, 10]):
        key = str(int(horizon))
        if len(post_bars) < int(horizon):
            horizons[key] = {"status": "NOT_MATURE"}
            continue
        window = post_bars[: int(horizon)]
        end_close = float(window[-1]["close"])
        max_high = max(float(bar["high"]) for bar in window)
        min_low = min(float(bar["low"]) for bar in window)
        horizons[key] = {
            "status": "MATURE",
            "end_date": window[-1]["date"],
            "close_return_pct": round((end_close / baseline - 1.0) * 100.0, 8),
            "MFE_pct": round((max_high / baseline - 1.0) * 100.0, 8),
            "MAE_pct": round((min_low / baseline - 1.0) * 100.0, 8),
        }

    first_post = post_bars[0] if post_bars else None
    first_day_volume_multiple = None
    if first_post is not None:
        first_day_volume_multiple = float(first_post["volume"]) / float(
            by_date[reset_date]["volume"]
        )

    reasons = [*reset_reasons]
    if any(value.get("status") == "NOT_MATURE" for value in horizons.values()):
        reasons.append("FOLLOWUP_HORIZON_NOT_MATURE")
    return {
        "evaluation_asof": evaluation_asof.isoformat(),
        "reference_at": reference_at.isoformat(),
        "ticker": payload["ticker"],
        "derived_reset_date": reset_date.isoformat(),
        "reset_date_is_contract_derived": True,
        "reset_price_status": reset_price_status,
        "reset_price": reset_price,
        "reset_price_reasons": reset_reasons,
        "baseline_close": baseline,
        "first_post_session_volume_multiple": (
            round(first_day_volume_multiple, 8)
            if first_day_volume_multiple is not None
            else None
        ),
        "horizons": horizons,
        "block_reasons": reasons,
        "causality_status": "NOT_ESTABLISHED_SINGLE_EVENT",
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input_json.read_text())
    print(json.dumps(evaluate_cb_reset_event(payload), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
