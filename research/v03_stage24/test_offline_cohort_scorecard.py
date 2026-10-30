"""Synthetic checks for descriptive scorecard; no real market access."""
import datetime as dt
import unittest
from offline_cohort_scorecard import scorecard
from offline_reference_commitment import create_commitment
from test_offline_fixed_time_comparison import fixture, START

def setup_case():
    raw = fixture()
    anchor = (START + dt.timedelta(minutes=5)).isoformat()
    manifest = create_commitment(anchor, ["TESTA", "NO_SIGNAL"], "synthetic-scorecard")
    return raw, manifest

class ScorecardTests(unittest.TestCase):
    def test_both_cohorts_retained(self):
        raw, manifest = setup_case()
        groups = scorecard(raw, manifest)["groups"]
        self.assertEqual(groups["signal_by_reference_time"]["candidates"], 1)
        self.assertEqual(groups["no_signal_by_reference_time"]["candidates"], 1)
    def test_downside_counted(self):
        raw, manifest = setup_case()
        row = scorecard(raw, manifest)["groups"]["no_signal_by_reference_time"]["horizons"]["5"]
        self.assertEqual(row["declined"], 1)
        self.assertEqual(row["threshold_reached"], 0)
    def test_missing_60_minute_not_counted_as_failure_or_success(self):
        raw, manifest = setup_case()
        for group in scorecard(raw, manifest)["groups"].values():
            row = group["horizons"]["60"]
            self.assertEqual((row["candidates"], row["observed"], row["missing"]), (1, 0, 1))
            self.assertIsNone(row["threshold_rate_among_observed_pct"])
    def test_missing_5_minute_is_visible(self):
        raw, manifest = setup_case()
        raw["rows"][1]["ohlcv"] = [b for i, b in enumerate(raw["rows"][1]["ohlcv"]) if i != 10]
        row = scorecard(raw, manifest)["groups"]["no_signal_by_reference_time"]["horizons"]["5"]
        self.assertEqual((row["observed"], row["missing"]), (0, 1))
    def test_threshold_customizable(self):
        raw, manifest = setup_case()
        r = scorecard(raw, manifest, threshold_pct=4)
        self.assertEqual(r["groups"]["signal_by_reference_time"]["horizons"]["5"]["threshold_reached"], 1)
    def test_invalid_threshold_rejected(self):
        raw, manifest = setup_case()
        with self.assertRaisesRegex(ValueError, "INVALID_THRESHOLD"):
            scorecard(raw, manifest, threshold_pct=0)
    def test_manifest_tampering_rejected(self):
        raw, manifest = setup_case()
        manifest["payload"]["symbols"].pop()
        with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
            scorecard(raw, manifest)
    def test_small_sample_warning_on_both_groups(self):
        raw, manifest = setup_case()
        result = scorecard(raw, manifest)
        for group in result["groups"].values():
            self.assertEqual(group["horizons"]["5"]["sample_warning"],
                             "INSUFFICIENT_OBSERVED_SAMPLE")
            self.assertFalse(group["horizons"]["5"]["interpretation_allowed"])

    def test_missing_outcome_warning_is_separate(self):
        raw, manifest = setup_case()
        row = scorecard(raw, manifest)["groups"]["signal_by_reference_time"]["horizons"]["60"]
        self.assertEqual(row["missing_data_warning"], "MISSING_OUTCOMES")
        self.assertEqual(row["sample_warning"], "INSUFFICIENT_OBSERVED_SAMPLE")

    def test_complete_observation_has_no_missing_warning(self):
        raw, manifest = setup_case()
        row = scorecard(raw, manifest)["groups"]["signal_by_reference_time"]["horizons"]["5"]
        self.assertIsNone(row["missing_data_warning"])

    def test_nan_threshold_rejected(self):
        raw, manifest = setup_case()
        with self.assertRaisesRegex(ValueError, "INVALID_THRESHOLD"):
            scorecard(raw, manifest, threshold_pct=float("nan"))

    def test_not_validated_and_no_orders(self):
        raw, manifest = setup_case()
        r = scorecard(raw, manifest)
        self.assertFalse(r["prediction_accuracy_verified"])
        self.assertFalse(r["orders_allowed"])

if __name__ == "__main__":
    unittest.main()
