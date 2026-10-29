"""Strict as-of offline descriptive scorecard (additive, legacy remains unchanged).

A one-minute bar timestamp denotes its START. At reference instant T,
the most recent structurally completed bar starts at T-1 minute; a close
stamped T is NOT available at T. Outcomes at T+h use the bar starting
T+h-1 minute. This assumes zero publication latency and is not a fill.
No network, order, or live experiment is performed.
"""
from __future__ import annotations

import datetime as dt

from mobile_outcomes import _price, _time
from offline_asof_availability import audit_asof_availability

HORIZONS_MINUTES = (5, 15, 30, 60)
MINUTE = dt.timedelta(minutes=1)
GROUPS = ("signal_known_by_reference_time", "no_signal_known_by_reference_time")


def strict_asof_scorecard(sessions):
    """Score each frozen NY session separately, never pool independent samples.

    audit_asof_availability performs the existing raw/signal, commitment,
    market-calendar, and session checks before any descriptive calculation.
    """
    audit = audit_asof_availability(sessions)
    raw_by_day = {item["session_day_ny"]: item["raw"] for item in sessions}
    audit_by_key = {(r["session_day_ny"], r["symbol"]): r for r in audit["rows"]}
    results = []
    for day in sorted(raw_by_day):
        raw = raw_by_day[day]
        reference = next(r["reference_time_utc"] for r in audit["rows"]
                         if r["session_day_ny"] == day)
        anchor = _time(reference)
        rows = []
        for row in raw["rows"]:
            key = (day, row["symbol"])
            info = audit_by_key[key]
            prices = {_time(bar["t"]): _price(bar["c"]) for bar in row["ohlcv"]}
            baseline_stamp = anchor - MINUTE
            baseline = prices.get(baseline_stamp)
            changes = {}
            outcomes = {}
            for minutes in HORIZONS_MINUTES:
                horizon = str(minutes)
                target_stamp = anchor + dt.timedelta(minutes=minutes) - MINUTE
                target = prices.get(target_stamp)
                if baseline is None:
                    changes[horizon] = None
                    outcomes[horizon] = "MISSING_COMPLETED_REFERENCE_BAR"
                elif target is None:
                    changes[horizon] = None
                    outcomes[horizon] = "MISSING_EXACT_COMPLETED_HORIZON_BAR"
                else:
                    changes[horizon] = round((target / baseline - 1) * 100, 4)
                    outcomes[horizon] = "OBSERVED_DESCRIPTIVE_ONLY"
            rows.append({
                "symbol": row["symbol"],
                "strict_asof_group": info["strict_asof_group"],
                "legacy_group": info["legacy_group"],
                "reference_time_utc": anchor.isoformat(),
                "baseline_bar_start_utc": baseline_stamp.isoformat(),
                "baseline_completed_bar_close": baseline,
                "baseline_is_executable_quote": False,
                "changes_pct": changes,
                "horizon_status": outcomes,
            })
        counts = {
            horizon: {
                group: {
                    "candidates": sum(r["strict_asof_group"] == group for r in rows),
                    "observed": sum(r["strict_asof_group"] == group and
                                    r["changes_pct"][horizon] is not None for r in rows),
                    "missing": sum(r["strict_asof_group"] == group and
                                   r["changes_pct"][horizon] is None for r in rows),
                }
                for group in GROUPS
            }
            for horizon in map(str, HORIZONS_MINUTES)
        }
        results.append({
            "session_day_ny": day,
            "reference_time_utc": anchor.isoformat(),
            "candidate_count": len(rows),
            "rows": sorted(rows, key=lambda r: r["symbol"]),
            "observed_counts_by_horizon": counts,
        })
    return {
        "schema": "LUCA_V03_OFFLINE_STRICT_ASOF_SCORECARD_V1",
        "sessions": results,
        "session_count": len(results),
        "independent_sample_count_verified": 0,
        "aggregate_win_rate_computed": False,
        "reference_price_rule": "exact_bar_start_T_minus_1min_completed_at_T_zero_latency_assumed",
        "horizon_price_rule": "exact_bar_start_T_plus_h_minus_1min_completed_at_T_plus_h",
        "missing_horizon_imputed": False,
        "bar_publication_latency_verified": False,
        "signal_publication_latency_verified": False,
        "commitment_timestamp_externally_verified": False,
        "prediction_accuracy_verified": False,
        "statistical_significance_verified": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "orders_allowed": False,
        "real_trades_allowed": False,
        "warnings": sorted(set(audit["warnings"]) | {
            "ASOF_BOUNDARY_ASSUMES_ZERO_DATA_PUBLICATION_LATENCY",
            "HISTORICAL_COMPLETED_CLOSE_IS_NOT_EXECUTABLE_QUOTE",
            "DESCRIPTIVE_PRICE_CHANGES_ARE_NOT_VERIFIED_PREDICTIONS",
            "PER_SESSION_ONLY_NO_POOLED_INDEPENDENCE_CLAIM",
        }),
        "note_ko": "기준 시각 T에 이미 끝난 1분봉(T-1분)의 종가를 기준으로 T+5/15/30/60분까지 완료된 봉만 비교합니다. 자료가 빠지면 결과를 비워 둡니다. 데이터 수신 지연은 검증하지 않았고, 종가는 실제 매수 가능 가격이 아닙니다. 날짜별 결과를 합쳐 독립 표본 승률을 만들지 않습니다.",
    }
