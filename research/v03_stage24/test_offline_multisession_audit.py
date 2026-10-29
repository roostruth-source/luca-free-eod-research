"""Synthetic multi-session audit regressions. Never accesses external services."""
import copy
import datetime as dt
import unittest
from zoneinfo import ZoneInfo

from offline_multisession_audit import audit_session_bundle
from offline_reference_commitment import create_commitment
from test_offline_fixed_time_comparison import fixture, START

NY = ZoneInfo("America/New_York")
UTC = dt.timezone.utc


def session(day="2026-10-29", observation_id="day-1", hour=10, minute=0):
    raw = copy.deepcopy(fixture())
    target = dt.datetime.combine(dt.date.fromisoformat(day), dt.time(hour, minute),
                                 tzinfo=NY).astimezone(UTC)
    shift = target - START
    def moved(stamp):
        return (dt.datetime.fromisoformat(stamp) + shift).isoformat()
    for row in raw["rows"]:
        for bar in row["ohlcv"]:
            bar["t"] = moved(bar["t"])
        for signal in row["signals"]:
            signal["signal"]["signal_bar_start_utc"] = moved(
                signal["signal"]["signal_bar_start_utc"])
            # The six input bars share object identity with row["ohlcv"] in
            # fixture(); they were already shifted above. Do not shift twice.
    manifest = create_commitment((target + dt.timedelta(minutes=5)).isoformat(),
                                 [r["symbol"] for r in raw["rows"]], observation_id)
    return {"session_day_ny": day, "raw": raw, "manifest": manifest}


