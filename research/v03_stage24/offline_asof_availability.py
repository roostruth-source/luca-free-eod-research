"""Offline as-of availability audit for 1-minute bar-start timestamps.

Detects a subtle look-ahead: the close of a bar stamped 10:05 is not
available at 10:05; it becomes observable only after that minute ends.
This is diagnostic only; it never authorizes trading or prediction claims.
"""
from __future__ import annotations

import datetime as dt
from mobile_outcomes import _time, _price
from offline_multisession_audit import audit_session_bundle

BAR_DURATION = dt.timedelta(minutes=1)


def audit_asof_availability(sessions):
    """Check as-of signal group and baseline close against frozen reference.

    The legacy scorecard groups signal_bar_start <= reference_time and uses
    close[reference_time] as a descriptive baseline. Both can use a bar that
    was still forming at reference_time. Keep legacy output untouched; return
    an explicit conservative diagnostic alongside it.
    """
    base = audit_session_bundle(sessions)
    by_day = {item["session_day_ny"]: item for item in sessions}
    details = []
    warnings = set(base["warnings"])
    legacy_membership_leaks = 0
    baseline_not_yet_closed = 0
    for session in base["sessions"]:
        anchor = _time(session["reference_time_utc"])
        raw = by_day[session["session_day_ny"]]["raw"]
        # The scorecard's groups contain aggregate counts; use the same
        # legacy grouping rule on each validated raw row.
        for row in raw["rows"]:
            signals = [_time(entry["signal"]["signal_bar_start_utc"])
                       for entry in row["signals"]]
            legacy_signal = any(stamp <= anchor for stamp in signals)
            eligible_signal = any(stamp + BAR_DURATION <= anchor for stamp in signals)
            unclosed_signals = sum(stamp <= anchor < stamp + BAR_DURATION
                                   for stamp in signals)
            bars = [(_time(bar["t"]), _price(bar["c"])) for bar in row["ohlcv"]]
            reference_bar = [price for stamp, price in bars if stamp == anchor]
            # Last fully closed bar as of the reference instant. This is a
            # historical close, NOT an executable quote or fill price.
            eligible_bars = [(stamp, price) for stamp, price in bars
                             if stamp + BAR_DURATION <= anchor]
            latest = max(eligible_bars, default=None, key=lambda item: item[0])
            if reference_bar:
                baseline_not_yet_closed += 1
            if legacy_signal and not eligible_signal:
                legacy_membership_leaks += 1
            if unclosed_signals:
                warnings.add("REFERENCE_MINUTE_SIGNAL_NOT_YET_CLOSED")
            if reference_bar:
                warnings.add("REFERENCE_BAR_CLOSE_NOT_AVAILABLE_AT_BAR_START")
            if not latest:
                warnings.add("NO_COMPLETED_BAR_AT_REFERENCE")
            details.append({
                "session_day_ny": session["session_day_ny"],
                "symbol": row["symbol"],
                "reference_time_utc": anchor.isoformat(),
                "legacy_group": ("signal_by_reference_time" if legacy_signal
                                 else "no_signal_by_reference_time"),
                "strict_asof_group": ("signal_known_by_reference_time" if eligible_signal
                                      else "no_signal_known_by_reference_time"),
                "unclosed_signal_count_at_reference": unclosed_signals,
                "signal_known_at_reference_count": sum(
                    stamp + BAR_DURATION <= anchor for stamp in signals),
                "legacy_reference_bar_close_used": bool(reference_bar),
                "legacy_reference_bar_close_asof_available": False if reference_bar else None,
                "latest_completed_bar_start_utc": latest[0].isoformat() if latest else None,
                "latest_completed_bar_close": latest[1] if latest else None,
                "latest_completed_close_is_executable_price": False,
            })
    return {
        "schema": "LUCA_V03_OFFLINE_ASOF_AVAILABILITY_AUDIT_V1",
        "rows": sorted(details, key=lambda r: (r["session_day_ny"], r["symbol"])),
        "legacy_signal_membership_not_asof_count": legacy_membership_leaks,
        "legacy_reference_bar_not_asof_count": baseline_not_yet_closed,
        "reference_bar_duration_seconds_assumed": 60,
        "asof_signal_availability_externally_verified": False,
        "raw_collection_time_externally_verified": False,
        "independent_sample_count_verified": 0,
        "prediction_accuracy_verified": False,
        "statistical_significance_verified": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "orders_allowed": False,
        "real_trades_allowed": False,
        "warnings": sorted(warnings | {
            "STRICT_ASOF_IS_STRUCTURAL_ONLY_NOT_PROVEN_PRE_REGISTRATION",
            "HISTORICAL_COMPLETED_CLOSE_IS_NOT_EXECUTABLE_QUOTE",
            "LEGACY_SCORECARD_REMAINS_DESCRIPTIVE_NOT_ASOF_VERIFIED",
        }),
        "note_ko": "1분봉 시각은 봉이 시작된 시간입니다. 10:05 봉 종가와 그 봉으로 만든 신호는 10:05 정각에 알 수 없습니다. 마지막으로 완료된 봉은 따로 표시하지만 실제 매수 가능 가격이나 검증된 예측력이 아닙니다.",
    }
