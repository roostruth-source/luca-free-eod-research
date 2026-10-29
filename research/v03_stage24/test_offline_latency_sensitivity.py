"""Synthetic-only latency sensitivity regressions; no network or orders."""
import datetime as dt
import unittest

from mobile_outcomes import _time
from offline_latency_sensitivity import latency_sensitivity
from offline_strict_asof_scorecard import strict_asof_scorecard
from test_offline_asof_availability import at_reference
from test_offline_multisession_audit import session


def row_for(report, latency=0, symbol="TESTA", index=0):
    scenarios = report["sessions"][index]["latency_scenarios"]
    return next(row for s in scenarios if s["assumed_latency_seconds"] == latency
                for row in s["rows"] if row["symbol"] == symbol)


class LatencySensitivityTests(unittest.TestCase):
    def test_zero_latency_matches_strict_completed_bar_scorecard(self):
        item = session()
        old = strict_asof_scorecard([item])["sessions"][0]["rows"]
        new = latency_sensitivity([item], [0])
        for old_row in old:
            row = row_for(new, 0, old_row["symbol"])
            self.assertEqual(row["group"], old_row["strict_asof_group"])
            self.assertEqual(row["baseline_close"], old_row["baseline_completed_bar_close"])
            self.assertEqual(row["changes_pct"], old_row["changes_pct"])

    def test_one_second_excludes_just_closed_bar(self):
        report = latency_sensitivity([session()], [0, 1])
        a = row_for(report, 0)
        b = row_for(report, 1)
        self.assertEqual(_time(a["baseline_bar_start_utc"]) -
                         _time(b["baseline_bar_start_utc"]), dt.timedelta(minutes=1))
        self.assertNotEqual(a["baseline_close"], b["baseline_close"])

    def test_30_and_60_seconds_same_minute_boundary(self):
        report = latency_sensitivity([session()], [30, 60])
        self.assertEqual(row_for(report, 30)["baseline_bar_start_utc"],
                         row_for(report, 60)["baseline_bar_start_utc"])

    def test_61_seconds_excludes_another_bar(self):
        report = latency_sensitivity([session()], [60, 61])
        a = row_for(report, 60)
        b = row_for(report, 61)
        self.assertEqual(_time(a["baseline_bar_start_utc"]) -
                         _time(b["baseline_bar_start_utc"]), dt.timedelta(minutes=1))

    def test_signal_eligibility_changes_when_latency_added(self):
        item = at_reference(session(), 6)
        report = latency_sensitivity([item], [0, 1])
        self.assertEqual(row_for(report, 0)["group"], "signal_known_by_reference_time")
        self.assertEqual(row_for(report, 1)["group"], "no_signal_known_by_reference_time")

    def test_future_signal_never_eligible(self):
        report = latency_sensitivity([at_reference(session(), 4)], [0, 30])
        self.assertEqual(row_for(report, 0)["group"], "no_signal_known_by_reference_time")
        self.assertEqual(row_for(report, 30)["group"], "no_signal_known_by_reference_time")

    def test_horizon_target_moves_with_latency(self):
        report = latency_sensitivity([session()], [0, 30])
        a = _time(row_for(report, 0)["horizon_bar_starts_utc"]["5"])
        b = _time(row_for(report, 30)["horizon_bar_starts_utc"]["5"])
        self.assertEqual(a - b, dt.timedelta(minutes=1))

    def test_missing_exact_baseline_not_backfilled(self):
        item = session()
        anchor = _time(item["manifest"]["payload"]["reference_time_utc"])
        missing = anchor - dt.timedelta(minutes=2)
        for row in item["raw"]["rows"]:
            row["ohlcv"] = [bar for bar in row["ohlcv"] if _time(bar["t"]) != missing]
        report = latency_sensitivity([item], [30])
        row = row_for(report, 30)
        self.assertIsNone(row["changes_pct"]["5"])
        self.assertEqual(row["horizon_status"]["5"],
                         "MISSING_EXACT_LATENCY_ELIGIBLE_BASELINE_BAR")

    def test_missing_exact_horizon_not_backfilled(self):
        item = session()
        anchor = _time(item["manifest"]["payload"]["reference_time_utc"])
        missing = anchor + dt.timedelta(minutes=3)
        for row in item["raw"]["rows"]:
            row["ohlcv"] = [bar for bar in row["ohlcv"] if _time(bar["t"]) != missing]
        row = row_for(latency_sensitivity([item], [30]), 30)
        self.assertIsNone(row["changes_pct"]["5"])
        self.assertEqual(row["horizon_status"]["5"],
                         "MISSING_EXACT_LATENCY_ELIGIBLE_HORIZON_BAR")

    def test_60_minute_missing_is_not_zero(self):
        report = latency_sensitivity([session()], [0, 120])
        for latency in (0, 120):
            self.assertIsNone(row_for(report, latency)["changes_pct"]["60"])

    def test_two_days_stay_separate_and_not_independent(self):
        report = latency_sensitivity([session(), session("2026-10-30", "day-2")], [0])
        self.assertEqual(report["session_count"], 2)
        self.assertEqual([s["candidate_count"] for s in report["sessions"]], [2, 2])
        self.assertEqual(report["independent_sample_count_verified"], 0)
        self.assertFalse(report["aggregate_win_rate_computed"])
        self.assertIn("REPEATED_SYMBOL_ACROSS_DAYS_NOT_INDEPENDENT", report["warnings"])

    def test_early_close_day_keeps_warning(self):
        report = latency_sensitivity([session("2026-11-27", "early")], [0])
        self.assertIn("EARLY_CLOSE_REQUIRES_MISSING_HORIZON_REVIEW", report["warnings"])

    def test_weekend_rejected(self):
        with self.assertRaisesRegex(ValueError, "CLOSED_OR_UNSUPPORTED_NY_SESSION_DATE"):
            latency_sensitivity([session("2026-10-31")])

    def test_unsafe_raw_rejected(self):
        item = session()
        item["raw"]["orders_allowed"] = True
        with self.assertRaisesRegex(ValueError, "UNSAFE_EVIDENCE"):
            latency_sensitivity([item])

    def test_invalid_latency_values_rejected(self):
        for values in ([], [True], [-1], [301], [0.5], ["30"], [0, 0]):
            with self.subTest(values=values), self.assertRaisesRegex(
                    ValueError, "LATENCY"):
                latency_sensitivity([session()], values)

    def test_scenarios_sorted_without_duplicate(self):
        report = latency_sensitivity([session()], [120, 0, 30])
        self.assertEqual(report["latencies_seconds_assumed"], [0, 30, 120])

    def test_missing_early_baseline_does_not_invent_price(self):
        item = at_reference(session(), 0)
        report = latency_sensitivity([item], [0, 30])
        self.assertIsNone(row_for(report, 0)["baseline_close"])
        self.assertIsNone(row_for(report, 30)["baseline_close"])

    def test_safety_status_and_latency_uncertainty(self):
        report = latency_sensitivity([session()])
        self.assertEqual(report["validation_status"], "NOT_VALIDATED")
        self.assertEqual(report["sec_status"], "SEC_UNVERIFIED")
        self.assertEqual(report["all_grades"], "D")
        self.assertEqual(report["operating_mode"], "NO_ORDERS")
        self.assertFalse(report["orders_allowed"])
        self.assertFalse(report["real_trades_allowed"])
        self.assertFalse(report["latency_values_measured"])
        self.assertFalse(report["prediction_accuracy_verified"])
        self.assertFalse(row_for(report)["executable_price_verified"])
        self.assertIn("HYPOTHETICAL_LATENCY_ONLY_NOT_MEASURED", report["warnings"])


if __name__ == "__main__":
    unittest.main()
