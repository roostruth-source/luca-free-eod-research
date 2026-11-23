"""NYSE official full-day closure regression; no extrapolation to other years."""
import unittest
from datetime import date
from prospective_outcomes import _known_closed_equity_session, _validate_daily_bar_series, _same_day_premarket_gate
from zoneinfo import ZoneInfo
from datetime import datetime

class OfficialClosureTests(unittest.TestCase):
    def test_nyse_2026_thanksgiving_closed_and_black_friday_open(self):
        self.assertTrue(_known_closed_equity_session(date(2026, 11, 26)))
        self.assertFalse(_known_closed_equity_session(date(2026, 11, 27)))
        self.assertFalse(_known_closed_equity_session(date(2026, 11, 11)))

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
