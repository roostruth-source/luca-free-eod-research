import copy
import unittest

from prospective_ledger import append_observations


def watchlist():
    return {
        "collected_at": "2026-11-18T10:00:00+00:00",
        "rows": [{"ticker": "ABC", "iex_price": 1.0,
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
        self.assertFalse(first["events"][0]["predicted_spike"])

    def test_tampering_with_old_event_is_rejected(self):
        first = append_observations(watchlist(), "2026-11-18T10:01:00Z")
        first["events"][0]["iex_reference_price"] = 100.0
        with self.assertRaisesRegex(ValueError, "previous_ledger_chain_invalid"):
            append_observations(watchlist(), "2026-11-18T10:02:00Z", first)

    def test_future_or_unsafe_input_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "future_watchlist_not_allowed"):
            append_observations(watchlist(), "2026-11-18T09:00:00Z")
        item = watchlist()
        item["NO_ORDERS"] = False
        with self.assertRaisesRegex(ValueError, "unsafe_watchlist"):
            append_observations(item, "2026-11-18T10:01:00Z")


if __name__ == "__main__":
    unittest.main()
