"""Fail-closed NYSE session check using live official NYSE pages.

This is not a market-data call.  A future approved run must confirm the
official holiday calendar and market-status page before any IEX request.  The
2026 scheduled closures below are transcribed from the official NYSE calendar;
an unreachable or unrecognizable live source blocks the run.
"""
from __future__ import annotations

import datetime as dt
import html
import re
from urllib.parse import urlparse
from urllib.request import Request, urlopen


CALENDAR_URL = "https://www.nyse.com/trade/hours-calendars"
STATUS_URL = "https://www.nyse.com/market-status/history"
MAX_SOURCE_BYTES = 750_000

SCHEDULED_HOLIDAYS_2026 = {
    dt.date(2026, 1, 1): "NEW_YEARS_DAY",
    dt.date(2026, 1, 19): "MARTIN_LUTHER_KING_JR_DAY",
    dt.date(2026, 2, 16): "WASHINGTONS_BIRTHDAY",
    dt.date(2026, 4, 3): "GOOD_FRIDAY",
    dt.date(2026, 5, 25): "MEMORIAL_DAY",
    dt.date(2026, 6, 19): "JUNETEENTH",
    dt.date(2026, 7, 3): "INDEPENDENCE_DAY_OBSERVED",
    dt.date(2026, 9, 7): "LABOR_DAY",
    dt.date(2026, 11, 26): "THANKSGIVING_DAY",
    dt.date(2026, 12, 25): "CHRISTMAS_DAY",
}

EARLY_CLOSES_2026 = {
    dt.date(2026, 11, 27): "DAY_AFTER_THANKSGIVING_1PM_ET",
    dt.date(2026, 12, 24): "CHRISTMAS_EVE_1PM_ET",
}

CALENDAR_MARKERS = (
    "All NYSE markets observe U.S. holidays",
    "Thursday, January 1",
    "Monday, January 19",
    "Monday, February 16",
    "Friday, April 3",
    "Monday, May 25",
    "Friday, June 19",
    "Friday, July 3",
    "Monday, September 7",
    "Thursday, November 26",
    "Friday, December 25",
    "Friday, November 27, 2026",
    "Thursday, December 24, 2026",
)
STATUS_MARKERS = ("Market Status", "System Status")


def _read_official(url, opener):
    request = Request(url, method="GET", headers={
        "User-Agent": "luca-v03-research-calendar-check/1.0",
        "Accept": "text/html",
    })
    try:
        with opener(request, timeout=12) as response:
            status = getattr(response, "status", None)
            final_url = response.geturl()
            payload = response.read(MAX_SOURCE_BYTES + 1)
    except Exception as exc:
        raise ValueError("OFFICIAL_NYSE_SOURCE_UNAVAILABLE") from exc
    if status != 200:
        raise ValueError("OFFICIAL_NYSE_SOURCE_HTTP_STATUS")
    parsed = urlparse(final_url)
    if parsed.scheme != "https" or parsed.hostname not in {"nyse.com", "www.nyse.com"}:
        raise ValueError("OFFICIAL_NYSE_SOURCE_REDIRECTED")
    if not 0 < len(payload) <= MAX_SOURCE_BYTES:
        raise ValueError("OFFICIAL_NYSE_SOURCE_SIZE")
    try:
        text = payload.decode("utf8")
    except UnicodeDecodeError as exc:
        raise ValueError("OFFICIAL_NYSE_SOURCE_ENCODING") from exc
    normalized = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text)))
    return normalized


def _target_date_forms(day):
    return (
        day.isoformat(), day.strftime("%m/%d/%Y"),
        f"{day.strftime('%B')} {day.day}, {day.year}",
    )


def _has_special_closure_notice(text, day):
    closure = re.compile(
        r"(?:special.{0,60}(?:clos|suspend)|market.{0,60}(?:closed|closure)|"
        r"will not (?:open|be open)|trading.{0,60}suspend)", re.IGNORECASE)
    for form in _target_date_forms(day):
        start = 0
        while True:
            index = text.find(form, start)
            if index < 0:
                break
            context = text[max(0, index - 240):index + len(form) + 240]
            if closure.search(context):
                return True
            start = index + len(form)
    return False


def verify_nyse_session(session_day, now, opener=urlopen):
    """Return official session evidence or raise before any market-data call."""
    if type(session_day) is not dt.date:
        raise ValueError("BAD_NYSE_SESSION_DAY")
    if type(now) is not dt.datetime or now.tzinfo is None:
        raise ValueError("AWARE_NYSE_CHECK_TIME_REQUIRED")
    if session_day.year != 2026:
        raise ValueError("UNSUPPORTED_NYSE_CALENDAR_YEAR")
    if session_day.weekday() >= 5:
        raise ValueError("NYSE_WEEKEND")
    holiday = SCHEDULED_HOLIDAYS_2026.get(session_day)
    if holiday:
        raise ValueError("NYSE_SCHEDULED_HOLIDAY:" + holiday)

    calendar = _read_official(CALENDAR_URL, opener)
    if any(marker not in calendar for marker in CALENDAR_MARKERS):
        raise ValueError("OFFICIAL_NYSE_CALENDAR_UNRECOGNIZED")
    status = _read_official(STATUS_URL, opener)
    if not all(marker in status for marker in STATUS_MARKERS):
        raise ValueError("OFFICIAL_NYSE_STATUS_UNRECOGNIZED")
    if (_has_special_closure_notice(calendar, session_day) or
            _has_special_closure_notice(status, session_day)):
        raise ValueError("NYSE_SPECIAL_CLOSURE")

    return {
        "schema": "LUCA_V03_OFFICIAL_NYSE_SESSION_GATE_V1",
        "session_day_ny": session_day.isoformat(),
        "checked_at_utc": now.astimezone(dt.timezone.utc).isoformat(),
        "official_calendar_url": CALENDAR_URL,
        "official_status_url": STATUS_URL,
        "official_sources_live_verified": True,
        "scheduled_holiday": False,
        "special_closure_notice_found": False,
        "early_close": session_day in EARLY_CLOSES_2026,
        "early_close_reason": EARLY_CLOSES_2026.get(session_day),
        "regular_session_confirmed": True,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "real_trades_allowed": False,
        "orders_allowed": False,
    }
