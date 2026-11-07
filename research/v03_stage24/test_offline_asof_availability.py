"""Synthetic regression tests for one-minute bar-start look-ahead risks."""
import copy
import datetime as dt
import unittest

from offline_asof_availability import audit_asof_availability
from offline_reference_commitment import create_commitment
from test_offline_multisession_audit import session
from mobile_outcomes import _time


def at_reference(item, minutes_from_start):
    result = copy.deepcopy(item)
    first_bar = _time(result["raw"]["rows"][0]["ohlcv"][0]["t"])
    stamp = (first_bar + dt.timedelta(minutes=minutes_from_start)).isoformat()
    result["manifest"] = create_commitment(
        stamp, [r["symbol"] for r in result["raw"]["rows"]],
        result["manifest"]["payload"]["observation_id"])
    return result


class AsofAvailabilityTests(unittest.TestCase):
    def test_signal_stamped_reference_is_not_yet_available(self):
        result = audit_asof_availability([session()])
        by_symbol = {r["symbol"]: r for r in result["rows"]}
        row = by_symbol["TESTA"]
        self.assertEqual(row["legacy_group"], "signal_by_reference_time")
        self.assertEqual(row["strict_asof_group"], "no_signal_known_by_reference_time")
        self.assertEqual(row["unclosed_signal_count_at_reference"], 1)
        self.assertEqual(result["legacy_signal_membership_not_asof_count"], 1)

    def test_previous_minute_close_is_latest_available(self):
        result = audit_asof_availability([session()])
        row = next(r for r in result["rows"] if r["symbol"] == "TESTA")
        anchor = _time(row["reference_time_utc"])
        self.assertEqual(_time(row["latest_completed_bar_start_utc"]),
                         anchor - dt.timedelta(minutes=1))
        self.assertFalse(row["latest_completed_close_is_executable_price"])

    def test_reference_bar_close_is_not_available_at_its_start(self):
        result = audit_asof_availability([session()])
        self.assertEqual(result["legacy_reference_bar_not_asof_count"], 2)
        self.assertTrue(all(r["legacy_reference_bar_close_asof_available"] is False
                            for r in result["rows"]))
        self.assertIn("REFERENCE_BAR_CLOSE_NOT_AVAILABLE_AT_BAR_START",
                      result["warnings"])

    def test_signal_becomes_eligible_after_bar_completes(self):
        item = at_reference(session(), 6)
        result = audit_asof_availability([item])
        row = next(r for r in result["rows"] if r["symbol"] == "TESTA")
        self.assertEqual(row["strict_asof_group"], "signal_known_by_reference_time")
        self.assertEqual(row["unclosed_signal_count_at_reference"], 0)
        self.assertEqual(result["legacy_signal_membership_not_asof_count"], 0)

    def test_reference_before_signal_does_not_promote_future_signal(self):
        item = at_reference(session(), 4)
        result = audit_asof_availability([item])
        row = next(r for r in result["rows"] if r["symbol"] == "TESTA")
        self.assertEqual(row["strict_asof_group"], "no_signal_known_by_reference_time")
        self.assertEqual(row["legacy_group"], "no_signal_by_reference_time")

    def test_reference_first_bar_has_no_completed_close(self):
        item = at_reference(session(), 0)
        result = audit_asof_availability([item])
        self.assertTrue(all(r["latest_completed_bar_close"] is None
                            for r in result["rows"]))
        self.assertIn("NO_COMPLETED_BAR_AT_REFERENCE", result["warnings"])

    def test_zero_bar_session_does_not_claim_completed_prices(self):
        item = session()
        for row in item["raw"]["rows"]:
            row["ohlcv"] = []
            row["signals"] = []
        result = audit_asof_availability([item])
        self.assertEqual(result["legacy_reference_bar_not_asof_count"], 0)
        self.assertTrue(all(r["latest_completed_bar_close"] is None
                            for r in result["rows"]))

    def test_two_sessions_repeated_symbols_still_not_independent(self):
        result = audit_asof_availability([
            session(), session("2026-10-30", "day-2")])
        self.assertEqual(len(result["rows"]), 4)
        self.assertEqual(result["independent_sample_count_verified"], 0)
        self.assertIn("REPEATED_SYMBOL_ACROSS_DAYS_NOT_INDEPENDENT",
                      result["warnings"])

    def test_unsafe_raw_still_rejected(self):
        item = session()
        item["raw"]["orders_allowed"] = True
        with self.assertRaisesRegex(ValueError, "UNSAFE_EVIDENCE"):
            audit_asof_availability([item])

    def test_weekend_still_rejected(self):
        with self.assertRaisesRegex(ValueError, "CLOSED_OR_UNSUPPORTED_NY_SESSION_DATE"):
            audit_asof_availability([session("2026-10-31")])

    def test_safety_and_uncertainty_flags_preserved(self):
        result = audit_asof_availability([session()])
        self.assertEqual(result["validation_status"], "NOT_VALIDATED")
        self.assertEqual(result["sec_status"], "SEC_UNVERIFIED")
        self.assertEqual(result["all_grades"], "D")
        self.assertFalse(result["orders_allowed"])
        self.assertFalse(result["prediction_accuracy_verified"])
        self.assertFalse(result["asof_signal_availability_externally_verified"])

if __name__ == "__main__":
    unittest.main()
