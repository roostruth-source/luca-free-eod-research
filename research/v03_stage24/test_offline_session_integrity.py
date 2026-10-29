"""Synthetic calendar and repeated-symbol integrity tests. No network calls."""
import unittest

from offline_session_integrity import audit_day_ledger
from test_offline_cohort_scorecard import setup_case


class OfflineSessionIntegrityTests(unittest.TestCase):
    def setUp(self):
        _, self.manifest = setup_case()

    def ledger(self, *dates):
        return [{"observation_date_utc": day, "symbol": symbol}
                for day in dates for symbol in ("TESTA", "NO_SIGNAL")]

    def test_reference_day_is_utc_and_new_york_explicit(self):
        result = audit_day_ledger(self.manifest, self.ledger("2026-10-29"))
        self.assertEqual(result["reference_utc_date"], "2026-10-29")
        self.assertEqual(result["reference_session_date_ny"], "2026-10-29")
        self.assertEqual(result["offline_scheduled_calendar_by_utc_date"]["2026-10-29"],
                         "SCHEDULED_WEEKDAY_NOT_LIVE_VERIFIED")
        self.assertEqual(result["independent_session_count_verified"], 0)

    def test_weekend_flagged_without_network(self):
        result = audit_day_ledger(self.manifest, self.ledger("2026-10-31"))
        self.assertEqual(result["offline_scheduled_calendar_by_utc_date"]["2026-10-31"], "WEEKEND")
        self.assertIn("OFFLINE_CALENDAR_REJECTS_CLAIMED_DATES", result["warnings"])

    def test_thanksgiving_flagged(self):
        result = audit_day_ledger(self.manifest, self.ledger("2026-11-26"))
        self.assertEqual(result["offline_scheduled_calendar_by_utc_date"]["2026-11-26"],
                         "SCHEDULED_NYSE_HOLIDAY")

    def test_independence_day_observed_flagged(self):
        result = audit_day_ledger(self.manifest, self.ledger("2026-07-03"))
        self.assertEqual(result["offline_scheduled_calendar_by_utc_date"]["2026-07-03"],
                         "SCHEDULED_NYSE_HOLIDAY")

    def test_early_close_separate_from_holiday(self):
        result = audit_day_ledger(self.manifest, self.ledger("2026-11-27"))
        self.assertEqual(result["offline_scheduled_calendar_by_utc_date"]["2026-11-27"],
                         "SCHEDULED_EARLY_CLOSE")
        self.assertIn("EARLY_CLOSE_REQUIRES_SESSION_HORIZON_CHECK", result["warnings"])
        self.assertNotIn("2026-11-27", result["calendar_rejected_utc_dates"])

    def test_other_year_not_assumed_open(self):
        result = audit_day_ledger(self.manifest, self.ledger("2027-01-04"))
        self.assertEqual(result["offline_scheduled_calendar_by_utc_date"]["2027-01-04"],
                         "UNSUPPORTED_CALENDAR_YEAR")
        self.assertIn("2027-01-04", result["calendar_rejected_utc_dates"])

    def test_repeated_symbols_not_independent(self):
        result = audit_day_ledger(self.manifest, self.ledger("2026-10-28", "2026-10-29"))
        self.assertEqual(result["claimed_symbol_date_pairs"], 4)
        self.assertEqual(result["unique_symbols"], 2)
        self.assertEqual(result["extra_symbol_date_pairs_beyond_first"], 2)
        self.assertEqual(result["repeated_symbols"], {"NO_SIGNAL": 2, "TESTA": 2})
        self.assertIn("REPEATED_SYMBOL_DAY_PAIRS_NOT_INDEPENDENT", result["warnings"])

    def test_second_day_cannot_be_justified_by_single_anchor(self):
        result = audit_day_ledger(self.manifest, self.ledger("2026-10-28", "2026-10-29"))
        self.assertEqual(result["off_anchor_utc_dates"], ["2026-10-28"])
        self.assertIn("SINGLE_REFERENCE_ANCHOR_CANNOT_VERIFY_OTHER_DAYS", result["warnings"])

    def test_duplicate_symbol_date_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_DAY_SYMBOL"):
            audit_day_ledger(self.manifest, self.ledger("2026-10-29") * 2)

    def test_invalid_date_rejected(self):
        with self.assertRaisesRegex(ValueError, "INVALID_OBSERVATION_DATE"):
            audit_day_ledger(self.manifest, self.ledger("2026-02-30"))

    def test_safety_invariants(self):
        result = audit_day_ledger(self.manifest, self.ledger("2026-10-29"))
        self.assertEqual(result["validation_status"], "NOT_VALIDATED")
        self.assertEqual(result["sec_status"], "SEC_UNVERIFIED")
        self.assertEqual(result["all_grades"], "D")
        self.assertFalse(result["orders_allowed"])
        self.assertFalse(result["real_trades_allowed"])
        self.assertFalse(result["actual_market_sessions_verified"])
        self.assertFalse(result["predictive_accuracy_verified"])


if __name__ == "__main__":
    unittest.main()
