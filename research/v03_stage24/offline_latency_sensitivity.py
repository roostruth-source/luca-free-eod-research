"""Offline hypothetical publication-latency sensitivity for completed one-minute bars.

Bar stamps denote START, not availability. For assumed latency L seconds,
a bar can be used at instant T only if bar_start + 60s + L <= T.
This is an additive diagnostic; latency is not measured, nor is any price a
tradeable quote. All source validation is delegated to existing offline gates.
"""
from __future__ import annotations

import datetime as dt
import math

from mobile_outcomes import _price, _time
from offline_asof_availability import audit_asof_availability

MINUTE = dt.timedelta(minutes=1)
HORIZONS = (5, 15, 30, 60)
GROUPS = ("signal_known_by_reference_time", "no_signal_known_by_reference_time")
DEFAULT_LATENCIES_SECONDS = (0, 1, 30, 60, 120)
MAX_ASSUMED_LATENCY_SECONDS = 300


def _latencies(values):
    if not isinstance(values, (tuple, list)) or not values:
        raise ValueError("MISSING_LATENCY_SCENARIOS")
    if any(type(v) is not int or v < 0 or v > MAX_ASSUMED_LATENCY_SECONDS
           for v in values):
        raise ValueError("INVALID_ASSUMED_LATENCY_SECONDS")
    if len(set(values)) != len(values):
        raise ValueError("DUPLICATE_LATENCY_SCENARIO")
    return tuple(sorted(values))


def _eligible_stamp(instant, latency_seconds):
    """Exact expected one-minute bar start; never backfill a missing minute."""
    # T is minute-aligned by audit_asof_availability. Even one second of
    # assumed publication delay excludes the bar that finishes exactly at T.
    extra_minutes = (latency_seconds + 59) // 60
    return instant - MINUTE * (1 + extra_minutes)


def latency_sensitivity(sessions, latencies_seconds=DEFAULT_LATENCIES_SECONDS):
    """Per-session, per-latency descriptive returns; no pooled success rate."""
    scenarios = _latencies(latencies_seconds)
    audit = audit_asof_availability(sessions)
    reference_by_day = {
        row["session_day_ny"]: _time(row["reference_time_utc"])
        for row in audit["rows"]
    }
    output = []
    for item in sorted(sessions, key=lambda s: s["session_day_ny"]):
        day = item["session_day_ny"]
        anchor = reference_by_day[day]
        scenario_results = []
        for latency in scenarios:
            delta = dt.timedelta(seconds=latency)
            baseline_stamp = _eligible_stamp(anchor, latency)
            rows = []
            for row in item["raw"]["rows"]:
                prices = {_time(bar["t"]): _price(bar["c"])
                          for bar in row["ohlcv"]}
                known = any(
                    _time(entry["signal"]["signal_bar_start_utc"]) + MINUTE + delta <= anchor
                    for entry in row["signals"]
                )
                group = (GROUPS[0] if known else GROUPS[1])
                baseline = prices.get(baseline_stamp)
                changes, status, horizon_stamps = {}, {}, {}
                for minutes in HORIZONS:
                    key = str(minutes)
                    target_stamp = _eligible_stamp(
                        anchor + dt.timedelta(minutes=minutes), latency)
                    horizon_stamps[key] = target_stamp.isoformat()
                    target = prices.get(target_stamp)
                    if baseline is None:
                        changes[key] = None
                        status[key] = "MISSING_EXACT_LATENCY_ELIGIBLE_BASELINE_BAR"
                    elif target is None:
                        changes[key] = None
                        status[key] = "MISSING_EXACT_LATENCY_ELIGIBLE_HORIZON_BAR"
                    else:
                        change = (target / baseline - 1) * 100
                        if not math.isfinite(change):
                            raise ValueError("NONFINITE_DESCRIPTIVE_CHANGE")
                        changes[key] = round(change, 4)
                        status[key] = "OBSERVED_DESCRIPTIVE_ONLY"
                rows.append({
                    "symbol": row["symbol"],
                    "group": group,
                    "assumed_latency_seconds": latency,
                    "baseline_bar_start_utc": baseline_stamp.isoformat(),
                    "baseline_close": baseline,
                    "horizon_bar_starts_utc": horizon_stamps,
                    "changes_pct": changes,
                    "horizon_status": status,
                    "executable_price_verified": False,
                })
            counts = {
                str(h): {
                    group: {
                        "candidates": sum(r["group"] == group for r in rows),
                        "observed": sum(r["group"] == group and
                                        r["changes_pct"][str(h)] is not None for r in rows),
                        "missing": sum(r["group"] == group and
                                       r["changes_pct"][str(h)] is None for r in rows),
                    }
                    for group in GROUPS
                }
                for h in HORIZONS
            }
            scenario_results.append({
                "assumed_latency_seconds": latency,
                "rows": sorted(rows, key=lambda r: r["symbol"]),
                "counts_by_horizon": counts,
            })
        output.append({
            "session_day_ny": day,
            "reference_time_utc": anchor.isoformat(),
            "candidate_count": len(item["raw"]["rows"]),
            "latency_scenarios": scenario_results,
        })
    return {
        "schema": "LUCA_V03_OFFLINE_LATENCY_SENSITIVITY_V1",
        "sessions": output,
        "session_count": len(output),
        "latencies_seconds_assumed": list(scenarios),
        "latency_values_measured": False,
        "bar_publication_latency_verified": False,
        "signal_calculation_latency_verified": False,
        "independent_sample_count_verified": 0,
        "aggregate_win_rate_computed": False,
        "prediction_accuracy_verified": False,
        "statistical_significance_verified": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "operating_mode": "NO_ORDERS",
        "orders_allowed": False,
        "real_trades_allowed": False,
        "warnings": sorted(set(audit["warnings"]) | {
            "HYPOTHETICAL_LATENCY_ONLY_NOT_MEASURED",
            "BAR_CLOSE_IS_NOT_EXECUTABLE_QUOTE",
            "EXACT_MISSING_BARS_NOT_BACKFILLED",
            "REPEATED_SYMBOL_SESSIONS_NOT_INDEPENDENT",
            "NO_POOLED_PREDICTION_WIN_RATE",
        }),
        "note_ko": "0·1·30·60·120초는 가정한 지연 시나리오이며 실제 측정값이 아닙니다. 각 시각까지 완료되고 지연시간까지 지난 1분봉만 사용합니다. 빠진 분봉은 임의로 채우지 않고, 날짜별로만 계산합니다. 실제 매수·매도 수익이나 검증된 예측 성공률이 아닙니다.",
    }
