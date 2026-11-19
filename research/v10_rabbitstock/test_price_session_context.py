from datetime import datetime, timezone
import unittest

from price_session_context import (FRESH_PREMARKET, FRESH_REGULAR, PENDING,
                                   classify, market_session)


def row(trade="2026-11-19T12:04:00Z", quote="2026-11-19T12:04:30Z"):
    return {
        "iex_last_trade_utc": trade,
        "iex_quote_utc": quote,
        "iex_quote_spread_pct": 1.5,
        "price_band_0_20_to_20": True,
        "research_status": "PENDING_STALE_OR_MISSING",
    }


class PriceSessionContextTests(unittest.TestCase):
    def test_recent_premarket_trade_and_quote_are_watch_only_fresh(self):
        result = classify(row(), datetime(2026, 11, 19, 12, 5, tzinfo=timezone.utc))
        self.assertEqual(result["market_session"], "PREMARKET")
        self.assertEqual(result["status"], FRESH_PREMARKET)
        self.assertTrue(result["trade_fresh"])
        self.assertTrue(result["quote_fresh"])
        self.assertFalse(result["full_market_quote_verified"])
        self.assertTrue(result["NO_ORDERS"])

    def test_regular_session_keeps_established_regular_gate(self):
        item = row("2026-11-19T15:04:00Z", "2026-11-19T15:04:30Z")
        item["research_status"] = FRESH_REGULAR
        result = classify(item, datetime(2026, 11, 19, 15, 5, tzinfo=timezone.utc))
        self.assertEqual(result["status"], FRESH_REGULAR)

    def test_stale_future_or_missing_quote_never_becomes_fresh(self):
        asof = datetime(2026, 11, 19, 12, 5, tzinfo=timezone.utc)
        self.assertEqual(classify(row(trade="2026-11-19T11:00:00Z"), asof)["status"], PENDING)
        self.assertEqual(classify(row(trade="2026-11-19T12:06:00Z"), asof)["status"], PENDING)
        future = classify(row(trade="2026-11-19T12:06:00Z"), asof)
        self.assertIsNone(future["trade_timestamp_utc"])
        self.assertIn("FUTURE_TRADE_TIMESTAMP_REJECTED", future["rejection_reasons"])
        item = row()
        item["iex_quote_spread_pct"] = None
        self.assertEqual(classify(item, asof)["status"], PENDING)

    def test_after_hours_weekend_and_overnight_remain_blocked(self):
        self.assertEqual(market_session(datetime(2026, 11, 19, 22, tzinfo=timezone.utc)),
                         "AFTER_HOURS")
        self.assertEqual(classify(row(), datetime(2026, 11, 21, 12, 5,
                                                  tzinfo=timezone.utc))["status"], PENDING)
        self.assertEqual(classify(row(), datetime(2026, 11, 19, 8,
                                                  tzinfo=timezone.utc))["status"], PENDING)


if __name__ == "__main__":
    unittest.main()