class MultiSessionAuditTests(unittest.TestCase):
    def test_two_separate_day_archives_no_independence_claim(self):
        report = audit_session_bundle([session(), session("2026-10-30", "day-2")])
        self.assertEqual(report["claimed_session_days_with_structurally_consistent_records"], 2)
        self.assertEqual(report["unique_symbols"], 2)
        self.assertEqual(report["symbol_session_pairs"], 4)
        self.assertEqual(report["extra_symbol_sessions_beyond_first"], 2)
        self.assertEqual(report["repeated_symbols"], {"NO_SIGNAL": 2, "TESTA": 2})
        self.assertEqual(report["independent_sample_count_verified"], 0)
        self.assertFalse(report["actual_market_sessions_verified"])
        self.assertFalse(report["orders_allowed"])
        self.assertEqual(report["all_grades"], "D")
        self.assertEqual(len(report["sessions"]), 2)

    def test_one_symbol_missing_from_other_day_is_not_fabricated(self):
        first, second = session(), session("2026-10-30", "day-2")
        second["raw"]["rows"].pop()
        anchor = second["manifest"]["payload"]["reference_time_utc"]
        second["manifest"] = create_commitment(anchor, ["TESTA"], "day-2")
        report = audit_session_bundle([first, second])
        self.assertEqual(report["symbol_session_pairs"], 3)
        self.assertEqual(report["repeated_symbols"], {"TESTA": 2})

    def test_shifted_identical_price_sequence_warns(self):
        report = audit_session_bundle([session(), session("2026-10-30", "day-2")])
        self.assertIn("IDENTICAL_PRICE_SEQUENCE_ACROSS_DAYS_REVIEW", report["warnings"])
        self.assertEqual(report["matching_price_sequences_ignoring_timestamps"],
                         [{"first_session_day_ny": "2026-10-29",
                           "repeated_session_day_ny": "2026-10-30"}])

    def test_different_price_sequence_no_copy_warning(self):
        first, second = session(), session("2026-10-30", "day-2")
        second["raw"]["rows"][0]["ohlcv"][6]["c"] += 0.5
        report = audit_session_bundle([first, second])
        self.assertEqual(report["matching_price_sequences_ignoring_timestamps"], [])
        self.assertNotIn("IDENTICAL_PRICE_SEQUENCE_ACROSS_DAYS_REVIEW", report["warnings"])

    def test_non_minute_reference_rejected(self):
        item = session()
        anchor = dt.datetime.fromisoformat(item["manifest"]["payload"]["reference_time_utc"])
        item["manifest"] = create_commitment(
            (anchor + dt.timedelta(seconds=30)).isoformat(),
            ["TESTA", "NO_SIGNAL"], "day-1")
        with self.assertRaisesRegex(ValueError, "REFERENCE_NOT_MINUTE_ALIGNED"):
            audit_session_bundle([item])

    def test_non_minute_raw_bar_rejected(self):
        item = session()
        bar = item["raw"]["rows"][0]["ohlcv"][-1]
        bar["t"] = (dt.datetime.fromisoformat(bar["t"]) +
                    dt.timedelta(seconds=30)).isoformat()
        with self.assertRaisesRegex(ValueError, "RAW_BAR_NOT_MINUTE_ALIGNED"):
            audit_session_bundle([item])

    def test_duplicate_ny_day_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_NY_SESSION_DAY"):
            audit_session_bundle([session(), session(observation_id="day-2")])

    def test_reused_observation_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_OBSERVATION_ID"):
            audit_session_bundle([session(), session("2026-10-30")])

    def test_forged_day_label_rejected(self):
        item = session()
        item["session_day_ny"] = "2026-10-30"
        with self.assertRaisesRegex(ValueError, "REFERENCE_OUTSIDE_DECLARED_NY_SESSION"):
            audit_session_bundle([item])

    def test_weekend_rejected(self):
        with self.assertRaisesRegex(ValueError, "CLOSED_OR_UNSUPPORTED_NY_SESSION_DATE"):
            audit_session_bundle([session("2026-10-31")])

    def test_thanksgiving_rejected(self):
        with self.assertRaisesRegex(ValueError, "CLOSED_OR_UNSUPPORTED_NY_SESSION_DATE"):
            audit_session_bundle([session("2026-11-26")])

    def test_outside_calendar_year_rejected(self):
        with self.assertRaisesRegex(ValueError, "CLOSED_OR_UNSUPPORTED_NY_SESSION_DATE"):
            audit_session_bundle([session("2027-01-04")])

    def test_premarket_reference_rejected(self):
        item = session(hour=9, minute=0)
        with self.assertRaisesRegex(ValueError, "REFERENCE_OUTSIDE_DECLARED_NY_SESSION"):
            audit_session_bundle([item])

    def test_out_of_session_raw_bar_rejected(self):
        item = session()
        item["raw"]["rows"][0]["ohlcv"][-1]["t"] = (
            dt.datetime(2026, 10, 29, 17, 0, tzinfo=NY).astimezone(UTC).isoformat())
        with self.assertRaisesRegex(ValueError, "RAW_BAR_OUTSIDE_DECLARED_NY_SESSION"):
            audit_session_bundle([item])

    def test_early_close_rejects_bars_after_1pm(self):
        item = session("2026-11-27", "early", hour=12, minute=45)
        with self.assertRaisesRegex(ValueError, "RAW_BAR_OUTSIDE_DECLARED_NY_SESSION"):
            audit_session_bundle([item])

    def test_early_close_valid_morning_still_warns(self):
        item = session("2026-11-27", "early")
        report = audit_session_bundle([item])
        self.assertIn("EARLY_CLOSE_REQUIRES_MISSING_HORIZON_REVIEW", report["warnings"])
        self.assertEqual(report["sessions"][0]["calendar_status"], "SCHEDULED_EARLY_CLOSE")

    def test_manifest_hash_tamper_rejected(self):
        item = session()
        item["manifest"]["payload"]["observation_id"] = "forged"
        with self.assertRaisesRegex(ValueError, "COMMITMENT_HASH_MISMATCH"):
            audit_session_bundle([item])

    def test_forged_candidate_universe_rejected(self):
        item = session()
        item["raw"]["rows"].pop()
        with self.assertRaisesRegex(ValueError, "CANDIDATE_UNIVERSE_CHANGED"):
            audit_session_bundle([item])

    def test_same_empty_raw_archive_reused_on_two_days_rejected(self):
        first, second = session(), session("2026-10-30", "day-2")
        for item in (first, second):
            for row in item["raw"]["rows"]:
                row["ohlcv"] = []
                row["signals"] = []
        with self.assertRaisesRegex(ValueError, "REUSED_RAW_ARCHIVE_CONTENT"):
            audit_session_bundle([first, second])

    def test_unsafe_raw_rejected(self):
        item = session()
        item["raw"]["orders_allowed"] = True
        with self.assertRaisesRegex(ValueError, "UNSAFE_EVIDENCE"):
            audit_session_bundle([item])

    def test_missing_bundle_rejected(self):
        with self.assertRaisesRegex(ValueError, "MISSING_SESSION_BUNDLE"):
            audit_session_bundle([])

    def test_invalid_day_format_rejected(self):
        item = session()
        item["session_day_ny"] = "2026-10-29T10:00"
        with self.assertRaisesRegex(ValueError, "INVALID_NY_SESSION_DATE"):
            audit_session_bundle([item])


if __name__ == "__main__":
    unittest.main()
