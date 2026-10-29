"""Offline official-calendar gate tests; no internet is used."""
import datetime as dt
import unittest

from nyse_session_gate import (
    CALENDAR_MARKERS, CALENDAR_URL, STATUS_URL, verify_nyse_session,
)


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 29, 14, 0, tzinfo=UTC)


class Response:
    status = 200

    def __init__(self, url, text):
        self.url = url
        self.payload = text.encode("utf8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, count=-1):
        return self.payload[:count]


def official_opener(extra_status="", bad_calendar=False, fail=False, calls=None):
    calendar = " | ".join(CALENDAR_MARKERS)
    if bad_calendar:
        calendar = "not a calendar"
    status = "Market Status System Status Normal " + extra_status

    def open_fake(request, timeout):
        if calls is not None:
            calls.append(request.full_url)
        if request.get_method() != "GET":
            raise AssertionError("OFFICIAL_CHECK_MUST_BE_GET")
        if fail:
            raise OSError("synthetic offline failure")
        if request.full_url == CALENDAR_URL:
            return Response(CALENDAR_URL, calendar)
        if request.full_url == STATUS_URL:
            return Response(STATUS_URL, status)
        raise AssertionError("UNEXPECTED_OFFICIAL_URL")
    return open_fake


class NyseSessionGateTests(unittest.TestCase):
    def test_regular_weekday_needs_two_live_official_sources(self):
        calls = []
        result = verify_nyse_session(
            dt.date(2026, 10, 29), NOW, official_opener(calls=calls))
        self.assertTrue(result["official_sources_live_verified"])
        self.assertTrue(result["regular_session_confirmed"])
        self.assertEqual(calls, [CALENDAR_URL, STATUS_URL])
        self.assertFalse(result["orders_allowed"])

    def test_scheduled_holiday_is_distinct_and_blocks_before_network(self):
        calls = []
        with self.assertRaisesRegex(ValueError, "NYSE_SCHEDULED_HOLIDAY:THANKSGIVING"):
            verify_nyse_session(
                dt.date(2026, 11, 26), NOW, official_opener(calls=calls))
        self.assertEqual(calls, [])

    def test_special_closure_notice_is_distinct_and_blocks(self):
        notice = "October 30, 2026 special market closure; market closed"
        with self.assertRaisesRegex(ValueError, "NYSE_SPECIAL_CLOSURE"):
            verify_nyse_session(
                dt.date(2026, 10, 30), NOW,
                official_opener(extra_status=notice))

    def test_weekend_blocks_before_network(self):
        calls = []
        with self.assertRaisesRegex(ValueError, "NYSE_WEEKEND"):
            verify_nyse_session(
                dt.date(2026, 10, 31), NOW, official_opener(calls=calls))
        self.assertEqual(calls, [])

    def test_unavailable_official_source_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "OFFICIAL_NYSE_SOURCE_UNAVAILABLE"):
            verify_nyse_session(
                dt.date(2026, 10, 29), NOW, official_opener(fail=True))

    def test_unrecognized_official_calendar_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "OFFICIAL_NYSE_CALENDAR_UNRECOGNIZED"):
            verify_nyse_session(
                dt.date(2026, 10, 29), NOW,
                official_opener(bad_calendar=True))

    def test_unknown_year_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_NYSE_CALENDAR_YEAR"):
            verify_nyse_session(
                dt.date(2027, 1, 4), NOW, official_opener())

    def test_official_early_close_is_labeled_not_full_holiday(self):
        result = verify_nyse_session(
            dt.date(2026, 11, 27), NOW, official_opener())
        self.assertTrue(result["early_close"])
        self.assertIn("1PM_ET", result["early_close_reason"])


if __name__ == "__main__":
    unittest.main()
