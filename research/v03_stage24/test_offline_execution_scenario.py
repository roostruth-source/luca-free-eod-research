"""Offline-only synthetic execution sensitivity regressions."""
import unittest
from offline_execution_scenario import scenario

class ExecutionScenarioTests(unittest.TestCase):
    def test_spread_is_cost_even_without_slippage(self):
        r = scenario(1.00, 1.05, 100)
        self.assertLess(r["hypothetical_round_trip_pct"], 0)
        self.assertAlmostEqual(r["hypothetical_round_trip_pct"], (1/1.05-1)*100)
        self.assertFalse(r["orders_allowed"])

    def test_more_slippage_worsens_hypothetical_result(self):
        self.assertLess(scenario(1, 1.05, 100, 100)["hypothetical_round_trip_pct"],
                        scenario(1, 1.05, 100, 0)["hypothetical_round_trip_pct"])

    def test_halt_never_generates_fill(self):
        r = scenario(1, 1.05, 100, halted=True)
        self.assertIsNone(r["hypothetical_buy"])
        self.assertIsNone(r["hypothetical_round_trip_pct"])
        self.assertFalse(r["halt_verified"])

    def test_bad_values_rejected(self):
        for args in [(1, 1, 10), (2, 1, 10), (1, 2, 0), (True, 2, 10),
                     (1, 2, 10, -1), (1, 2, 10, 10001), (float("nan"), 2, 10)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                scenario(*args)

    def test_missing_depth_never_claims_sufficient(self):
        r = scenario(1, 1.05, 100)
        self.assertTrue(r["depth_claim_missing"])
        self.assertFalse(r["depth_claim_sufficient"])
        self.assertFalse(r["depth_authenticated"])

    def test_insufficient_ask_or_bid_depth(self):
        for bid_size, ask_size in ((1000, 99), (99, 1000)):
            with self.subTest(bid_size=bid_size, ask_size=ask_size):
                r = scenario(1, 1.05, 100, bid_size=bid_size, ask_size=ask_size)
                self.assertTrue(r["depth_claim_exceeded"])
                self.assertFalse(r["depth_claim_sufficient"])
                self.assertFalse(r["orders_allowed"])

    def test_sufficient_synthetic_depth_still_unverified(self):
        r = scenario(1, 1.05, 100, bid_size=100, ask_size=100)
        self.assertTrue(r["depth_claim_sufficient"])
        self.assertFalse(r["depth_authenticated"])
        self.assertFalse(r["fill_verified"])

    def test_invalid_depth_rejected(self):
        for value in (0, -1, True, float("nan"), "100"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "INVALID_SYNTHETIC_DEPTH"):
                scenario(1, 1.05, 100, ask_size=value)

    def test_safety_contract(self):
        r = scenario(1, 1.05, 100)
        self.assertEqual((r["validation_status"], r["sec_status"], r["all_grades"], r["operating_mode"]),
                         ("NOT_VALIDATED", "SEC_UNVERIFIED", "D", "NO_ORDERS"))
        self.assertFalse(r["fill_verified"])
        self.assertEqual(r["independent_sample_count_verified"], 0)

if __name__ == "__main__":
    unittest.main()
