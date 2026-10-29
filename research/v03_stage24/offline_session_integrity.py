"""Offline audit of *claimed* UTC observation dates; never validates sessions.

Reuse the existing 2026 NYSE scheduled calendar without network access.
A date-only UTC ledger cannot establish New York session dates or independent
observations. This is a diagnostic attached to the descriptive scorecard.
"""
from __future__ import annotations

import datetime as dt
import hashlib
from collections import Counter
from zoneinfo import ZoneInfo

from mobile_outcomes import _time
from offline_reference_commitment import SCHEMA, canonical
from nyse_session_gate import EARLY_CLOSES_2026, SCHEDULED_HOLIDAYS_2026

NY = ZoneInfo("America/New_York")


def _calendar_label(day):
    """Offline scheduled-calendar classification, NOT official live confirmation."""
    if day.year != 2026:
        return "UNSUPPORTED_CALENDAR_YEAR"
    if day.weekday() >= 5:
        return "WEEKEND"
    if day in SCHEDULED_HOLIDAYS_2026:
        return "SCHEDULED_NYSE_HOLIDAY"
    if day in EARLY_CLOSES_2026:
        return "SCHEDULED_EARLY_CLOSE"
    return "SCHEDULED_WEEKDAY_NOT_LIVE_VERIFIED"


def audit_day_ledger(manifest, day_ledger):
    if not isinstance(manifest, dict) or not isinstance(manifest.get("payload"), dict):
        raise ValueError("INVALID_MANIFEST")
    payload = manifest["payload"]
    if (payload.get("schema") != SCHEMA or
            payload.get("validation_status") != "NOT_VALIDATED" or
            payload.get("orders_allowed") is not False):
        raise ValueError("UNSAFE_MANIFEST")
    expected = payload.get("symbols")
    if not isinstance(expected, list) or not expected or any(
            not isinstance(s, str) or not s for s in expected) or len(expected) != len(set(expected)):
        raise ValueError("INVALID_MANIFEST_SYMBOLS")
    digest = hashlib.sha256(canonical(payload).encode("utf8")).hexdigest()
    if manifest.get("sha256") != digest:
        raise ValueError("COMMITMENT_HASH_MISMATCH")
    anchor = _time(payload.get("reference_time_utc"))
    if not isinstance(day_ledger, list) or not day_ledger:
        raise ValueError("MISSING_DAY_LEDGER")
    anchor_utc_day = anchor.date().isoformat()
    anchor_ny_day = anchor.astimezone(NY).date().isoformat()
    counts = Counter()
    symbols = set()
    dates = set()
    pairs = set()
    for item in day_ledger:
        if not isinstance(item, dict):
            raise ValueError("INVALID_LEDGER_ENTRY")
        day, symbol = item.get("observation_date_utc"), item.get("symbol")
        if not isinstance(day, str) or not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("INVALID_LEDGER_ENTRY")
        try:
            parsed = dt.date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError("INVALID_OBSERVATION_DATE") from exc
        if parsed.isoformat() != day:
            raise ValueError("INVALID_OBSERVATION_DATE")
        if symbol not in expected:
            raise ValueError("UNKNOWN_LEDGER_SYMBOL")
        if (day, symbol) in pairs:
            raise ValueError("DUPLICATE_DAY_SYMBOL")
        pairs.add((day, symbol))
        counts[symbol] += 1
        dates.add(day)
        symbols.add(symbol)

    if symbols != set(expected):
        raise ValueError("LEDGER_CANDIDATE_COVERAGE_MISMATCH")
    calendar = {day: _calendar_label(dt.date.fromisoformat(day))
                for day in sorted(dates)}
    repeated = {symbol: count for symbol, count in sorted(counts.items())
                if count > 1}
    off_anchor = sorted(day for day in dates if day != anchor_utc_day)
    unsafe_calendar = sorted(day for day, status in calendar.items()
                             if status in ("WEEKEND", "SCHEDULED_NYSE_HOLIDAY",
                                           "UNSUPPORTED_CALENDAR_YEAR"))
    warnings = ["UTC_DATE_ONLY_CANNOT_PROVE_NY_SESSION",
                "NO_EXTERNAL_MARKET_SESSION_VERIFICATION"]
    if repeated:
        warnings.append("REPEATED_SYMBOL_DAY_PAIRS_NOT_INDEPENDENT")
    if off_anchor:
        warnings.append("SINGLE_REFERENCE_ANCHOR_CANNOT_VERIFY_OTHER_DAYS")
    if unsafe_calendar:
        warnings.append("OFFLINE_CALENDAR_REJECTS_CLAIMED_DATES")
    if any(value == "SCHEDULED_EARLY_CLOSE" for value in calendar.values()):
        warnings.append("EARLY_CLOSE_REQUIRES_SESSION_HORIZON_CHECK")

    return {
        "schema": "LUCA_V03_OFFLINE_DAY_INTEGRITY_AUDIT_V1",
        "commitment_sha256": digest,
        "commitment_timestamp_externally_verified": False,
        "reference_time_utc": anchor.isoformat(),
        "reference_utc_date": anchor_utc_day,
        "reference_session_date_ny": anchor_ny_day,
        "claimed_distinct_utc_dates": len(dates),
        "claimed_symbol_date_pairs": len(pairs),
        "unique_symbols": len(symbols),
        "repeated_symbols": repeated,
        "extra_symbol_date_pairs_beyond_first": sum(count - 1 for count in counts.values()),
        "off_anchor_utc_dates": off_anchor,
        "offline_scheduled_calendar_by_utc_date": calendar,
        "calendar_rejected_utc_dates": unsafe_calendar,
        "calendar_date_basis": "UTC_DATE_ONLY_NOT_NY_SESSION",
        "independent_session_count_verified": 0,
        "independent_sample_count_verified": 0,
        "actual_market_sessions_verified": False,
        "predictive_accuracy_verified": False,
        "statistical_significance_verified": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "orders_allowed": False,
        "real_trades_allowed": False,
        "warnings": warnings,
        "note_ko": "UTC 날짜 장부는 실제 뉴욕 거래일과 독립 관찰을 증명하지 못합니다. 2026년 예정 휴장일만 오프라인으로 분류하며 임시 휴장과 실시간 개장 여부는 확인하지 않습니다. 같은 종목의 여러 날짜 기록을 별개의 검증 표본으로 세지 않습니다.",
    }
