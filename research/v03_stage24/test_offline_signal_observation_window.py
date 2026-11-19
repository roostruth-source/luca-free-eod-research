"""Synthetic regressions: observation time is never an executable quote."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo

from mobile_outcomes import _time
from offline_signal_observation_window import audit_signal_observation_window
from test_offline_asof_availability import at_reference
from test_offline_multisession_audit import session

NY = ZoneInfo("America/New_York")


def scenario(report, feed=0, compute=0, review=0, day_index=0):
    return next(s for s in report["sessions"][day_index]["scenarios"]
                if s["assumed_publication_latency_seconds"] == feed
                and s["assumed_signal_computation_seconds"] == compute
                and s["assumed_human_review_seconds"] == review)


def row(report, symbol="TESTA", feed=0, compute=0, review=0, day_index=0):
    return next(r for r in scenario(report, feed, compute, review, day_index)["rows"]
                if r["symbol"] == symbol)


def near_close(day, hour, minute):
    """Trim synthetic horizon bars to avoid claiming after-hours source data."""
    item = session(day, "near-close-" + day, hour=hour, minute=minute)
    close_hour = 13 if day in ("2026-11-27", "2026-12-24") else 16
    close = dt.datetime.combine(dt.date.fromisoformat(day),
                                dt.time(close_hour), tzinfo=NY).astimezone(dt.timezone.utc)
    for candidate in item["raw"]["rows"]:
        candidate["ohlcv"] = [b for b in candidate["ohlcv"] if _time(b["t"]) < close]
    return item


class SignalObservationWindowTests(unittest.TestCase):
    def test_default_scenario_grid_has_no_trading_claim(self):
        report = audit_signal_observation_window([session()])
        self.assertEqual(report["scenario_combinations_per_session"], 60)
        self.assertEqual(len(report["sessions"][0]["scenarios"]), 60)
        self.assertEqual(report["session_count"], 1)
        self.assertFalse(report["orders_allowed"])

    def test_signal_stamped_at_reference_is_future_at_reference(self):
        report = audit_signal_observation_window([session()], [0], [0], [0])
        r = row(report)
        anchor = _time(report["sessions"][0]["reference_time_utc"])
        self.assertFalse(r["signal_ready_by_frozen_reference"])
        self.assertEqual(r["status"], "SIGNAL_NOT_READY_AT_FROZEN_REFERENCE")
        self.assertEqual(_time(r["first_hypothetical_review_complete_utc"]),
                         anchor + dt.timedelta(minutes=1))
        self.assertFalse(r["order_ready"])

    def test_zero_delay_ready_signal_is_only_hypothetically_observable(self):
        report = audit_signal_observation_window([at_reference(session(), 6)],
                                                 [0], [0], [0])
        r = row(report)
        self.assertTrue(r["signal_ready_by_frozen_reference"])
        self.assertTrue(r["review_completes_before_scheduled_close"])
        self.assertEqual(r["status"], "HYPOTHETICAL_OBSERVATION_WINDOW_ONLY")
        self.assertEqual(r["seconds_until_review_complete_from_reference"], 0)
        self.assertFalse(r["executable_quote_verified"])

    def test_review_delay_starts_no_earlier_than_reference(self):
        report = audit_signal_observation_window([at_reference(session(), 10)],
                                                 [0], [0], [1, 60])
        self.assertEqual(row(report, review=1)["seconds_until_review_complete_from_reference"], 1)
        self.assertEqual(row(report, review=60)["seconds_until_review_complete_from_reference"], 60)

    def test_feed_delay_cannot_promote_signal_at_reference(self):
        report = audit_signal_observation_window([at_reference(session(), 6)],
                                                 [0, 1], [0], [0])
        self.assertTrue(row(report, feed=0)["signal_ready_by_frozen_reference"])
        self.assertFalse(row(report, feed=1)["signal_ready_by_frozen_reference"])
        self.assertEqual(row(report, feed=1)["status"], "SIGNAL_NOT_READY_AT_FROZEN_REFERENCE")

    def test_computation_delay_cannot_promote_signal_at_reference(self):
        report = audit_signal_observation_window([at_reference(session(), 6)],
                                                 [0], [0, 1], [0])
        self.assertTrue(row(report, compute=0)["signal_ready_by_frozen_reference"])
        self.assertFalse(row(report, compute=1)["signal_ready_by_frozen_reference"])

    def test_review_does_not_rewrite_frozen_signal_membership(self):
        report = audit_signal_observation_window([session()], [0], [0], [0, 60])
        for s in report["sessions"][0]["scenarios"]:
            r = next(r for r in s["rows"] if r["symbol"] == "TESTA")
            self.assertEqual(r["status"], "SIGNAL_NOT_READY_AT_FROZEN_REFERENCE")
            self.assertFalse(r["signal_ready_by_frozen_reference"])

    def test_no_signal_has_no_fabricated_observation_time(self):
        report = audit_signal_observation_window([session()], [0], [0], [0])
        r = row(report, "NO_SIGNAL")
        self.assertEqual(r["status"], "NO_ARCHIVED_SIGNAL")
        self.assertIsNone(r["first_hypothetical_review_complete_utc"])
        self.assertIsNone(r["seconds_remaining_before_scheduled_close_after_review"])
        self.assertFalse(r["review_completes_before_scheduled_close"])

    def test_missing_exact_reference_bar_never_backfilled(self):
        item = at_reference(session(), 10)
        missing = _time(item["manifest"]["payload"]["reference_time_utc"]) - dt.timedelta(minutes=1)
        for candidate in item["raw"]["rows"]:
            candidate["ohlcv"] = [b for b in candidate["ohlcv"] if _time(b["t"]) != missing]
        report = audit_signal_observation_window([item], [0], [0], [0])
        r = row(report)
        self.assertTrue(r["signal_ready_by_frozen_reference"])
        self.assertFalse(r["exact_reference_bar_present"])
        self.assertEqual(r["status"], "MISSING_EXACT_REFERENCE_BAR")

    def test_regular_scheduled_close_is_4pm_new_york(self):
        report = audit_signal_observation_window([session()], [0], [0], [0])
        self.assertEqual(report["sessions"][0]["scheduled_close_utc"],
                         "2026-10-29T20:00:00+00:00")
        self.assertFalse(report["sessions"][0]["scheduled_close_live_verified"])

    def test_early_scheduled_close_is_1pm_new_york(self):
        report = audit_signal_observation_window([session("2026-11-27", "early")],
                                                 [0], [0], [0])
        self.assertEqual(report["sessions"][0]["scheduled_close_utc"],
                         "2026-11-27T18:00:00+00:00")
        self.assertIn("EARLY_CLOSE_REQUIRES_MISSING_HORIZON_REVIEW", report["warnings"])

    def test_regular_close_strict_boundary_at_exact_close(self):
        report = audit_signal_observation_window([near_close("2026-10-29", 15, 40)],
                                                 [0], [0], [839, 840])
        self.assertEqual(row(report, review=839)["status"],
                         "SIGNAL_NOT_READY_AT_FROZEN_REFERENCE")
        self.assertTrue(row(report, review=839)["review_completes_before_scheduled_close"])
        self.assertFalse(row(report, review=840)["review_completes_before_scheduled_close"])
        self.assertEqual(row(report, review=840)[
            "seconds_remaining_before_scheduled_close_after_review"], 0)

    def test_early_close_strict_boundary_at_exact_close(self):
        report = audit_signal_observation_window([near_close("2026-11-27", 12, 40)],
                                                 [0], [0], [839, 840])
        self.assertTrue(row(report, review=839)["review_completes_before_scheduled_close"])
        self.assertFalse(row(report, review=840)["review_completes_before_scheduled_close"])

    def test_ready_signal_can_be_too_late_after_review(self):
        item = near_close("2026-10-29", 15, 40)
        item = at_reference(item, 6)
        report = audit_signal_observation_window([item], [0], [0], [0, 840])
        self.assertEqual(row(report, review=0)["status"],
                         "HYPOTHETICAL_OBSERVATION_WINDOW_ONLY")
        self.assertEqual(row(report, review=840)["status"],
                         "REVIEW_AT_OR_AFTER_SCHEDULED_CLOSE")

    def test_repeated_symbols_remain_separate_sessions(self):
        report = audit_signal_observation_window(
            [session(), session("2026-10-30", "day-2")], [0], [0], [0])
        self.assertEqual(report["session_count"], 2)
        self.assertEqual([x["candidate_count"] for x in report["sessions"]], [2, 2])
        self.assertEqual(report["independent_sample_count_verified"], 0)
        self.assertFalse(report["aggregate_win_rate_computed"])
        self.assertIn("REPEATED_SYMBOL_ACROSS_DAYS_NOT_INDEPENDENT", report["warnings"])

    def test_new_york_dst_conversion_for_scheduled_close(self):
        report = audit_signal_observation_window(
            [session("2026-11-02", "after-dst")], [0], [0], [0])
        self.assertEqual(report["sessions"][0]["scheduled_close_utc"],
                         "2026-11-02T21:00:00+00:00")

    def test_holiday_and_weekend_rejected(self):
        for day in ("2026-10-31", "2026-11-26"):
            with self.subTest(day=day), self.assertRaisesRegex(
                    ValueError, "CLOSED_OR_UNSUPPORTED_NY_SESSION_DATE"):
                audit_signal_observation_window([session(day)], [0], [0], [0])

    def test_unsafe_raw_rejected_by_existing_gate(self):
        item = session()
        item["raw"]["orders_allowed"] = True
        with self.assertRaisesRegex(ValueError, "UNSAFE_EVIDENCE"):
            audit_signal_observation_window([item], [0], [0], [0])

    def test_bad_review_scenarios_fail_closed(self):
        for values in ([], [True], [-1], [1801], [0.5], ["30"], [0, 0]):
            with self.subTest(values=values), self.assertRaisesRegex(
                    ValueError, "REVIEW_DELAY"):
                audit_signal_observation_window([session()], [0], [0], values)

    def test_too_many_combinations_rejected(self):
        with self.assertRaisesRegex(ValueError, "TOO_MANY_OBSERVATION_SCENARIOS"):
            audit_signal_observation_window([session()],
                                            list(range(5)), list(range(5)),
                                            list(range(4)))

    def test_zero_bar_session_still_has_no_signal(self):
        item = session()
        for candidate in item["raw"]["rows"]:
            candidate["ohlcv"] = []
            candidate["signals"] = []
        report = audit_signal_observation_window([item], [0], [0], [0])
        self.assertEqual(scenario(report)["frozen_reference_signal_count"], 0)
        self.assertEqual(scenario(report)["hypothetical_window_only_count"], 0)

    def test_uncertainty_and_no_order_guards(self):
        report = audit_signal_observation_window([session()], [0], [0], [0])
        self.assertEqual(report["validation_status"], "NOT_VALIDATED")
        self.assertEqual(report["sec_status"], "SEC_UNVERIFIED")
        self.assertEqual(report["all_grades"], "D")
        self.assertEqual(report["operating_mode"], "NO_ORDERS")
        for flag in ("orders_allowed", "real_trades_allowed",
                     "executable_bid_ask_verified", "liquidity_and_fill_verified",
                     "prediction_accuracy_verified", "human_review_time_measured",
                     "actual_market_open_verified"):
            self.assertFalse(report[flag], flag)
        for s in report["sessions"][0]["scenarios"]:
            for r in s["rows"]:
                self.assertFalse(r["order_ready"])
                self.assertFalse(r["orders_allowed"])
                self.assertFalse(r["executable_quote_verified"])


if __name__ == "__main__":
    unittest.main()
