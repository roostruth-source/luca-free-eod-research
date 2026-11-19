"""Classify bounded regular or pre-market IEX price freshness for V10.

The upstream V0.3 enrichment remains regular-session only.  V10 may separately
retain a pre-market observation when both the IEX trade and quote timestamps are
recent.  IEX is one exchange, not a full-market NBBO, so this context is only a
watchlist input and can never authorize an order.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
import math
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
MAX_AGE_SECONDS = 600
FRESH_REGULAR = "WATCH_ONLY_FRESH_IEX"
FRESH_PREMARKET = "WATCH_ONLY_FRESH_IEX_PREMARKET"
PENDING = "PENDING_STALE_OR_MISSING"


def _timestamp(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def market_session(asof: datetime) -> str:
    if not isinstance(asof, datetime) or asof.tzinfo is None:
        raise ValueError("price_context_asof_timezone_required")
    local = asof.astimezone(ET)
    if local.weekday() >= 5:
        return "CLOSED"
    if time(4, 0) <= local.time() < time(9, 30):
        return "PREMARKET"
    if time(9, 30) <= local.time() < time(16, 0):
        return "REGULAR"
    if time(16, 0) <= local.time() < time(20, 0):
        return "AFTER_HOURS"
    return "OVERNIGHT_OR_CLOSED"


def classify(row: dict, asof: datetime) -> dict:
    if not isinstance(row, dict):
        raise ValueError("price_context_row_required")
    session = market_session(asof)
    now = asof.astimezone(timezone.utc)
    trade_time = _timestamp(row.get("iex_last_trade_utc"))
    quote_time = _timestamp(row.get("iex_quote_utc"))
    trade_age = (now - trade_time).total_seconds() if trade_time else None
    quote_age = (now - quote_time).total_seconds() if quote_time else None
    trade_future = trade_age is not None and trade_age < 0
    quote_future = quote_age is not None and quote_age < 0
    trade_fresh = trade_age is not None and 0 <= trade_age <= MAX_AGE_SECONDS
    quote_fresh = quote_age is not None and 0 <= quote_age <= MAX_AGE_SECONDS
    spread = row.get("iex_quote_spread_pct")
    valid_spread = (type(spread) in (int, float) and math.isfinite(spread)
                    and 0 <= spread <= 1000)
    band = row.get("price_band_0_20_to_20") is True

    if (session == "REGULAR" and row.get("research_status") == FRESH_REGULAR
            and trade_fresh and quote_fresh and valid_spread and band):
        status = FRESH_REGULAR
    elif session == "PREMARKET" and trade_fresh and quote_fresh and valid_spread and band:
        status = FRESH_PREMARKET
    else:
        status = PENDING

    return {
        "status": status,
        "market_session": session,
        "trade_timestamp_utc": trade_time.isoformat() if trade_time and not trade_future else None,
        "quote_timestamp_utc": quote_time.isoformat() if quote_time and not quote_future else None,
        "trade_age_seconds": round(trade_age) if trade_age is not None and not trade_future else None,
        "quote_age_seconds": round(quote_age) if quote_age is not None and not quote_future else None,
        "trade_fresh": trade_fresh,
        "quote_fresh": quote_fresh,
        "full_market_quote_verified": False,
        "source": "ALPACA_IEX_SINGLE_EXCHANGE_NOT_SIP",
        "rejection_reasons": (["FUTURE_TRADE_TIMESTAMP_REJECTED"] if trade_future else [])
                             + (["FUTURE_QUOTE_TIMESTAMP_REJECTED"] if quote_future else []),
        "NO_ORDERS": True,
    }
