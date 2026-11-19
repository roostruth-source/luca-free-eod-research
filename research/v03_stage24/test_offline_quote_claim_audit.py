"""Synthetic-only quote-claim regressions. No provider, orders, or network."""
import copy
import datetime as dt
import unittest

from mobile_outcomes import _time
from offline_quote_claim_audit import audit_quote_claims
from test_offline_asof_availability import at_reference
from test_offline_multisession_audit import session


def ready():
    return at_reference(session(), 6)


def quote(item, symbol="TESTA", offset=1):
    ref = _time(item["manifest"]["payload"]["reference_time_utc"])
    stamp = ref + dt.timedelta(seconds=offset)
    return {
        "session_day_ny": item["session_day_ny"],
        "symbol": symbol,
        "quote_time_utc": stamp.isoformat(),
        "captured_at_utc": (stamp + dt.timedelta(seconds=1)).isoformat(),
        "bid": 1.01, "ask": 1.03, "bid_size": 100, "ask_size": 200,
        "venue": "SYNTHETIC", "provider": "UNVERIFIED_TEST", "quote_id": "fake-1",
    }


class QuoteClaimAuditTests(unittest.TestCase):
    def test_missing_quotes_are_not_execution_evidence(self):
        report = audit_quote_claims([ready()])
        self.assertEqual(report["claims_supplied"], 0)
        self.assertEqual(report["sessions"][0]["missing_quote_evidence_count"], 1)
        row = next(r for r in report["sessions"][0]["rows"] if r["symbol"] == "TESTA")
        self.assertEqual(row["status"], "MISSING_QUOTE_EVIDENCE")
        self.assertFalse(row["quote_executable_verified"])
        self.assertFalse(row["orders_allowed"])

    def test_complete_synthetic_claim_still_never_verifies_quote(self):
        item = ready()
        report = audit_quote_claims([item], [quote(item)])
        self.assertEqual(report["sessions"][0]["unverified_claim_count"], 1)
        row = next(r for r in report["sessions"][0]["rows"] if r["symbol"] == "TESTA")
        self.assertEqual(row["status"], "STRUCTURALLY_PLAUSIBLE_UNVERIFIED_QUOTE_CLAIM")
        for field in ("quote_source_authenticated", "quote_timestamp_externally_verified",
                      "quote_executable_verified", "actual_liquidity_verified",
                      "fill_price_verified", "order_ready", "orders_allowed"):
            self.assertFalse(row[field], field)

    def test_future_signal_not_promoted_by_quote(self):
        item = session()
        report = audit_quote_claims([item])
        row = next(r for r in report["sessions"][0]["rows"] if r["symbol"] == "TESTA")
        self.assertEqual(row["status"], "NO_FROZEN_OBSERVATION_WINDOW")
        self.assertFalse(row["frozen_signal_ready"])

    def test_unknown_symbol_claim_rejected(self):
        item = ready()
        with self.assertRaisesRegex(ValueError, "UNKNOWN_QUOTE_CLAIM_CANDIDATE"):
            audit_quote_claims([item], [quote(item, "INVENTED")])

    def test_duplicate_quote_claim_rejected(self):
        item = ready()
        with self.assertRaisesRegex(ValueError, "DUPLICATE_QUOTE_CLAIM"):
            audit_quote_claims([item], [quote(item), quote(item)])

    def test_claim_must_not_include_order_authorization(self):
        item = ready()
        claim = quote(item)
        claim["orders_allowed"] = True
        with self.assertRaisesRegex(ValueError, "INVALID_QUOTE_CLAIM_FIELDS"):
            audit_quote_claims([item], [claim])

    def test_missing_quote_field_rejected(self):
        item = ready()
        claim = quote(item)
        del claim["provider"]
        with self.assertRaisesRegex(ValueError, "INVALID_QUOTE_CLAIM_FIELDS"):
            audit_quote_claims([item], [claim])

    def test_invalid_prices_and_sizes_rejected(self):
        item = ready()
        for key, value in (("bid", True), ("bid", float("nan")), ("ask", 0),
                           ("ask_size", -1), ("bid_size", "100")):
            with self.subTest(key=key, value=value):
                claim = quote(item)
                claim[key] = value
                with self.assertRaisesRegex(ValueError, "INVALID_"):
                    audit_quote_claims([item], [claim])

    def test_crossed_or_locked_quote_rejected(self):
        item = ready()
        for ask in (1.01, 1.00):
            claim = quote(item)
            claim["ask"] = ask
            with self.assertRaisesRegex(ValueError, "LOCKED_OR_CROSSED"):
                audit_quote_claims([item], [claim])

    def test_quote_before_review_rejected(self):
        item = ready()
        with self.assertRaisesRegex(ValueError, "QUOTE_CLAIM_BEFORE_HYPOTHETICAL_REVIEW"):
            audit_quote_claims([item], [quote(item, offset=-1)])

    def test_capture_before_quote_rejected(self):
        item = ready()
        claim = quote(item)
        claim["captured_at_utc"] = (_time(claim["quote_time_utc"])
                                    - dt.timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "CAPTURE_BEFORE_QUOTE"):
            audit_quote_claims([item], [claim])

    def test_stale_capture_rejected(self):
        item = ready()
        claim = quote(item)
        claim["captured_at_utc"] = (_time(claim["quote_time_utc"])
                                    + dt.timedelta(seconds=6)).isoformat()
        with self.assertRaisesRegex(ValueError, "STALE_QUOTE_CLAIM"):
            audit_quote_claims([item], [claim])

    def test_naive_timestamp_rejected(self):
        item = ready()
        claim = quote(item)
        claim["quote_time_utc"] = "2026-10-29T14:05:01"
        with self.assertRaisesRegex(ValueError, "NAIVE_QUOTE_TIME"):
            audit_quote_claims([item], [claim])

    def test_quote_at_scheduled_close_rejected(self):
        item = ready()
        claim = quote(item)
        claim["quote_time_utc"] = "2026-10-29T20:00:00+00:00"
        claim["captured_at_utc"] = claim["quote_time_utc"]
        with self.assertRaisesRegex(ValueError, "QUOTE_CLAIM_AT_OR_AFTER_SCHEDULED_CLOSE"):
            audit_quote_claims([item], [claim])

    def test_multiple_days_not_independent_win_rate(self):
        report = audit_quote_claims([
            session(), session("2026-10-30", "day-2")
        ])
        self.assertEqual(report["session_count"], 2)
        self.assertEqual(report["independent_sample_count_verified"], 0)
        self.assertFalse(report["aggregate_win_rate_computed"])
        self.assertIn("REPEATED_SYMBOL_ACROSS_DAYS_NOT_INDEPENDENT", report["warnings"])

    def test_weekend_and_holiday_rejected(self):
        for day in ("2026-10-31", "2026-11-26"):
            with self.subTest(day=day), self.assertRaisesRegex(
                    ValueError, "CLOSED_OR_UNSUPPORTED_NY_SESSION_DATE"):
                audit_quote_claims([session(day)])

    def test_no_order_safety_contract(self):
        report = audit_quote_claims([ready()])
        self.assertEqual(report["validation_status"], "NOT_VALIDATED")
        self.assertEqual(report["sec_status"], "SEC_UNVERIFIED")
        self.assertEqual(report["all_grades"], "D")
        self.assertEqual(report["operating_mode"], "NO_ORDERS")
        for key in ("orders_allowed", "real_trades_allowed", "actual_fill_verified",
                    "real_time_market_status_verified", "quote_source_authenticated",
                    "prediction_accuracy_verified"):
            self.assertFalse(report[key], key)


if __name__ == "__main__":
    unittest.main()
