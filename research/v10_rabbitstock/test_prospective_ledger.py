import copy
import unittest

from prospective_ledger import append_observations


def watchlist():
    return {
        "collected_at": "2026-11-18T10:00:00+00:00",
        "rows": [{"ticker": "ABC", "iex_price": 1.0,
                  "screener_groups": {"active_volume": 4, "gainers": 2},
                  "iex_quote_spread_pct": 1.25,
                  "volume_first_context": {
                      "status": "OUTSIDE_US_REGULAR_CONTEXT_WINDOW",
                      "volume_first_recent": False, "NO_ORDERS": True,
                  },
                  "research_priority_score": 52,
                  "research_priority_rank": 1,
                  "research_priority_label": "PRIORITY_2_WATCH",
                  "priority_reasons": [{"code": "FRESH_IEX", "ko": "최근 가격"}],
                  "risk_flags": ["SEC_UNVERIFIED"],
                  "priority_is_buy_signal": False, "buy_allowed": False,
                  "security_scope": {
                      "status": "COMMON_EQUITY_CANDIDATE_SCOPE",
                      "security_name": "ABC Inc. Common Stock", "etf_flag": "N",
                      "test_issue": "N", "exchange_code": "NASDAQ",
                      "financial_status": "N", "financial_status_label": "NORMAL",
                      "financial_status_risk": False, "financial_status_ko": "정상",
                      "source_url": "https://example.test/directory",
                  },
                  "iex_status": "PENDING_STALE_OR_MISSING",
                  "sec_status": "SEC_NOT_CHECKED_CONTACT_REQUIRED"}],
        "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
    }


