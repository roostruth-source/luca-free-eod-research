import unittest

from prioritize_watchlist import prioritize


def report():
    return {
        "rows": [
            {"ticker": "WEAK", "iex_status": "WATCH_ONLY_FRESH_IEX",
             "screener_groups": {}, "iex_quote_spread_pct": 12.0,
             "volume_first_context": {"volume_first_recent": False}, "NO_ORDERS": True},
            {"ticker": "STRONG", "iex_status": "WATCH_ONLY_FRESH_IEX",
             "screener_groups": {"active_volume": 2, "active_trades": 3, "gainers": 1},
             "iex_quote_spread_pct": 1.0,
             "volume_first_context": {"volume_first_recent": True}, "NO_ORDERS": True},
            {"ticker": "STALE", "iex_status": "PENDING_STALE_OR_MISSING",
             "screener_groups": {"active_volume": 1}, "iex_quote_spread_pct": 1.0,
             "volume_first_context": {"volume_first_recent": True}, "NO_ORDERS": True},
        ],
        "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
    }


class PrioritizeWatchlistTests(unittest.TestCase):
    def test_transparent_priority_orders_strong_fresh_candidate_first(self):
        result = prioritize(report())
        self.assertEqual([row["ticker"] for row in result["rows"]],
                         ["STRONG", "WEAK", "STALE"])
        first = result["rows"][0]
        self.assertEqual(first["research_priority_label"], "PRIORITY_1_RESEARCH")
        self.assertEqual(first["research_priority_rank"], 1)
        self.assertIn("VOLUME_FIRST_RECENT", {x["code"] for x in first["priority_reasons"]})
        self.assertFalse(first["priority_is_buy_signal"])
        self.assertFalse(first["buy_allowed"])

    def test_stale_price_is_always_zero_and_held(self):
        item = prioritize(report())["rows"][-1]
        self.assertEqual(item["ticker"], "STALE")
        self.assertEqual(item["research_priority_score"], 0)
        self.assertEqual(item["research_priority_label"], "HOLD_STALE_OR_MISSING_PRICE")
        self.assertIn("PRICE_STALE_OR_MISSING", item["risk_flags"])

    def test_wide_spread_and_missing_volume_pattern_are_visible_risks(self):
        weak = next(row for row in prioritize(report())["rows"] if row["ticker"] == "WEAK")
        self.assertIn("WIDE_IEX_SPREAD", weak["risk_flags"])
        self.assertIn("VOLUME_FIRST_NOT_CONFIRMED", weak["risk_flags"])

    def test_input_is_not_mutated_and_unsafe_input_is_rejected(self):
        original = report()
        prioritize(original)
        self.assertNotIn("research_priority_score", original["rows"][0])
        original["NO_ORDERS"] = False
        with self.assertRaisesRegex(ValueError, "unsafe_watchlist_report"):
            prioritize(original)


if __name__ == "__main__":
    unittest.main()
