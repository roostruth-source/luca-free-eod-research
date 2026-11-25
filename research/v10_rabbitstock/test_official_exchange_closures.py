"""NYSE official full-day closure regression; no extrapolation to other years."""
import unittest
from datetime import date
from prospective_outcomes import _known_closed_equity_session, _validate_daily_bar_series, _same_day_premarket_gate, _daily_bar_completed_at
from zoneinfo import ZoneInfo
from datetime import datetime

class OfficialClosureTests(unittest.TestCase):
    def test_nyse_2026_thanksgiving_closed_and_black_friday_open(self):
        self.assertTrue(_known_closed_equity_session(date(2026, 11, 26)))
        self.assertFalse(_known_closed_equity_session(date(2026, 11, 27)))
        self.assertFalse(_known_closed_equity_session(date(2026, 11, 11)))

    def test_nyse_2027_and_2028_official_closures_are_frozen(self):
        for day in (date(2027, 1, 1), date(2027, 3, 26), date(2027, 12, 24),
                    date(2028, 4, 14), date(2028, 7, 4), date(2028, 12, 25)):
            self.assertTrue(_known_closed_equity_session(day))
        self.assertFalse(_known_closed_equity_session(date(2027, 11, 26)))
        self.assertFalse(_known_closed_equity_session(date(2028, 7, 3)))

    def test_2026_official_early_closes_use_1315_et_buffer(self):
        et = ZoneInfo("America/New_York")
        for day in (date(2026, 11, 27), date(2026, 12, 24)):
            self.assertFalse(_known_closed_equity_session(day))
            self.assertFalse(_daily_bar_completed_at(datetime(day.year, day.month, day.day, 13, 14, tzinfo=et)))
            self.assertTrue(_daily_bar_completed_at(datetime(day.year, day.month, day.day, 13, 15, tzinfo=et)))

    def test_2027_and_2028_official_early_closes_use_1315_et_buffer(self):
        et = ZoneInfo("America/New_York")
        for day in (date(2027, 11, 26), date(2028, 7, 3), date(2028, 11, 24)):
            self.assertFalse(_daily_bar_completed_at(datetime(day.year, day.month, day.day, 13, 14, tzinfo=et)))
            self.assertTrue(_daily_bar_completed_at(datetime(day.year, day.month, day.day, 13, 15, tzinfo=et)))

    def test_regular_day_and_holiday_eve_do_not_inherit_early_close(self):
        et = ZoneInfo("America/New_York")
        for day in (date(2026, 11, 25), date(2026, 12, 23), date(2026, 7, 2)):
            self.assertFalse(_daily_bar_completed_at(datetime(day.year, day.month, day.day, 13, 15, tzinfo=et)))
            self.assertTrue(_daily_bar_completed_at(datetime(day.year, day.month, day.day, 16, 15, tzinfo=et)))

    def test_holiday_daily_bar_rejected(self):
        row = {"session_date": "2026-11-26", "o": 1.0, "h": 1.1, "l": 0.9, "c": 1.0}
        with self.assertRaisesRegex(ValueError, "non_trading_closed_daily_session"):
            _validate_daily_bar_series("ABC", [row], date(2026, 11, 27))

    def test_holiday_premarket_never_same_day(self):
        observed = datetime(2026, 11, 26, 8, 0, tzinfo=ZoneInfo("America/New_York"))
        result = _same_day_premarket_gate(
            {"observation_status": "FRESH_PREMARKET_WATCH_ONLY"}, observed)
        self.assertFalse(result["eligible"])
        self.assertEqual(result["reason"], "NEXT_SESSION_CLOSED_EQUITY_HOLIDAY")

if __name__ == "__main__":
    unittest.main()
