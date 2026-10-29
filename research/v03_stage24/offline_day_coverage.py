"""Offline observation-day coverage checks for descriptive cohort scorecards.

An explicitly supplied day ledger is required. No dates are inferred from signals.
This is an integrity/coverage summary, not a statistical significance test.
"""
from __future__ import annotations
import datetime as dt
from offline_cohort_scorecard import scorecard

MIN_DISTINCT_DAYS = 10  # Conservative heuristic, not a validated sample-size calculation.


def summarize_day_coverage(raw, manifest, day_ledger):
    if not isinstance(day_ledger, list) or not day_ledger:
        raise ValueError("MISSING_DAY_LEDGER")
    expected_symbols = {row["symbol"] for row in raw.get("rows", [])}
    seen = set()
    by_day = {}
    for item in day_ledger:
        if not isinstance(item, dict):
            raise ValueError("INVALID_LEDGER_ENTRY")
        day = item.get("observation_date_utc")
        symbol = item.get("symbol")
        if not isinstance(day, str) or not isinstance(symbol, str):
            raise ValueError("INVALID_LEDGER_ENTRY")
        try:
            parsed = dt.date.fromisoformat(day)
        except ValueError as exc:
            raise ValueError("INVALID_OBSERVATION_DATE") from exc
        if parsed.isoformat() != day:
            raise ValueError("INVALID_OBSERVATION_DATE")
        if symbol not in expected_symbols:
            raise ValueError("UNKNOWN_LEDGER_SYMBOL")
        pair = (day, symbol)
        if pair in seen:
            raise ValueError("DUPLICATE_DAY_SYMBOL")
        seen.add(pair)
        by_day.setdefault(day, set()).add(symbol)
    if {symbol for _, symbol in seen} != expected_symbols:
        raise ValueError("LEDGER_CANDIDATE_COVERAGE_MISMATCH")
    result = scorecard(raw, manifest)
    distinct_days = len(by_day)
    result["day_coverage"] = {
        "distinct_observation_days": distinct_days,
        "candidate_day_pairs": len(seen),
        "candidates_per_day": {day: len(symbols) for day, symbols in sorted(by_day.items())},
        "min_distinct_days_heuristic": MIN_DISTINCT_DAYS,
        "day_count_warning": "TOO_FEW_OBSERVATION_DAYS" if distinct_days < MIN_DISTINCT_DAYS else None,
        "observation_days_externally_verified": False,
        "ledger_represents_actual_trading_days_verified": False,
        "note_ko": "날짜는 제공된 장부를 그대로 집계합니다. 실제 거래일인지 외부 확인하지 않았고, 같은 종목의 여러 날 기록이 독립 표본이라는 뜻도 아닙니다.",
    }
    return result
