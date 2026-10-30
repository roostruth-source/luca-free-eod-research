"""Synthetic-only as-of decision-readiness audit with assumed processing delay.

A signal computed from a one-minute bar can be considered ready only after
bar completion + assumed feed delay + assumed computation delay. This is
a structural sensitivity check, NOT evidence of real processing speed,
tradable prices, order timing, or predictive success.
"""
from __future__ import annotations

import datetime as dt

from mobile_outcomes import _time
from offline_asof_availability import audit_asof_availability
from offline_latency_sensitivity import _eligible_stamp, _latencies

MINUTE = dt.timedelta(minutes=1)
DEFAULT_FEED_SECONDS = (0, 1, 30, 60)
DEFAULT_COMPUTE_SECONDS = (0, 1, 30, 60, 120)
MAX_COMPUTE_SECONDS = 300
MAX_SCENARIO_PAIRS = 25


def _compute_delays(values):
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError("MISSING_COMPUTATION_DELAY_SCENARIOS")
    if any(type(value) is not int or not 0 <= value <= MAX_COMPUTE_SECONDS
           for value in values):
        raise ValueError("INVALID_COMPUTATION_DELAY_SECONDS")
    if len(set(values)) != len(values):
        raise ValueError("DUPLICATE_COMPUTATION_DELAY_SCENARIO")
    return tuple(sorted(values))


def audit_decision_readiness(
    sessions,
    publication_latencies_seconds=DEFAULT_FEED_SECONDS,
    computation_delays_seconds=DEFAULT_COMPUTE_SECONDS,
):
    """Return per-session readiness at frozen reference T; never pool wins.

    All input validation is delegated to the existing frozen-session gate.
    A ready signal does not mean a trade was possible. A bar close is not
    an executable quote, and future outcome prices are not read here.
    """
    feeds = _latencies(publication_latencies_seconds)
    computes = _compute_delays(computation_delays_seconds)
    if len(feeds) * len(computes) > MAX_SCENARIO_PAIRS:
        raise ValueError("TOO_MANY_DELAY_SCENARIOS")
    audited = audit_asof_availability(sessions)
    reference_by_day = {
        day["session_day_ny"]: _time(day["reference_time_utc"])
        for day in audited["rows"]
    }
    output = []
    for session in sorted(sessions, key=lambda s: s["session_day_ny"]):
        day = session["session_day_ny"]
        reference = reference_by_day[day]
        scenarios = []
        for feed in feeds:
            for compute in computes:
                total = dt.timedelta(seconds=feed + compute)
                baseline_stamp = _eligible_stamp(reference, feed)
                rows = []
                for row in session["raw"]["rows"]:
                    stamps = [
                        _time(signal["signal"]["signal_bar_start_utc"])
                        for signal in row["signals"]
                    ]
                    ready_times = [stamp + MINUTE + total for stamp in stamps]
                    first_ready = min(ready_times, default=None)
                    known_count = sum(ready <= reference for ready in ready_times)
                    prices_at_baseline = [
                        bar for bar in row["ohlcv"]
                        if _time(bar["t"]) == baseline_stamp
                    ]
                    has_baseline = bool(prices_at_baseline)
                    if not stamps:
                        status = "NO_SIGNAL_IN_ARCHIVE"
                    elif known_count:
                        status = "SIGNAL_READY_BY_REFERENCE"
                    else:
                        status = "SIGNAL_NOT_READY_BY_REFERENCE"
                    rows.append({
                        "symbol": row["symbol"],
                        "status": status,
                        "signal_ready_by_reference": bool(known_count),
                        "known_signal_count": known_count,
                        "signal_count_in_archive": len(stamps),
                        "earliest_hypothetical_signal_ready_utc": (
                            first_ready.isoformat() if first_ready else None
                        ),
                        "seconds_until_first_signal_ready_from_reference": (
                            int((first_ready - reference).total_seconds())
                            if first_ready else None
                        ),
                        "baseline_bar_start_utc": baseline_stamp.isoformat(),
                        "exact_baseline_bar_present": has_baseline,
                        "ready_signal_with_reference_bar": bool(known_count and has_baseline),
                        "executable_quote_verified": False,
                        "orders_allowed": False,
                    })
                scenarios.append({
                    "assumed_publication_latency_seconds": feed,
                    "assumed_signal_computation_seconds": compute,
                    "rows": sorted(rows, key=lambda r: r["symbol"]),
                    "candidate_count": len(rows),
                    "ready_signal_count": sum(r["signal_ready_by_reference"] for r in rows),
                    "ready_with_reference_bar_count": sum(
                        r["ready_signal_with_reference_bar"] for r in rows
                    ),
                    "missing_reference_bar_count": sum(
                        not r["exact_baseline_bar_present"] for r in rows
                    ),
                })
        output.append({
            "session_day_ny": day,
            "reference_time_utc": reference.isoformat(),
            "candidate_count": len(session["raw"]["rows"]),
            "scenarios": scenarios,
        })
    return {
        "schema": "LUCA_V03_OFFLINE_DECISION_READINESS_V1",
        "sessions": output,
        "session_count": len(output),
        "publication_latencies_seconds_assumed": list(feeds),
        "computation_delays_seconds_assumed": list(computes),
        "publication_latency_measured": False,
        "signal_computation_time_measured": False,
        "actual_signal_delivery_time_verified": False,
        "actual_order_timing_verified": False,
        "executable_prices_verified": False,
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
        "warnings": sorted(set(audited["warnings"]) | {
            "HYPOTHETICAL_COMPUTATION_DELAY_NOT_MEASURED",
            "HYPOTHETICAL_PUBLICATION_LATENCY_NOT_MEASURED",
            "SIGNAL_READY_IS_NOT_TRADE_READY",
            "BAR_CLOSE_NOT_EXECUTABLE_QUOTE",
            "REPEATED_SYMBOL_SESSIONS_NOT_INDEPENDENT",
            "NO_POOLED_WIN_RATE",
        }),
        "note_ko": (
            "완성된 1분봉이 도착한 뒤 신호 계산에 시간이 더 걸린다고 "
            "가정하여 기준 시각까지 신호를 알 수 있었는지 날짜별로 검사합니다. "
            "가정한 초 단위 지연은 실제 측정값이 아니며, 신호가 준비됐더라도 "
            "그 가격에 매수할 수 있었다는 뜻이 아닙니다. 승률·수익률은 계산하지 않습니다."
        ),
    }
