import unittest

from evaluate_followups import evaluate_followups


def signal(ticker="AAA", close1=11.0):
    return {
        "ticker": ticker,
        "signal_at": "2026-11-12T00:08:00+09:00",
        "entry_price": 10.0,
        "entry_rule": "SCREEN_REFERENCE_PRICE",
        "engine_hits": ["preview", "signal", "best"],
        "dilution_warning": False,
        "bars": [
            {
                "session_close_at": "2026-11-12T16:00:00-05:00",
                "open": 10.0,
                "high": max(12.0, close1),
                "low": 9.0,
                "close": close1,
                "complete": True,
                "price_basis": "SPLIT_ADJUSTED_TO_SIGNAL",
            },
            {
                "session_close_at": "2026-11-13T16:00:00-05:00",
                "open": 11.0,
                "high": 15.0,
                "low": 10.0,
                "close": 12.0,
                "complete": True,
                "price_basis": "SPLIT_ADJUSTED_TO_SIGNAL",
            },
            {
                "session_close_at": "2026-11-16T16:00:00-05:00",
                "open": 9.5,
                "high": 10.0,
                "low": 8.0,
                "close": 9.0,
                "complete": True,
                "price_basis": "SPLIT_ADJUSTED_TO_SIGNAL",
            },
        ],
    }


def payload(*signals):
    return {
        "evaluation_asof": "2026-11-16T17:00:00-05:00",
        "signals": list(signals or (signal(),)),
    }


class FollowupEvaluationTests(unittest.TestCase):
    def test_completed_horizons_and_excursions(self):
        result = evaluate_followups(payload())
        record = result["records"][0]
        self.assertAlmostEqual(record["outcomes"]["1"]["close_return_pct"], 10.0)
        self.assertAlmostEqual(record["outcomes"]["1"]["mfe_pct"], 20.0)
        self.assertAlmostEqual(record["outcomes"]["1"]["mae_pct"], -10.0)
        self.assertAlmostEqual(record["outcomes"]["3"]["close_return_pct"], -10.0)
        self.assertAlmostEqual(record["outcomes"]["3"]["mfe_pct"], 50.0)
        self.assertAlmostEqual(record["outcomes"]["3"]["mae_pct"], -20.0)
        self.assertEqual(record["outcomes"]["5"]["status"], "NOT_MATURE")
        self.assertTrue(result["accuracy_not_computed"])
        self.assertTrue(result["WATCH_ONLY"])
        self.assertTrue(result["NO_ORDERS"])

    def test_future_bar_is_rejected(self):
        item = signal()
        with self.assertRaisesRegex(ValueError, "future_bar_not_allowed"):
            evaluate_followups(
                {"evaluation_asof": "2026-11-12T15:00:00-05:00", "signals": [item]}
            )

    def test_incomplete_bar_is_rejected(self):
        item = signal()
        item["bars"][0]["complete"] = False
        with self.assertRaisesRegex(ValueError, "incomplete_bar_not_allowed"):
            evaluate_followups(payload(item))

    def test_split_adjusted_basis_is_required(self):
        item = signal()
        item["bars"][0]["price_basis"] = "RAW"
        with self.assertRaisesRegex(ValueError, "split_adjusted_price_basis_required"):
            evaluate_followups(payload(item))

    def test_group_statistics_remove_largest_gain(self):
        first = signal("AAA", 11.0)
        second = signal("BBB", 13.0)
        result = evaluate_followups(payload(first, second))
        stats = result["grouped_reference_statistics"]["engine_count:3+"]["1"]
        self.assertEqual(stats["n"], 2)
        self.assertEqual(stats["positive_close_rate_pct"], 100.0)
        self.assertAlmostEqual(stats["mean_close_return_pct"], 20.0)
        self.assertAlmostEqual(stats["median_close_return_pct"], 20.0)
        self.assertAlmostEqual(stats["mean_ex_largest_gain_pct"], 10.0)

    def test_requested_combinations_are_grouped(self):
        item = signal()
        item["engine_hits"] = ["preview", "signal", "burning_up"]
        result = evaluate_followups(payload(item))
        groups = result["records"][0]["groups"]
        self.assertIn("combo:preview+signal", groups)
        self.assertIn("combo:signal+burning_up", groups)


if __name__ == "__main__":
    unittest.main()
