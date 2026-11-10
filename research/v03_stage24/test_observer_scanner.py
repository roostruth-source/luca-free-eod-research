"""Offline tests for LUCA V0.3 observer scanner. No network."""
import datetime as dt
import json
import unittest

from observer_scanner import build_watchlist, observation_priority, run_live_readonly

ENRICH = {
    "schema": "LUCA_V03_IEX_CANDIDATE_ENRICHMENT_V1",
    "collected_at_utc": "2026-11-11T14:00:00+00:00",
    "validation_status": "NOT_VALIDATED",
    "real_trades_allowed": False,
    "rows": [
        {
            "symbol": "AAA",
            "screener_groups": {"active_volume": 1, "active_trades": 2},
            "iex_last_trade_price": 1.5,
            "iex_quote_spread_pct": 1.0,
            "price_band_0_20_to_20": True,
            "research_status": "WATCH_ONLY_FRESH_IEX",
            "buy_allowed": False,
        },
        {
            "symbol": "BBB",
            "screener_groups": {"gainers": 1},
            "iex_last_trade_price": 2.5,
            "iex_quote_spread_pct": 8.0,
            "price_band_0_20_to_20": True,
            "research_status": "WATCH_ONLY_FRESH_IEX",
            "buy_allowed": False,
        },
        {
            "symbol": "CCC",
            "screener_groups": {"active_volume": 2},
            "iex_last_trade_price": 3.5,
            "iex_quote_spread_pct": 0.5,
            "price_band_0_20_to_20": True,
            "research_status": "PENDING_STALE_OR_MISSING",
            "buy_allowed": False,
        },
    ],
}


class ObserverScannerTests(unittest.TestCase):
    def test_ranks_only_fresh_price_band_names(self):
        out = build_watchlist(ENRICH)
        self.assertEqual(out["candidate_count"], 2)
        self.assertEqual([x["symbol"] for x in out["candidates"]], ["AAA", "BBB"])
        self.assertTrue(all(x["buy_allowed"] is False for x in out["candidates"]))
        self.assertTrue(all(x["grade"] == "WATCH_ONLY" for x in out["candidates"]))
        self.assertFalse(out["orders_allowed"])
        self.assertEqual(out["validation_status"], "NOT_VALIDATED")

    def test_priority_is_observation_only_and_prefers_multi_source(self):
        a, _ = observation_priority(ENRICH["rows"][0])
        b, _ = observation_priority(ENRICH["rows"][1])
        self.assertGreater(a, b)

    def test_unsafe_top_level_trading_flag_rejected(self):
        bad = json.loads(json.dumps(ENRICH))
        bad["real_trades_allowed"] = True
        with self.assertRaisesRegex(ValueError, "TRADING_FLAG_MUST_BE_FALSE"):
            build_watchlist(bad)

    def test_unsafe_row_buy_flag_rejected(self):
        bad = json.loads(json.dumps(ENRICH))
        bad["rows"][0]["buy_allowed"] = True
        with self.assertRaisesRegex(ValueError, "ROW_BUY_FLAG_MUST_BE_FALSE"):
            build_watchlist(bad)

    def test_live_mode_requires_explicit_approval_before_network(self):
        called = {"value": False}
        def opener(*args, **kwargs):
            called["value"] = True
            raise AssertionError("network must not be reached")
        with self.assertRaisesRegex(PermissionError, "READ_ONLY_MARKET_OBSERVATION_NOT_APPROVED"):
            run_live_readonly("key", "secret", "", now=dt.datetime.now(dt.timezone.utc), opener=opener)
        self.assertFalse(called["value"])

    def test_limit_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "INVALID_LIMIT"):
            build_watchlist(ENRICH, limit=13)


if __name__ == "__main__":
    unittest.main()
