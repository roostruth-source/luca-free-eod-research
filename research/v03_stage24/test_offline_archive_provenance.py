"""Offline synthetic receipt integrity tests; no network or live observations."""
import copy
import datetime as dt
import unittest

from mobile_outcomes import _time
from offline_archive_provenance import audit_claimed_receipts
from offline_multisession_audit import audit_session_bundle
from test_offline_multisession_audit import session

UTC = dt.timezone.utc


def receipt(item, capture_id="synthetic-capture-1"):
    summary = audit_session_bundle([item])["sessions"][0]
    anchor = _time(summary["reference_time_utc"])
    bars = [_time(bar["t"]) for row in item["raw"]["rows"] for bar in row["ohlcv"]]
    captured = max([anchor] + [bar + dt.timedelta(minutes=1) for bar in bars])
    return {
        "session_day_ny": item["session_day_ny"],
        "observation_id": summary["observation_id"],
        "capture_id": capture_id,
        "source_label": "test-only",
        "source_kind": "SYNTHETIC",
        "raw_content_sha256": summary["raw_content_sha256"],
        "commitment_sha256": summary["commitment_sha256"],
        "claimed_commitment_recorded_at_utc": (
            anchor - dt.timedelta(minutes=1)).isoformat(),
        "claimed_raw_captured_at_utc": captured.isoformat(),
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "orders_allowed": False,
        "real_trades_allowed": False,
        "source_externally_verified": False,
        "timestamps_externally_verified": False,
    }


class ClaimedProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.one = session()
        self.r1 = receipt(self.one)

    def audit(self, receipt_override=None):
        return audit_claimed_receipts([self.one], [receipt_override or self.r1])

    def test_valid_self_report_remains_unverified(self):
        result = self.audit()
        self.assertEqual(result["session_count_with_consistent_claimed_receipts"], 1)
        self.assertFalse(result["source_provenance_verified"])
        self.assertFalse(result["commitment_timestamp_externally_verified"])
        self.assertFalse(result["orders_allowed"])
        self.assertEqual(result["all_grades"], "D")
        self.assertIn("SYNTHETIC_RECEIPT_NOT_MARKET_EVIDENCE", result["warnings"])

    def test_two_days_have_two_distinct_receipts_without_independence_claim(self):
        other = session("2026-10-30", "day-2")
        result = audit_claimed_receipts(
            [self.one, other], [self.r1, receipt(other, "synthetic-capture-2")])
        self.assertEqual(result["session_count_with_consistent_claimed_receipts"], 2)
        self.assertEqual(result["independent_sample_count_verified"], 0)

    def test_wrong_raw_hash_rejected(self):
        self.r1["raw_content_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "RECEIPT_RAW_HASH_MISMATCH"):
            self.audit()

    def test_wrong_manifest_hash_rejected(self):
        self.r1["commitment_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "RECEIPT_COMMITMENT_HASH_MISMATCH"):
            self.audit()

    def test_missing_receipt_rejected(self):
        with self.assertRaisesRegex(ValueError, "RECEIPT_COVERAGE_MISMATCH"):
            audit_claimed_receipts([self.one], [])

    def test_duplicate_capture_id_rejected(self):
        other = session("2026-10-30", "day-2")
        with self.assertRaisesRegex(ValueError, "REUSED_CAPTURE_ID"):
            audit_claimed_receipts([self.one, other],
                                   [self.r1, receipt(other, "synthetic-capture-1")])

    def test_duplicate_receipt_day_rejected(self):
        other = session("2026-10-30", "day-2")
        with self.assertRaisesRegex(ValueError, "RECEIPT_DAY_MISSING_OR_DUPLICATED"):
            audit_claimed_receipts([self.one, other], [self.r1, copy.deepcopy(self.r1)])

    def test_claimed_precommit_after_reference_rejected(self):
        anchor = _time(self.one["manifest"]["payload"]["reference_time_utc"])
        self.r1["claimed_commitment_recorded_at_utc"] = (
            anchor + dt.timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "CLAIMED_COMMITMENT_AFTER_REFERENCE"):
            self.audit()

    def test_claimed_capture_before_reference_rejected(self):
        anchor = _time(self.one["manifest"]["payload"]["reference_time_utc"])
        self.r1["claimed_raw_captured_at_utc"] = (
            anchor - dt.timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError, "CLAIMED_CAPTURE_BEFORE_REFERENCE"):
            self.audit()

    def test_capture_at_bar_start_not_close_rejected(self):
        bars = [_time(bar["t"]) for row in self.one["raw"]["rows"] for bar in row["ohlcv"]]
        self.r1["claimed_raw_captured_at_utc"] = max(bars).isoformat()
        with self.assertRaisesRegex(ValueError, "CLAIMED_CAPTURE_BEFORE_LAST_BAR_CLOSE"):
            self.audit()

    def test_non_utc_claimed_timestamp_rejected(self):
        self.r1["claimed_raw_captured_at_utc"] = "2026-10-29T11:30:00-04:00"
        with self.assertRaisesRegex(ValueError, "NOT_UTC_RAW_CAPTURED_AT"):
            self.audit()

    def test_naive_claimed_timestamp_rejected(self):
        self.r1["claimed_commitment_recorded_at_utc"] = "2026-10-29T14:04:00"
        with self.assertRaisesRegex(ValueError, "NOT_UTC_COMMITMENT_RECORDED_AT"):
            self.audit()

    def test_unsafe_or_unverified_claim_rejected(self):
        self.r1["source_externally_verified"] = True
        with self.assertRaisesRegex(ValueError, "UNSAFE_OR_UNSUPPORTED_RECEIPT_CLAIM"):
            self.audit()

    def test_source_kind_cannot_claim_verified(self):
        self.r1["source_kind"] = "OFFICIALLY_VERIFIED"
        with self.assertRaisesRegex(ValueError, "UNVERIFIED_SOURCE_KIND_REQUIRED"):
            self.audit()

    def test_empty_bars_warn_not_price_evidence(self):
        for row in self.one["raw"]["rows"]:
            row["ohlcv"] = []
            row["signals"] = []
        r = receipt(self.one)
        result = audit_claimed_receipts([self.one], [r])
        self.assertIn("ZERO_BAR_RECEIPT_CANNOT_ESTABLISH_PRICE_COLLECTION", result["warnings"])
        self.assertEqual(result["receipts"][0]["raw_bar_count"], 0)

    def test_non_string_day_rejected_cleanly(self):
        self.r1["session_day_ny"] = []
        with self.assertRaisesRegex(ValueError, "RECEIPT_DAY_MISSING_OR_DUPLICATED"):
            self.audit()

    def test_non_string_source_kind_rejected_cleanly(self):
        self.r1["source_kind"] = []
        with self.assertRaisesRegex(ValueError, "UNVERIFIED_SOURCE_KIND_REQUIRED"):
            self.audit()

    def test_future_bars_are_outcomes_not_asof_evidence(self):
        result = self.audit()
        self.assertGreater(result["receipts"][0]["post_reference_raw_bar_count"], 0)
        self.assertIn("POST_REFERENCE_BARS_ARE_OUTCOMES_NOT_ASOF_SIGNAL_EVIDENCE",
                      result["warnings"])

    def test_observation_id_mismatch_rejected(self):
        self.r1["observation_id"] = "different"
        with self.assertRaisesRegex(ValueError, "RECEIPT_OBSERVATION_ID_MISMATCH"):
            self.audit()


if __name__ == "__main__":
    unittest.main()
