"""Synthetic-only audit: signal readiness is not a verified execution opportunity.

Separate the frozen reference T, hypothetical signal completion, assumed
human review completion and scheduled NYSE close. Never move T, never turn a
future signal into a signal known at T, and never infer an executable quote.
Uses only the existing offline, fail-closed archive/commitment/calendar gates.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from mobile_outcomes import _time
from nyse_session_gate import EARLY_CLOSES_2026
from offline_decision_readiness import audit_decision_readiness

NY = ZoneInfo("America/New_York")
DEFAULT_REVIEW_SECONDS = (0, 1, 60)
MAX_REVIEW_SECONDS = 1800
MAX_TOTAL_SCENARIOS = 75


def _review_delays(values):
    if not isinstance(values, (tuple, list)) or not values:
        raise ValueError("MISSING_REVIEW_DELAY_SCENARIOS")
    if any(type(value) is not int or not 0 <= value <= MAX_REVIEW_SECONDS
           for value in values):
        raise ValueError("INVALID_REVIEW_DELAY_SECONDS")
    if len(set(values)) != len(values):
        raise ValueError("DUPLICATE_REVIEW_DELAY_SCENARIO")
    return tuple(sorted(values))


def _scheduled_close_utc(day_string):
    """Scheduled regular-session close, not live exchange status evidence."""
    day = dt.date.fromisoformat(day_string)
    local_close = dt.time(13, 0) if day in EARLY_CLOSES_2026 else dt.time(16, 0)
    return dt.datetime.combine(day, local_close, tzinfo=NY).astimezone(dt.timezone.utc)


def audit_signal_observation_window(
    sessions,
    publication_latencies_seconds=(0, 1, 30, 60),
    computation_delays_seconds=(0, 1, 30, 60, 120),
    review_delays_seconds=DEFAULT_REVIEW_SECONDS,
):
    """Describe *hypothetical* observation windows without a trading claim.

    Human-review delays are arbitrary scenarios, not measured human actions.
    The result contains no bid/ask, fill, order decision or return calculation.
    A signal first available after frozen T is NEVER counted as known at T.
    """
    review_delays = _review_delays(review_delays_seconds)
    # The underlying readiness gate also rejects invalid feed/compute values
    # and caps their pairwise combinations at 25.
    base = audit_decision_readiness(
        sessions, publication_latencies_seconds, computation_delays_seconds
    )
    if (base.get("validation_status") != "NOT_VALIDATED"
            or base.get("sec_status") != "SEC_UNVERIFIED"
            or base.get("operating_mode") != "NO_ORDERS"
            or base.get("orders_allowed") is not False):
        raise ValueError("UNSAFE_READINESS_REPORT")
    scenario_count = (len(base["publication_latencies_seconds_assumed"])
                      * len(base["computation_delays_seconds_assumed"])
                      * len(review_delays))
    if scenario_count > MAX_TOTAL_SCENARIOS:
        raise ValueError("TOO_MANY_OBSERVATION_SCENARIOS")

    days = []
    for session in base["sessions"]:
        day = session["session_day_ny"]
        reference = _time(session["reference_time_utc"])
        close = _scheduled_close_utc(day)
        if not reference < close:
            raise ValueError("REFERENCE_NOT_BEFORE_SCHEDULED_CLOSE")
        scenarios = []
        for ready_scenario in session["scenarios"]:
            for review in review_delays:
                rows = []
                for row in ready_scenario["rows"]:
                    first_ready = (None if row["earliest_hypothetical_signal_ready_utc"] is None
                                   else _time(row["earliest_hypothetical_signal_ready_utc"]))
                    # A signal already ready at T can be considered no earlier
                    # than T; a future signal remains explicitly ineligible at T.
                    considered = (max(first_ready, reference)
                                  + dt.timedelta(seconds=review)
                                  if first_ready is not None else None)
                    before_close = considered is not None and considered < close
                    frozen_eligible = row["signal_ready_by_reference"]
                    if first_ready is None:
                        status = "NO_ARCHIVED_SIGNAL"
                    elif not frozen_eligible:
                        status = "SIGNAL_NOT_READY_AT_FROZEN_REFERENCE"
                    elif not before_close:
                        status = "REVIEW_AT_OR_AFTER_SCHEDULED_CLOSE"
                    elif not row["exact_baseline_bar_present"]:
                        status = "MISSING_EXACT_REFERENCE_BAR"
                    else:
                        status = "HYPOTHETICAL_OBSERVATION_WINDOW_ONLY"
                    rows.append({
                        "symbol": row["symbol"],
                        "status": status,
                        "signal_ready_by_frozen_reference": frozen_eligible,
                        "signal_count_in_archive": row["signal_count_in_archive"],
                        "signal_count_ready_at_frozen_reference": row["known_signal_count"],
                        "first_hypothetical_signal_ready_utc": (
                            first_ready.isoformat() if first_ready is not None else None
                        ),
                        "first_hypothetical_review_complete_utc": (
                            considered.isoformat() if considered is not None else None
                        ),
                        "seconds_until_review_complete_from_reference": (
                            int((considered - reference).total_seconds())
                            if considered is not None else None
                        ),
                        "seconds_remaining_before_scheduled_close_after_review": (
                            int((close - considered).total_seconds())
                            if considered is not None else None
                        ),
                        "review_completes_before_scheduled_close": before_close,
                        "exact_reference_bar_present": row["exact_baseline_bar_present"],
                        "executable_quote_verified": False,
                        "actual_review_time_measured": False,
                        "order_ready": False,
                        "orders_allowed": False,
                    })
                scenarios.append({
                    "assumed_publication_latency_seconds":
                        ready_scenario["assumed_publication_latency_seconds"],
                    "assumed_signal_computation_seconds":
                        ready_scenario["assumed_signal_computation_seconds"],
                    "assumed_human_review_seconds": review,
                    "candidate_count": len(rows),
                    "frozen_reference_signal_count": sum(
                        r["signal_ready_by_frozen_reference"] for r in rows
                    ),
                    "hypothetical_window_only_count": sum(
                        r["status"] == "HYPOTHETICAL_OBSERVATION_WINDOW_ONLY"
                        for r in rows
                    ),
                    "post_reference_signal_count": sum(
                        r["status"] == "SIGNAL_NOT_READY_AT_FROZEN_REFERENCE"
                        for r in rows
                    ),
                    "rows": sorted(rows, key=lambda r: r["symbol"]),
                })
        days.append({
            "session_day_ny": day,
            "reference_time_utc": reference.isoformat(),
            "scheduled_close_utc": close.isoformat(),
            "scheduled_close_live_verified": False,
            "candidate_count": session["candidate_count"],
            "scenarios": scenarios,
        })
    return {
        "schema": "LUCA_V03_OFFLINE_SIGNAL_OBSERVATION_WINDOW_V1",
        "sessions": days,
        "session_count": len(days),
        "scenario_combinations_per_session": scenario_count,
        "human_review_delays_seconds_assumed": list(review_delays),
        "human_review_time_measured": False,
        "actual_market_open_verified": False,
        "scheduled_close_live_verified": False,
        "executable_bid_ask_verified": False,
        "liquidity_and_fill_verified": False,
        "order_routing_latency_measured": False,
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
        "warnings": sorted(set(base["warnings"]) | {
            "ASSUMED_HUMAN_REVIEW_TIME_NOT_MEASURED",
            "SCHEDULED_CLOSE_NOT_LIVE_VERIFIED",
            "FUTURE_SIGNAL_NOT_PROMOTED_TO_FROZEN_REFERENCE",
            "HYPOTHETICAL_OBSERVATION_IS_NOT_EXECUTABILITY",
            "NO_BID_ASK_ORDERBOOK_OR_FILL_EVIDENCE",
            "NO_POOLED_INDEPENDENT_WIN_RATE",
        }),
        "note_ko": (
            "고정된 기준 시각에 신호를 알 수 있었는지와 가정한 검토시간 뒤 "
            "예정 장 마감까지 시간이 남는지를 따로 계산합니다. 기준 시각 뒤에 "
            "나온 신호를 과거 신호로 인정하지 않습니다. 장 마감은 예정 시간일 뿐 "
            "실제 개장 확인이 아니며 호가·체결·실제 수익은 전혀 검증하지 않습니다."
        ),
    }
