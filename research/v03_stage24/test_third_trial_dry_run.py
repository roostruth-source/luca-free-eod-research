"""Network-free full-path third-trial rehearsal tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from third_trial_dry_run import (
    run_dry_run, EXPECTED_FIND_PATTERNS_SHA256,
)


class ThirdTrialDryRunTests(unittest.TestCase):
    def test_full_synthetic_path_replays_and_archives(self):
        with tempfile.TemporaryDirectory() as folder:
            result = run_dry_run(Path(folder) / "dry")
        self.assertTrue(result["synthetic_only"])
        self.assertFalse(result["internet_or_real_market_api_used"])
        self.assertEqual(result["fake_get_calls"], 1)
        self.assertTrue(result["gate_passed"])
        self.assertTrue(result["raw_ohlcv_archived"])
        self.assertTrue(result["replay_exact_match"])
        self.assertEqual(result["durable_archive_status"], "COMPLETE_REPLAY_VERIFIED")
        self.assertTrue(result["durable_archive_synthetic_label"])
        self.assertEqual(result["all_grades"], "D")
        self.assertFalse(result["orders_allowed"])

    def test_formula_source_change_blocks_before_fake_transport(self):
        with tempfile.TemporaryDirectory() as folder, patch(
                "third_trial_dry_run.signal_formula_source_sha256",
                return_value="0" * 64):
            with self.assertRaisesRegex(ValueError, "FIND_PATTERNS_BASELINE_CHANGED"):
                run_dry_run(Path(folder) / "dry")

    def test_expected_formula_hash_is_fixed_baseline(self):
        self.assertEqual(
            EXPECTED_FIND_PATTERNS_SHA256,
            "8b51d1b83ccd7791a39b84e69b8df17d04a867587aa23eb325765208e958d3e6")

    def test_existing_output_root_blocks_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "dry"
            root.mkdir()
            with self.assertRaisesRegex(FileExistsError, "SYNTHETIC_DRY_RUN_ROOT_EXISTS"):
                run_dry_run(root)


if __name__ == "__main__":
    unittest.main()
