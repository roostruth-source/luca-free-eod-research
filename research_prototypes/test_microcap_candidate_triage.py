"""Offline tests for candidate triage."""
import unittest
from microcap_candidate_triage import assess, rank

class TriageTests(unittest.TestCase):
    def row(self, **kw):
        r = {"ticker": "TEST", "close": 1.1, "prev_close": 1,
             "volume": 100000, "avg_volume_20d": 10000}
        r.update(kw)
        return r

    def test_high_volume_never_becomes_buy_signal(self):
        result = assess(self.row())
        self.assertEqual(result["research_score"], 29)
        self.assertFalse(result["trading_allowed"])
        self.assertEqual(result["sec_status"], "UNVERIFIED")
        self.assertIsNone(result["float_shares"])
        self.assertIn("cb_active", result["unknown_risks"])

    def test_bad_data_rejected(self):
        for overrides in ({"close": 0}, {"volume": -1},
                          {"avg_volume_20d": 0}, {"close": float("nan")},
                          {"ticker": "../BAD"}, {"volume": True}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    assess(self.row(**overrides))

    def test_rank_keeps_errors_and_never_claims_market_wide(self):
        result = rank([self.row(ticker="BBB", volume=200000),
                       self.row(ticker="AAA"), self.row(ticker="BAD", close=0)])
        self.assertEqual([r["ticker"] for r in result["candidates"]], ["BBB", "AAA"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertFalse(result["market_wide"])
        self.assertFalse(result["orders_enabled"])

if __name__ == "__main__":
    unittest.main()
