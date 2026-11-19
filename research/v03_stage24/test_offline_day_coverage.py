"""Synthetic tests for distinct observation-day coverage."""
import unittest
from offline_day_coverage import summarize_day_coverage
from test_offline_cohort_scorecard import setup_case

class DayCoverageTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.manifest = setup_case()
    def test_single_day_warning(self):
        ledger = [{"observation_date_utc": "2026-10-29", "symbol": s} for s in ("TESTA", "NO_SIGNAL")]
        result = summarize_day_coverage(self.raw, self.manifest, ledger)["day_coverage"]
        self.assertEqual(result["distinct_observation_days"], 1)
        self.assertEqual(result["candidate_day_pairs"], 2)
        self.assertEqual(result["day_count_warning"], "TOO_FEW_OBSERVATION_DAYS")
    def test_two_distinct_days(self):
        ledger = [{"observation_date_utc": d, "symbol": s}
                  for d in ("2026-10-28", "2026-10-29") for s in ("TESTA", "NO_SIGNAL")]
        result = summarize_day_coverage(self.raw, self.manifest, ledger)["day_coverage"]
        self.assertEqual(result["distinct_observation_days"], 2)
        self.assertEqual(result["candidate_day_pairs"], 4)
    def test_duplicate_day_symbol_rejected(self):
        ledger = [{"observation_date_utc": "2026-10-29", "symbol": "TESTA"}] * 2
        with self.assertRaisesRegex(ValueError, "DUPLICATE_DAY_SYMBOL"):
            summarize_day_coverage(self.raw, self.manifest, ledger)
    def test_unknown_symbol_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNKNOWN_LEDGER_SYMBOL"):
            summarize_day_coverage(self.raw, self.manifest,
                                   [{"observation_date_utc": "2026-10-29", "symbol": "LATE"}])
    def test_missing_candidate_rejected(self):
        with self.assertRaisesRegex(ValueError, "COVERAGE_MISMATCH"):
            summarize_day_coverage(self.raw, self.manifest,
                                   [{"observation_date_utc": "2026-10-29", "symbol": "TESTA"}])
    def test_bad_date_rejected(self):
        with self.assertRaisesRegex(ValueError, "INVALID_OBSERVATION_DATE"):
            summarize_day_coverage(self.raw, self.manifest,
                                   [{"observation_date_utc": "2026-02-30", "symbol": "TESTA"}])
    def test_empty_ledger_rejected(self):
        with self.assertRaisesRegex(ValueError, "MISSING_DAY_LEDGER"):
            summarize_day_coverage(self.raw, self.manifest, [])
    def test_integrated_audit_flags_repeated_symbols_and_unproven_days(self):
        ledger = [{"observation_date_utc": d, "symbol": s}
                  for d in ("2026-10-28", "2026-10-29") for s in ("TESTA", "NO_SIGNAL")]
        report = summarize_day_coverage(self.raw, self.manifest, ledger)
        audit = report["day_integrity_audit"]
        self.assertEqual(audit["unique_symbols"], 2)
        self.assertEqual(audit["claimed_symbol_date_pairs"], 4)
        self.assertEqual(audit["independent_session_count_verified"], 0)
        self.assertIn("SINGLE_REFERENCE_ANCHOR_CANNOT_VERIFY_OTHER_DAYS", audit["warnings"])
        self.assertFalse(report["orders_allowed"])

    def test_days_not_claimed_verified(self):
        ledger = [{"observation_date_utc": "2026-10-29", "symbol": s} for s in ("TESTA", "NO_SIGNAL")]
        result = summarize_day_coverage(self.raw, self.manifest, ledger)
        self.assertFalse(result["day_coverage"]["observation_days_externally_verified"])
        self.assertFalse(result["prediction_accuracy_verified"])

if __name__ == "__main__":
    unittest.main()
