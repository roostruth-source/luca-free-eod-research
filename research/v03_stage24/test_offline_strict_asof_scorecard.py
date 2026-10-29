"""Synthetic strict-as-of regressions; no external data or live trial."""
import datetime as dt
import unittest

from mobile_outcomes import _time
from offline_strict_asof_scorecard import strict_asof_scorecard
from test_offline_asof_availability import at_reference
from test_offline_multisession_audit import session


def row_for(report, symbol="TESTA", index=0):
    return next(row for row in report["sessions"][index]["rows"]
                if row["symbol"] == symbol)


class StrictAsofScorecardTests(unittest.TestCase):
    def test_reference_minute_signal_is_not_known(self):
        report = strict_asof_scorecard([session()])
        self.assertEqual(row_for(report)["strict_asof_group"],
                         "no_signal_known_by_reference_time")
        self.assertEqual(row_for(report)["legacy_group"], "signal_by_reference_time")

    def test_previous_completed_bar_is_baseline(self):
        item = session()
        report = strict_asof_scorecard([item])
        row = row_for(report)
        anchor = _time(row["reference_time_utc"])
        expected = next(bar["c"] for bar in item["raw"]["rows"][0]["ohlcv"]
                        if _time(bar["t"]) == anchor - dt.timedelta(minutes=1))
        self.assertEqual(row["baseline_completed_bar_close"], expected)
        self.assertEqual(_time(row["baseline_bar_start_utc"]),
                         anchor - dt.timedelta(minutes=1))
        self.assertFalse(row["baseline_is_executable_quote"])

    def test_exact_horizon_uses_last_completed_bar(self):
        item = session()
        report = strict_asof_scorecard([item])
        row = row_for(report)
        anchor = _time(row["reference_time_utc"])
        prices = {_time(bar["t"]): bar["c"] for bar in item["raw"]["rows"][0]["ohlcv"]}
        baseline = prices[anchor - dt.timedelta(minutes=1)]
        target = prices[anchor + dt.timedelta(minutes=4)]
        self.assertEqual(row["changes_pct"]["5"],
                         round((target / baseline - 1) * 100, 4))

    def test_legacy_reference_minute_not_used(self):
        item = session()
        report = strict_asof_scorecard([item])
        row = row_for(report)
        anchor = _time(row["reference_time_utc"])
        reference_minute_close = next(bar["c"] for bar in item["raw"]["rows"][0]["ohlcv"]
                                      if _time(bar["t"]) == anchor)
        self.assertNotEqual(row["baseline_completed_bar_close"], reference_minute_close)

    def test_signal_known_only_after_its_bar_closes(self):
        item = at_reference(session(), 6)
        report = strict_asof_scorecard([item])
        self.assertEqual(row_for(report)["strict_asof_group"],
                         "signal_known_by_reference_time")

    def test_signal_future_cannot_change_past_group(self):
        item = at_reference(session(), 4)
        report = strict_asof_scorecard([item])
        self.assertEqual(row_for(report)["strict_asof_group"],
                         "no_signal_known_by_reference_time")

    def test_no_completed_bar_at_start_is_missing_not_zero(self):
        item = at_reference(session(), 0)
        report = strict_asof_scorecard([item])
        row = row_for(report)
        self.assertIsNone(row["baseline_completed_bar_close"])
        self.assertIsNone(row["changes_pct"]["5"])
        self.assertEqual(row["horizon_status"]["5"], "MISSING_COMPLETED_REFERENCE_BAR")

    def test_missing_exact_horizon_is_not_backfilled(self):
        item = session()
        anchor = _time(item["manifest"]["payload"]["reference_time_utc"])
        target = anchor + dt.timedelta(minutes=4)
        for row in item["raw"]["rows"]:
            row["ohlcv"] = [bar for bar in row["ohlcv"] if _time(bar["t"]) != target]
        report = strict_asof_scorecard([item])
        self.assertIsNone(row_for(report)["changes_pct"]["5"])
        self.assertEqual(row_for(report)["horizon_status"]["5"],
                         "MISSING_EXACT_COMPLETED_HORIZON_BAR")

    def test_60_minute_missing_is_not_zero(self):
        report = strict_asof_scorecard([session()])
        self.assertIsNone(row_for(report)["changes_pct"]["60"])
        self.assertEqual(row_for(report)["horizon_status"]["60"],
                         "MISSING_EXACT_COMPLETED_HORIZON_BAR")

    def test_group_counts_and_missing_are_separate(self):
        report = strict_asof_scorecard([session()])
        groups = report["sessions"][0]["observed_counts_by_horizon"]["5"]
        self.assertEqual(groups["no_signal_known_by_reference_time"]["candidates"], 2)
        self.assertEqual(groups["no_signal_known_by_reference_time"]["observed"], 2)
        self.assertEqual(groups["signal_known_by_reference_time"]["candidates"], 0)

    def test_multi_day_never_pools_win_rate(self):
        report = strict_asof_scorecard([session(), session("2026-10-30", "day-2")])
        self.assertEqual(report["session_count"], 2)
        self.assertEqual([s["candidate_count"] for s in report["sessions"]], [2, 2])
        self.assertFalse(report["aggregate_win_rate_computed"])
        self.assertEqual(report["independent_sample_count_verified"], 0)

    def test_weekend_rejected_by_existing_gate(self):
        with self.assertRaisesRegex(ValueError, "CLOSED_OR_UNSUPPORTED_NY_SESSION_DATE"):
            strict_asof_scorecard([session("2026-10-31")])

    def test_invalid_signal_window_rejected(self):
        item = session()
        item["raw"]["rows"][0]["signals"][0]["calculation_input_ohlcv"].pop()
        with self.assertRaisesRegex(ValueError, "INVALID_SIGNAL_INPUT_WINDOW"):
            strict_asof_scorecard([item])

    def test_unsafe_order_flag_rejected(self):
        item = session()
        item["raw"]["orders_allowed"] = True
        with self.assertRaisesRegex(ValueError, "UNSAFE_EVIDENCE"):
            strict_asof_scorecard([item])

    def test_zero_bar_session_retains_missing_outcomes(self):
        item = session()
        for row in item["raw"]["rows"]:
            row["ohlcv"] = []
            row["signals"] = []
        report = strict_asof_scorecard([item])
        self.assertTrue(all(r["changes_pct"]["5"] is None
                            for r in report["sessions"][0]["rows"]))

    def test_safety_and_latency_uncertainty_preserved(self):
        report = strict_asof_scorecard([session()])
        self.assertEqual(report["validation_status"], "NOT_VALIDATED")
        self.assertEqual(report["sec_status"], "SEC_UNVERIFIED")
        self.assertEqual(report["all_grades"], "D")
        self.assertFalse(report["orders_allowed"])
        self.assertFalse(report["real_trades_allowed"])
        self.assertFalse(report["prediction_accuracy_verified"])
        self.assertFalse(report["bar_publication_latency_verified"])
        self.assertIn("ASOF_BOUNDARY_ASSUMES_ZERO_DATA_PUBLICATION_LATENCY",
                      report["warnings"])


if __name__ == "__main__":
    unittest.main()
