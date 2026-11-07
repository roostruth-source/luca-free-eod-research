"""Synthetic offline tests for fixed-time comparison; no real market data."""
import datetime as dt
import unittest
from offline_fixed_time_comparison import compare
from test_mobile_outcomes_integration import synthetic_raw, START

def fixture():
    raw = synthetic_raw(35)
    first = raw["rows"][0]
    first["signals"][0]["signal"]["signal_bar_start_utc"] = first["ohlcv"][5]["t"]
    second = {"symbol": "NO_SIGNAL", "grade": "D", "buy_allowed": False,
              "ohlcv": [dict(bar, c=200-i) for i, bar in enumerate(first["ohlcv"])],
              "signals": []}
    raw["rows"].append(second)
    return raw

class FixedTimeTests(unittest.TestCase):
    def test_both_groups_share_identical_reference_time(self):
        result = compare(fixture(), (START + dt.timedelta(minutes=5)).isoformat())
        self.assertEqual([row["group"] for row in result["rows"]],
                         ["signal_by_reference_time", "no_signal_by_reference_time"])
        self.assertEqual(result["observed_counts_by_horizon"]["5"],
                         {"signal_by_reference_time": 1, "no_signal_by_reference_time": 1})
    def test_downside_is_retained(self):
        result = compare(fixture(), (START + dt.timedelta(minutes=5)).isoformat())
        self.assertLess(result["rows"][1]["changes_pct"]["5"], 0)
    def test_60_minute_unknown_not_zero(self):
        result = compare(fixture(), (START + dt.timedelta(minutes=5)).isoformat())
        self.assertTrue(all(row["changes_pct"]["60"] is None for row in result["rows"]))
    def test_future_signal_cannot_change_past_group(self):
        result = compare(fixture(), (START + dt.timedelta(minutes=4)).isoformat())
        self.assertTrue(all(row["group"] == "no_signal_by_reference_time" for row in result["rows"]))
    def test_invalid_six_bar_evidence_rejected(self):
        raw = fixture()
        raw["rows"][0]["signals"][0]["calculation_input_ohlcv"].pop()
        with self.assertRaisesRegex(ValueError, "INVALID_SIGNAL_INPUT_WINDOW"):
            compare(raw, (START + dt.timedelta(minutes=5)).isoformat())
    def test_no_claim_of_accuracy_or_trading(self):
        result = compare(fixture(), (START + dt.timedelta(minutes=5)).isoformat())
        self.assertFalse(result["prediction_accuracy_verified"])
        self.assertFalse(result["orders_allowed"])

if __name__ == "__main__":
    unittest.main()
