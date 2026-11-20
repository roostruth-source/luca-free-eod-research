import unittest

from prioritize_watchlist import prioritize


def report():
    return {
        "rows": [
            {"ticker": "WEAK", "iex_status": "WATCH_ONLY_FRESH_IEX",
             "screener_groups": {}, "iex_quote_spread_pct": 12.0,
             "volume_first_context": {"volume_first_recent": False},
             "security_scope": {"status": "COMMON_EQUITY_CANDIDATE_SCOPE"},
             "NO_ORDERS": True},
            {"ticker": "STRONG", "iex_status": "WATCH_ONLY_FRESH_IEX",
             "screener_groups": {"active_volume": 2, "active_trades": 3, "gainers": 1},
             "iex_quote_spread_pct": 1.0,
             "volume_first_context": {"volume_first_recent": True},
             "security_scope": {"status": "COMMON_EQUITY_CANDIDATE_SCOPE"},
             "NO_ORDERS": True},
            {"ticker": "STALE", "iex_status": "PENDING_STALE_OR_MISSING",
             "screener_groups": {"active_volume": 1}, "iex_quote_spread_pct": 1.0,
             "volume_first_context": {"volume_first_recent": True},
             "security_scope": {"status": "COMMON_EQUITY_CANDIDATE_SCOPE"},
             "NO_ORDERS": True},
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

    def test_etf_is_zero_score_even_with_strong_market_activity(self):
        item = report()
        item["rows"][1]["security_scope"] = {"status": "EXCLUDED_ETF_OR_ETP"}
        strong = next(row for row in prioritize(item)["rows"] if row["ticker"] == "STRONG")
        self.assertEqual(strong["research_priority_score"], 0)
        self.assertEqual(strong["research_priority_label"],
                         "HOLD_OUT_OF_SCOPE_OR_UNVERIFIED")
        self.assertIn("EXCLUDED_ETF_OR_ETP", strong["risk_flags"])

    def test_premarket_fresh_context_is_ranked_but_never_priority_one(self):
        item = report()
        strong = item["rows"][1]
        strong["iex_status"] = "WATCH_ONLY_FRESH_IEX_PREMARKET"
        strong["price_session_context"] = {
            "status": "WATCH_ONLY_FRESH_IEX_PREMARKET",
            "market_session": "PREMARKET", "trade_fresh": True,
            "quote_fresh": True, "full_market_quote_verified": False,
            "NO_ORDERS": True,
        }
        result = next(row for row in prioritize(item)["rows"] if row["ticker"] == "STRONG")
        self.assertEqual(result["research_priority_label"], "PRIORITY_3_LOW_EVIDENCE")
        self.assertIn("FRESH_PREMARKET_IEX",
                      {reason["code"] for reason in result["priority_reasons"]})
        self.assertIn("PREMARKET_SINGLE_EXCHANGE_CONTEXT", result["risk_flags"])
        self.assertIn("REGULAR_SESSION_VOLUME_PATTERN_UNAVAILABLE", result["risk_flags"])
        self.assertFalse(result["priority_is_buy_signal"])

    def test_premarket_screener_ranks_cannot_inflate_score(self):
        item = report()
        strong = item["rows"][1]
        strong["iex_status"] = "WATCH_ONLY_FRESH_IEX_PREMARKET"
        strong["price_session_context"] = {
            "status": "WATCH_ONLY_FRESH_IEX_PREMARKET",
            "market_session": "PREMARKET", "trade_fresh": True,
            "quote_fresh": True, "full_market_quote_verified": False,
            "NO_ORDERS": True,
        }
        ranked = next(row for row in prioritize(item)["rows"] if row["ticker"] == "STRONG")
        strong["screener_groups"] = {}
        unranked = next(row for row in prioritize(item)["rows"] if row["ticker"] == "STRONG")
        self.assertEqual(ranked["research_priority_score"], unranked["research_priority_score"])
        self.assertEqual(ranked["research_priority_label"], "PRIORITY_3_LOW_EVIDENCE")
        self.assertIn("PREMARKET_SCREENER_RANK_SESSION_UNVERIFIED", ranked["risk_flags"])
        self.assertFalse({"ACTIVE_VOLUME_RANK", "ACTIVE_TRADES_RANK", "MOVER_GAINER"} &
                         {reason["code"] for reason in ranked["priority_reasons"]})
        self.assertFalse(ranked["buy_allowed"])

    def test_premarket_never_borrows_regular_volume_first_points(self):
        item = report()
        strong = item["rows"][1]
        strong["iex_status"] = "WATCH_ONLY_FRESH_IEX_PREMARKET"
        strong["price_session_context"] = {
            "status": "WATCH_ONLY_FRESH_IEX_PREMARKET",
            "market_session": "PREMARKET", "trade_fresh": True,
            "quote_fresh": True, "full_market_quote_verified": False,
            "NO_ORDERS": True,
        }
        with_regular_pattern = next(
            row for row in prioritize(item)["rows"] if row["ticker"] == "STRONG"
        )
        strong["volume_first_context"]["volume_first_recent"] = False
        without_regular_pattern = next(
            row for row in prioritize(item)["rows"] if row["ticker"] == "STRONG"
        )
        self.assertEqual(with_regular_pattern["research_priority_score"],
                         without_regular_pattern["research_priority_score"])
        self.assertNotIn("VOLUME_FIRST_RECENT",
                         {reason["code"] for reason in with_regular_pattern["priority_reasons"]})
        self.assertIn("PREMARKET_VOLUME_FIRST_UNVERIFIED",
                      with_regular_pattern["risk_flags"])
        self.assertNotEqual(with_regular_pattern["research_priority_label"],
                            "PRIORITY_1_RESEARCH")

    def test_premarket_status_without_frozen_context_is_zero_and_held(self):
        item = report()
        item["rows"][1]["iex_status"] = "WATCH_ONLY_FRESH_IEX_PREMARKET"
        result = next(row for row in prioritize(item)["rows"] if row["ticker"] == "STRONG")
        self.assertEqual(result["research_priority_score"], 0)
        self.assertEqual(result["research_priority_label"], "HOLD_STALE_OR_MISSING_PRICE")
        self.assertIn("PREMARKET_CONTEXT_INVALID", result["risk_flags"])

    def test_nasdaq_deficient_common_stock_is_zero_and_held(self):
        item = report()
        strong = item["rows"][1]
        strong["security_scope"].update({
            "financial_status": "D",
            "financial_status_label": "DEFICIENT_CONTINUED_LISTING_REQUIREMENTS",
            "financial_status_risk": True,
        })
        result = next(row for row in prioritize(item)["rows"] if row["ticker"] == "STRONG")
        self.assertEqual(result["research_priority_score"], 0)
        self.assertEqual(result["research_priority_label"],
                         "HOLD_FINANCIAL_OR_LISTING_STATUS")
        self.assertIn("NASDAQ_FINANCIAL_STATUS_D", result["risk_flags"])

    def test_sec_reverse_split_or_listing_notice_is_zero_and_held(self):
        item = report()
        strong = item["rows"][1]
        strong["listing_action_context"] = {
            "risk_detected": True,
            "signals": [{"code": "REVERSE_SPLIT"},
                        {"code": "LISTING_DEFICIENCY"}],
        }
        result = next(row for row in prioritize(item)["rows"]
                      if row["ticker"] == "STRONG")
        self.assertEqual(result["research_priority_score"], 0)
        self.assertEqual(result["research_priority_label"],
                         "HOLD_FINANCIAL_OR_LISTING_STATUS")
        self.assertIn("SEC_FILING_REVERSE_SPLIT", result["risk_flags"])
        self.assertIn("SEC_FILING_LISTING_DEFICIENCY", result["risk_flags"])
        self.assertFalse(result["buy_allowed"])

    def test_sec_supply_risk_is_zero_and_held_separately(self):
        item = report()
        strong = item["rows"][1]
        strong["sec_supply_context"] = {
            "dilution_risk_detected": True,
            "signals": [{"code": "ATM"}, {"code": "ELOC"}],
        }
        result = next(row for row in prioritize(item)["rows"]
                      if row["ticker"] == "STRONG")
        self.assertEqual(result["research_priority_score"], 0)
        self.assertEqual(result["research_priority_label"], "HOLD_SEC_SUPPLY_RISK")
        self.assertIn("SEC_FILING_ATM", result["risk_flags"])
        self.assertIn("SEC_FILING_ELOC", result["risk_flags"])
        self.assertFalse(result["buy_allowed"])


if __name__ == "__main__":
    unittest.main()
