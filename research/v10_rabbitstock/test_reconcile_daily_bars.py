import unittest

from reconcile_daily_bars import reconcile_bar


def source(name, close=10.0):
    return {
        "source_name": name,
        "source_url": f"https://example.com/{name}",
        "retrieved_at": "2026-11-13T06:33:00+09:00",
        "session_close_at": "2026-11-12T16:00:00-05:00",
        "open": 9.8,
        "high": 10.5,
        "low": 9.5,
        "close": close,
        "complete": True,
        "price_basis": "SPLIT_ADJUSTED_TO_SIGNAL",
    }


def payload(*sources):
    return {
        "ticker": "AAA",
        "signal_at": "2026-11-12T00:08:00+09:00",
        "evaluation_asof": "2026-11-13T06:33:00+09:00",
        "ohlc_tolerance_pct": 1.0,
        "sources": list(sources),
    }


class ReconcileDailyBarsTests(unittest.TestCase):
    def test_two_sources_within_tolerance_emit_median_bar(self):
        first = source("A", 10.0)
        second = source("B", 10.05)
        result = reconcile_bar(payload(first, second))
        self.assertEqual(result["reconciliation_status"], "VERIFIED")
        self.assertAlmostEqual(result["canonical_bar"]["close"], 10.025)
        self.assertEqual(result["canonical_bar"]["source_count"], 2)
        self.assertTrue(result["WATCH_ONLY"])
        self.assertTrue(result["NO_ORDERS"])

    def test_whlr_public_source_conflict_blocks_bar(self):
        first = source("ChartExchange", 0.5100)
        first.update({"open": 0.5800, "high": 0.5800, "low": 0.4300})
        second = source("Investing", 0.5398)
        second.update({"open": 0.5892, "high": 0.5984, "low": 0.4137})
        result = reconcile_bar(payload(first, second))
        self.assertEqual(result["reconciliation_status"], "SOURCE_CONFLICT")
        self.assertIsNone(result["canonical_bar"])
        self.assertIn("close", result["conflicting_fields"])
        self.assertGreater(result["field_spread_pct"]["close"], 5.0)

    def test_single_source_is_unverified(self):
        result = reconcile_bar(payload(source("A")))
        self.assertEqual(result["reconciliation_status"], "SINGLE_SOURCE_UNVERIFIED")
        self.assertIsNone(result["canonical_bar"])

    def test_duplicate_source_is_not_independent(self):
        with self.assertRaisesRegex(ValueError, "duplicate_source_not_independent"):
            reconcile_bar(payload(source("A"), source("A")))

    def test_duplicate_source_url_is_not_independent(self):
        first = source("A")
        second = source("B")
        second["source_url"] = first["source_url"]
        with self.assertRaisesRegex(ValueError, "duplicate_source_url_not_independent"):
            reconcile_bar(payload(first, second))

    def test_https_source_url_is_required(self):
        item = source("A")
        item["source_url"] = "http://example.com/A"
        with self.assertRaisesRegex(ValueError, "https_source_url_required"):
            reconcile_bar(payload(item, source("B")))

    def test_future_source_retrieval_is_rejected(self):
        item = source("A")
        item["retrieved_at"] = "2026-11-13T07:00:00+09:00"
        with self.assertRaisesRegex(ValueError, "future_source_retrieval_not_allowed"):
            reconcile_bar(payload(item, source("B")))

    def test_split_adjusted_basis_is_required(self):
        item = source("A")
        item["price_basis"] = "UNKNOWN"
        with self.assertRaisesRegex(ValueError, "split_adjusted_price_basis_required"):
            reconcile_bar(payload(item, source("B")))


if __name__ == "__main__":
    unittest.main()
