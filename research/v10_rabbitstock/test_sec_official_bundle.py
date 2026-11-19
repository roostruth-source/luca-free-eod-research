from datetime import datetime, timedelta, timezone
import unittest

from build_sec_official_bundle import build
from sec_official_bundle import canonical_sha256, validate_official_bundle


ASOF = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)


class SecOfficialBundleTests(unittest.TestCase):
    def test_builder_keeps_only_requested_mapped_symbols(self):
        ticker_payload = {
            "0": {"ticker": "ABC", "cik_str": 123, "title": "ABC Inc."},
            "1": {"ticker": "XYZ", "cik_str": 456, "title": "XYZ Inc."},
        }
        submission = {"cik": 123, "filings": {"recent": {
            "form": [], "accessionNumber": [], "acceptanceDateTime": [],
            "filingDate": [], "primaryDocument": [],
        }}}
        bundle = build(ticker_payload, {"ABC": submission}, ["ABC"], ASOF)
        self.assertEqual(bundle["ticker_map"], {"ABC": 123})
        self.assertEqual(set(bundle["submissions"]), {"ABC"})
        self.assertEqual(bundle["submissions"]["ABC"]["sha256"],
                         canonical_sha256(submission))
        validated = validate_official_bundle(bundle, ASOF, ["ABC"])
        self.assertEqual(validated["provenance"]["mapped_symbols"], 1)
        self.assertEqual(validated["provenance"]["submissions_available"], 1)
        self.assertFalse(validated["provenance"]["sec_clearance"])

    def test_builder_rejects_submission_cik_mismatch(self):
        ticker_payload = {
            "0": {"ticker": "ABC", "cik_str": 123, "title": "ABC Inc."},
        }
        with self.assertRaisesRegex(ValueError, "cik_mismatch"):
            build(ticker_payload, {"ABC": {"cik": 456}}, ["ABC"], ASOF)

    def test_validator_rejects_unexpected_submission_even_with_valid_hash(self):
        ticker_payload = {
            "0": {"ticker": "ABC", "cik_str": 123, "title": "ABC Inc."},
            "1": {"ticker": "XYZ", "cik_str": 456, "title": "XYZ Inc."},
        }
        submission = {"cik": 456, "filings": {"recent": {}}}
        bundle = build(ticker_payload, {}, ["ABC"], ASOF)
        bundle["submissions"]["XYZ"] = {
            "source_url": "https://data.sec.gov/submissions/CIK0000000456.json",
            "retrieved_at_utc": ASOF.isoformat(),
            "payload": submission,
            "sha256": canonical_sha256(submission),
        }
        with self.assertRaisesRegex(ValueError, "unexpected_submission_symbol"):
            validate_official_bundle(bundle, ASOF, ["ABC"])

    def test_validator_rejects_old_submission_with_fresh_bundle_timestamp(self):
        ticker_payload = {
            "0": {"ticker": "ABC", "cik_str": 123, "title": "ABC Inc."},
        }
        submission = {"cik": 123, "filings": {"recent": {}}}
        bundle = build(ticker_payload, {"ABC": submission}, ["ABC"], ASOF)
        bundle["submissions"]["ABC"]["retrieved_at_utc"] = (
            ASOF - timedelta(hours=73)).isoformat()
        with self.assertRaisesRegex(ValueError, "sec_bundle_submission_stale"):
            validate_official_bundle(bundle, ASOF, ["ABC"])

    def test_validator_rejects_duplicate_expected_symbols(self):
        ticker_payload = {
            "0": {"ticker": "ABC", "cik_str": 123, "title": "ABC Inc."},
        }
        bundle = build(ticker_payload, {}, ["ABC"], ASOF)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_official_bundle(bundle, ASOF + timedelta(minutes=1),
                                     ["ABC", "ABC"])


if __name__ == "__main__":
    unittest.main()
