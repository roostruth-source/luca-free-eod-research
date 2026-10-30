"""Synthetic-only regression checks for decision readiness; no network or orders."""
import datetime as dt
import unittest

from mobile_outcomes import _time
from offline_decision_readiness import audit_decision_readiness
from offline_strict_asof_scorecard import strict_asof_scorecard
from test_offline_asof_availability import at_reference
from test_offline_multisession_audit import session


def scenario(report, feed=0, compute=0, day_index=0):
    return next(s for s in report["sessions"][day_index]["scenarios"]
                if s["assumed_publication_latency_seconds"] == feed
                and s["assumed_signal_computation_seconds"] == compute)


def symbol_row(report, symbol="TESTA", feed=0, compute=0, day_index=0):
    return next(r for r in scenario(report, feed, compute, day_index)["rows"]
                if r["symbol"] == symbol)


class DecisionReadinessTests(unittest.TestCase):
    def test_zero_delay_agrees_with_existing_strict_asof_group(self):
        item = session()
        old = strict_asof_scorecard([item])["sessions"][0]["rows"]
        report = audit_decision_readiness([item], [0], [0])
        for previous in old:
            row = symbol_row(report, previous["symbol"])
            expected = previous["strict_asof_group"] == "signal_known_by_reference_time"
            self.assertEqual(row["signal_ready_by_reference"], expected)
            self.assertEqual(row["baseline_bar_start_utc"],
                             previous["baseline_bar_start_utc"])

    def test_reference_minute_signal_not_yet_ready(self):
        row = symbol_row(audit_decision_readiness([session()], [0], [0]))
        self.assertEqual(row["status"], "SIGNAL_NOT_READY_BY_REFERENCE")
        self.assertEqual(row["seconds_until_first_signal_ready_from_reference"], 60)
        self.assertFalse(row["signal_ready_by_reference"])

    def test_one_minute_later_ready_at_zero_delay(self):
        item = at_reference(session(), 6)
        row = symbol_row(audit_decision_readiness([item], [0], [0]))
        self.assertEqual(row["status"], "SIGNAL_READY_BY_REFERENCE")
        self.assertEqual(row["known_signal_count"], 1)
        self.assertTrue(row["ready_signal_with_reference_bar"])

    def test_one_second_processing_delay_prevents_premature_readiness(self):
        item = at_reference(session(), 6)
        report = audit_decision_readiness([item], [0], [0, 1])
        self.assertTrue(symbol_row(report, compute=0)["signal_ready_by_reference"])
        late = symbol_row(report, compute=1)
        self.assertFalse(late["signal_ready_by_reference"])
        self.assertEqual(late["seconds_until_first_signal_ready_from_reference"], 1)

    def test_one_second_feed_delay_also_prevents_readiness(self):
        item = at_reference(session(), 6)
        report = audit_decision_readiness([item], [0, 1], [0])
        self.assertTrue(symbol_row(report, feed=0)["signal_ready_by_reference"])
        self.assertFalse(symbol_row(report, feed=1)["signal_ready_by_reference"])

    def test_feed_and_processing_delay_are_additive(self):
        item = at_reference(session(), 6)
        report = audit_decision_readiness([item], [30], [60])
        row = symbol_row(report, feed=30, compute=60)
        self.assertEqual(row["seconds_until_first_signal_ready_from_reference"], 90)
        self.assertFalse(row["signal_ready_by_reference"])

    def test_computation_delay_does_not_change_bar_publication_time(self):
        report = audit_decision_readiness([session()], [0], [0, 120])
        self.assertEqual(symbol_row(report, compute=0)["baseline_bar_start_utc"],
                         symbol_row(report, compute=120)["baseline_bar_start_utc"])

    def test_feed_delay_moves_exact_reference_bar(self):
        report = audit_decision_readiness([session()], [0, 1], [0])
        first = _time(symbol_row(report, feed=0)["baseline_bar_start_utc"])
        second = _time(symbol_row(report, feed=1)["baseline_bar_start_utc"])
        self.assertEqual(first - second, dt.timedelta(minutes=1))

    def test_no_signal_remains_no_signal_for_every_delay(self):
        report = audit_decision_readiness([session()], [0, 30], [0, 120])
        for s in report["sessions"][0]["scenarios"]:
            row = next(r for r in s["rows"] if r["symbol"] == "NO_SIGNAL")
            self.assertEqual(row["status"], "NO_SIGNAL_IN_ARCHIVE")
            self.assertIsNone(row["earliest_hypothetical_signal_ready_utc"])
            self.assertFalse(row["signal_ready_by_reference"])

    def test_missing_exact_reference_bar_is_not_backfilled(self):
        item = at_reference(session(), 10)
        anchor = _time(item["manifest"]["payload"]["reference_time_utc"])
        missing = anchor - dt.timedelta(minutes=1)
        for row in item["raw"]["rows"]:
            row["ohlcv"] = [b for b in row["ohlcv"] if _time(b["t"]) != missing]
        report = audit_decision_readiness([item], [0], [0])
        row = symbol_row(report)
        self.assertTrue(row["signal_ready_by_reference"])
        self.assertFalse(row["exact_baseline_bar_present"])
        self.assertFalse(row["ready_signal_with_reference_bar"])
        self.assertEqual(scenario(report)["missing_reference_bar_count"], 2)

    def test_first_minute_has_no_reference_bar(self):
        item = at_reference(session(), 0)
        report = audit_decision_readiness([item], [0], [0])
        self.assertEqual(scenario(report)["missing_reference_bar_count"], 2)

    def test_two_days_stay_separate_and_repeated_symbols_warn(self):
        report = audit_decision_readiness(
            [session(), session("2026-10-30", "day-2")], [0], [0])
        self.assertEqual(report["session_count"], 2)
        self.assertEqual([x["candidate_count"] for x in report["sessions"]], [2, 2])
        self.assertEqual(report["independent_sample_count_verified"], 0)
        self.assertFalse(report["aggregate_win_rate_computed"])
        self.assertIn("REPEATED_SYMBOL_ACROSS_DAYS_NOT_INDEPENDENT", report["warnings"])

    def test_invalid_computation_delay_rejected(self):
        for values in ([], [True], [-1], [301], [0.5], ["30"], [0, 0]):
            with self.subTest(values=values), self.assertRaisesRegex(
                    ValueError, "COMPUTATION_DELAY"):
                audit_decision_readiness([session()], [0], values)

    def test_invalid_feed_delay_rejected(self):
        with self.assertRaisesRegex(ValueError, "LATENCY"):
            audit_decision_readiness([session()], [-1], [0])

    def test_scenario_combination_limit(self):
        with self.assertRaisesRegex(ValueError, "TOO_MANY_DELAY_SCENARIOS"):
            audit_decision_readiness([session()], list(range(6)), list(range(5)))

    def test_weekend_rejected_by_existing_gate(self):
        with self.assertRaisesRegex(ValueError, "CLOSED_OR_UNSUPPORTED_NY_SESSION_DATE"):
            audit_decision_readiness([session("2026-10-31")], [0], [0])

    def test_unsafe_raw_rejected_by_existing_gate(self):
        item = session()
        item["raw"]["orders_allowed"] = True
        with self.assertRaisesRegex(ValueError, "UNSAFE_EVIDENCE"):
            audit_decision_readiness([item], [0], [0])

    def test_safety_flags_and_uncertainty_preserved(self):
        report = audit_decision_readiness([session()], [0], [0])
        self.assertEqual(report["validation_status"], "NOT_VALIDATED")
        self.assertEqual(report["sec_status"], "SEC_UNVERIFIED")
        self.assertEqual(report["all_grades"], "D")
        self.assertEqual(report["operating_mode"], "NO_ORDERS")
        self.assertFalse(report["orders_allowed"])
        self.assertFalse(report["real_trades_allowed"])
        self.assertFalse(report["prediction_accuracy_verified"])
        self.assertFalse(report["signal_computation_time_measured"])
        self.assertFalse(report["actual_order_timing_verified"])
        self.assertFalse(symbol_row(report)["executable_quote_verified"])


if __name__ == "__main__":
    unittest.main()
