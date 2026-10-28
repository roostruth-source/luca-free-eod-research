"""Offline regression for the first-real-session count-only correction."""
import tempfile
import unittest

from first_count_only_six_minute_bounds import (
    analyze_verified_first, exact_count_bounds
)


class CountOnlySixMinuteBoundsTests(unittest.TestCase):
    def test_all_fourteen_slots_are_enumerated_by_count(self):
        bounds = exact_count_bounds()
        self.assertEqual(len(bounds), 15)
        self.assertEqual(bounds[0]["max_six_min_windows"], 0)
        self.assertEqual(bounds[14]["min_six_min_windows"], 9)
        self.assertEqual(bounds[14]["max_six_min_windows"], 9)

    def test_mathematical_bounds_without_original_timestamps(self):
        b = exact_count_bounds()
        expected = {
            13: (3, 8, 7, 13),
            14: (9, 9, 14, 14),
            11: (0, 6, 3, 11),
            9: (0, 4, 2, 9),
            6: (0, 1, 1, 6),
            5: (0, 0, 1, 5),
        }
        for count, wanted in expected.items():
            with self.subTest(observed_minutes=count):
                row = b[count]
                self.assertEqual(
                    (row["min_six_min_windows"], row["max_six_min_windows"],
                     row["min_longest_consecutive"], row["max_longest_consecutive"]),
                    wanted,
                )

    def test_real_archived_first_session_and_three_way_partition(self):
        result = analyze_verified_first()
        self.assertEqual(result["source_run_id"], 40517830351)
        self.assertEqual((result["observed_iex_bars"], result["expected_iex_bars"]), (94, 168))
        self.assertEqual(result["candidate_count"], 12)
        self.assertEqual(
            (result["guaranteed_evaluable_by_bar_count"],
             result["unresolved_by_bar_count"], result["impossible_by_bar_count"]),
            (4, 3, 5),
        )
        self.assertEqual(
            (result["possible_six_minute_windows_lower_bound"],
             result["possible_six_minute_windows_upper_bound"]),
            (18, 44),
        )
        sets = {"EXISTENCE_GUARANTEED_BUT_TIMESTAMPS_NOT_ARCHIVED": set(),
                "EXISTENCE_UNRESOLVED_WITHOUT_TIMESTAMPS": set(),
                "SIX_CONSECUTIVE_MINUTES_IMPOSSIBLE": set()}
        for row in result["rows"]:
            sets[row["count_only_class"]].add(row["symbol"])
        self.assertEqual(sets["EXISTENCE_GUARANTEED_BUT_TIMESTAMPS_NOT_ARCHIVED"],
                         {"NEXR", "AIOK", "BRAI", "JBLU"})
        self.assertEqual(sets["EXISTENCE_UNRESOLVED_WITHOUT_TIMESTAMPS"],
                         {"CLRO", "AEYE", "ARTV"})
        self.assertEqual(sets["SIX_CONSECUTIVE_MINUTES_IMPOSSIBLE"],
                         {"SXTP", "GPUS", "SOAR", "POM", "ACTU"})

    def test_no_unearned_signal_or_buy_claim(self):
        result = analyze_verified_first()
        self.assertEqual(result["first_recorded_pattern_symbols"], 0)
        self.assertIs(result["actual_signal_recomputed"], False)
        self.assertIs(result["exact_minute_timestamps_unavailable"], True)
        self.assertEqual(result["validation_status"], "NOT_VALIDATED")
        self.assertEqual(result["sec_status"], "SEC_UNVERIFIED")
        self.assertIs(result["real_trades_allowed"], False)
        for row in result["rows"]:
            self.assertIsNone(row["actual_six_minute_windows_observed"])
            self.assertIs(row["signal_pattern_recomputed"], False)
            self.assertIs(row["buy_allowed"], False)

    def test_wrong_grid_rejected_and_missing_archive_not_silently_replaced(self):
        for slots, width in ((15, 6), (14, 5), (True, 6), (14, True)):
            with self.subTest(slots=slots, width=width):
                with self.assertRaises(ValueError):
                    exact_count_bounds(slots, width)
        with tempfile.TemporaryDirectory() as missing_root:
            with self.assertRaises(FileNotFoundError):
                analyze_verified_first(missing_root)


if __name__ == "__main__":
    unittest.main()