class ProspectiveLedgerTests(unittest.TestCase):
    def test_append_is_deterministic_and_stale_remains_blocked(self):
        first = append_observations(watchlist(), "2026-11-18T10:01:00Z")
        again = append_observations(watchlist(), "2026-11-18T10:02:00Z", first)
        self.assertEqual(first["event_count"], 1)
        self.assertEqual(again["new_event_count"], 0)
        self.assertEqual(first["last_chain_hash"], again["last_chain_hash"])
        self.assertEqual(first["events"][0]["observation_status"], "STALE_OR_MISSING_PRICE_BLOCKED")
        self.assertEqual(first["events"][0]["screener_groups"],
                         {"active_volume": 4, "gainers": 2})
        self.assertEqual(first["events"][0]["iex_quote_spread_pct"], 1.25)
        self.assertEqual(first["events"][0]["volume_first_context"]["status"],
                         "OUTSIDE_US_REGULAR_CONTEXT_WINDOW")
        self.assertEqual(first["events"][0]["research_priority"]["label"],
                         "PRIORITY_2_WATCH")
        self.assertFalse(first["events"][0]["research_priority"]["priority_is_buy_signal"])
        self.assertEqual(first["events"][0]["security_scope"]["status"],
                         "COMMON_EQUITY_CANDIDATE_SCOPE")
        self.assertEqual(first["events"][0]["security_scope"]["financial_status_label"],
                         "NORMAL")
        self.assertEqual(first["events"][0]["security_scope"]["financial_status_ko"],
                         "정상")
        self.assertFalse(first["events"][0]["predicted_spike"])

    def test_tampering_with_old_event_is_rejected(self):
        first = append_observations(watchlist(), "2026-11-18T10:01:00Z")
        first["events"][0]["iex_reference_price"] = 100.0
        with self.assertRaisesRegex(ValueError, "previous_ledger_chain_invalid"):
            append_observations(watchlist(), "2026-11-18T10:02:00Z", first)

    def test_next_collection_continues_chain_without_rewriting_old_event(self):
        first = append_observations(watchlist(), "2026-11-18T10:01:00Z")
        later = watchlist()
        later["collected_at"] = "2026-11-19T10:00:00Z"
        later["rows"][0]["iex_price"] = 1.2
        second = append_observations(later, "2026-11-19T10:01:00Z", first)
        self.assertEqual(second["continuity_status"], "CHAIN_CONTINUED")
        self.assertEqual(second["event_count"], 2)
        self.assertEqual(second["events"][0], first["events"][0])
        self.assertNotEqual(second["last_chain_hash"], first["last_chain_hash"])

    def test_same_timestamp_revision_is_not_silently_ignored(self):
        first = append_observations(watchlist(), "2026-11-18T10:01:00Z")
        changed = watchlist()
        changed["rows"][0]["iex_price"] = 1.2
        with self.assertRaisesRegex(ValueError, "same_time_report_revision_not_allowed"):
            append_observations(changed, "2026-11-18T10:02:00Z", first)

    def test_future_or_unsafe_input_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "future_watchlist_not_allowed"):
            append_observations(watchlist(), "2026-11-18T09:00:00Z")
        item = watchlist()
        item["NO_ORDERS"] = False
        with self.assertRaisesRegex(ValueError, "unsafe_watchlist"):
            append_observations(item, "2026-11-18T10:01:00Z")

    def test_invalid_candidate_context_is_rejected(self):
        item = watchlist()
        item["rows"][0]["screener_groups"] = {"active_volume": 0}
        with self.assertRaisesRegex(ValueError, "invalid_screener_context"):
            append_observations(item, "2026-11-18T10:01:00Z")

    def test_future_volume_first_pattern_is_rejected(self):
        item = watchlist()
        item["rows"][0]["volume_first_context"] = {
            "status": "RECENT_VOLUME_FIRST_PATTERN_RESEARCH_ONLY",
            "volume_first_recent": True,
            "latest_pattern": {"iex_volume_ratio": 4.0,
                               "six_bar_price_change_pct": 2.0,
                               "bar_knowable_after_utc": "2026-11-18T10:01:00Z"},
            "evidence_bars": [], "NO_ORDERS": True,
        }
        with self.assertRaisesRegex(ValueError, "future_volume_first_pattern_not_allowed"):
            append_observations(item, "2026-11-18T10:02:00Z")

    def test_priority_cannot_be_turned_into_buy_signal(self):
        item = watchlist()
        item["rows"][0]["priority_is_buy_signal"] = True
        with self.assertRaisesRegex(ValueError, "invalid_research_priority"):
            append_observations(item, "2026-11-18T10:01:00Z")

    def test_premarket_price_context_is_frozen_as_separate_fresh_observation(self):
        item = watchlist()
        item["collected_at"] = "2026-11-18T12:05:00Z"
        row = item["rows"][0]
        row["iex_status"] = "WATCH_ONLY_FRESH_IEX_PREMARKET"
        row["price_session_context"] = {
            "status": "WATCH_ONLY_FRESH_IEX_PREMARKET",
            "market_session": "PREMARKET",
            "trade_timestamp_utc": "2026-11-18T12:04:00Z",
            "quote_timestamp_utc": "2026-11-18T12:04:30Z",
            "trade_age_seconds": 60, "quote_age_seconds": 30,
            "trade_fresh": True, "quote_fresh": True,
            "full_market_quote_verified": False,
            "source": "ALPACA_IEX_SINGLE_EXCHANGE_NOT_SIP", "NO_ORDERS": True,
        }
        result = append_observations(item, "2026-11-18T12:06:00Z")
        event = result["events"][0]
        self.assertEqual(event["observation_status"], "FRESH_PREMARKET_WATCH_ONLY")
        self.assertEqual(event["price_session_context"]["market_session"], "PREMARKET")

    def test_future_or_full_market_price_context_claim_is_rejected(self):
        item = watchlist()
        row = item["rows"][0]
        row["price_session_context"] = {
            "status": row["iex_status"], "market_session": "PREMARKET",
            "trade_timestamp_utc": "2026-11-18T10:01:00Z",
            "quote_timestamp_utc": "2026-11-18T09:59:00Z",
            "full_market_quote_verified": False, "NO_ORDERS": True,
        }
        with self.assertRaisesRegex(ValueError, "future_price_session_evidence"):
            append_observations(item, "2026-11-18T10:02:00Z")
        row["price_session_context"]["trade_timestamp_utc"] = "2026-11-18T09:59:00Z"
        row["price_session_context"]["full_market_quote_verified"] = True
        with self.assertRaisesRegex(ValueError, "full_market_quote_claim_not_allowed"):
            append_observations(item, "2026-11-18T10:02:00Z")


if __name__ == "__main__":
    unittest.main()
