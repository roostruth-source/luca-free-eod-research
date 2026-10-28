"""Synthetic-only tests for real 6-contiguous-minute IEX pattern evaluability."""
import copy
import unittest
from second_six_minute_evaluability import assess_six_minute_evaluability
from test_two_session_iex_comparison import fixture,SECOND_ID

class SixMinuteEvaluabilityTests(unittest.TestCase):
    def test_six_contiguous_even_with_gaps_elsewhere(self):
        f,r,p=fixture((0,1,2,3,4,5,7,9,11))
        out=assess_six_minute_evaluability(f,r,p,SECOND_ID)
        self.assertEqual(out["evaluable_symbols"],1)
        self.assertEqual(out["rows"][0]["longest_contiguous_minutes"],6)
        self.assertEqual(out["rows"][0]["evaluable_six_minute_windows"],1)
        self.assertEqual(out["rows"][0]["possible_six_minute_windows"],10)
        self.assertEqual(out["rows"][0]["evaluability_status"],"PATTERN_RECORDED_RESEARCH_ONLY")
        self.assertFalse(out["real_trades_allowed"])

    def test_six_scattered_not_one_six_minute_window(self):
        f,r,p=fixture((0,2,4,6,8,10))
        out=assess_six_minute_evaluability(f,r,p,SECOND_ID)
        self.assertEqual(out["rows"][0]["iex_minutes_observed"],6)
        self.assertEqual(out["evaluable_symbols"],0)
        self.assertEqual(out["rows"][0]["longest_contiguous_minutes"],1)
        self.assertEqual(out["rows"][0]["evaluability_status"],"NO_EVALUABLE_SIX_MINUTE_WINDOW")

    def test_contiguous_no_pattern_is_not_failure(self):
        f,r,p=fixture((6,7,8,9,10,11))
        out=assess_six_minute_evaluability(f,r,p,SECOND_ID)
        self.assertEqual(out["evaluable_symbols"],1)
        self.assertEqual(out["rows"][0]["evaluability_status"],"EVALUABLE_NO_PATTERN_RECORDED")
        self.assertTrue(out["rows"][0]["no_pattern_is_not_no_future_spike"])

    def test_all_fifteen_minutes_allow_ten_overlapping_windows(self):
        f,r,p=fixture(tuple(range(15)))
        out=assess_six_minute_evaluability(f,r,p,SECOND_ID)
        self.assertEqual(out["evaluable_windows"],10)
        self.assertEqual(out["rows"][0]["longest_contiguous_minutes"],15)

    def test_no_bars_means_no_evaluability_not_zero_returns(self):
        f,r,p=fixture(())
        out=assess_six_minute_evaluability(f,r,p,SECOND_ID)
        self.assertEqual(out["not_evaluable_symbols"],1)
        self.assertEqual(out["evaluable_windows"],0)
        self.assertTrue(out["no_future_price_behavior_verified"])

    def test_tampered_timestamp_grid_blocks(self):
        f,r,p=fixture((0,1,2,3,4,5))
        p["rows"][0]["missing_iex_bar_start_utc"]=[]
        with self.assertRaisesRegex(ValueError,"INCONSISTENT_TIMESTAMP_GRID"):
            assess_six_minute_evaluability(f,r,p,SECOND_ID)

    def test_false_reported_pattern_without_six_consecutive_rejected(self):
        f,r,p=fixture((0,2,4,6,8,10))
        r["results"][0]["pattern_count"]=1
        r["results"][0]["first_pattern"]={
            "signal_bar_start_utc":p["rows"][0]["observed_bar_start_utc"][5],
            "bar_knowable_after_utc":"2026-10-28T14:02:00+00:00",
            "research_pattern_only":True,"buy_allowed":False}
        r["forward_pattern_symbols"]=1
        with self.assertRaises(ValueError):
            assess_six_minute_evaluability(f,r,p,SECOND_ID)

    def test_wrong_frozen_identity_blocks(self):
        f,r,p=fixture()
        f["candidates"]=["MSFT"]
        with self.assertRaises(ValueError):
            assess_six_minute_evaluability(f,r,p,SECOND_ID)

if __name__=="__main__":
    unittest.main()
