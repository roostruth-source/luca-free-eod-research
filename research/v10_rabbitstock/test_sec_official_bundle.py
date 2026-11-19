from datetime import datetime, timedelta, timezone
import unittest
import json
from email.utils import format_datetime
from capture_sec_official_inputs import capture

from build_sec_official_bundle import build
from sec_official_bundle import canonical_sha256, validate_official_bundle


ASOF = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)


def captured_bundle(ticker_payload, submissions, symbols):
    class Response:
        headers = {"Date": format_datetime(ASOF, usegmt=True)}
        def __init__(self, payload):
            self.raw = json.dumps(payload).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, size=-1):
            return self.raw[:size]
    def opener(request, timeout):
        if "company_tickers" in request.full_url:
            return Response(ticker_payload)
        cik = int(request.full_url.rsplit("CIK", 1)[1].split(".json")[0])
        for payload in submissions.values():
            if payload.get("cik") == cik:
                return Response(payload)
        raise ValueError("fixture_missing_submission")
    requested_empty = not submissions
    if requested_empty:
        submissions = {symbol: {"cik": int(row["cik_str"])}
                       for row in ticker_payload.values()
                       for symbol in symbols if row["ticker"] == symbol}
    result = capture(symbols, "LUCA-Research contact@example.com",
                     opener=opener, clock=lambda: ASOF, sleeper=lambda _: None)
    bundle = build(result["ticker_payload"], result["submission_payloads"],
                   symbols, ASOF, capture_manifest=result["manifest"])
    if requested_empty:
        bundle["submissions"].clear()
        bundle["capture_manifest"]["submissions"].clear()
    return bundle


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
        bundle = captured_bundle(ticker_payload, {"ABC": submission}, ["ABC"])
        self.assertEqual(bundle["ticker_map"], {"ABC": 123})
        self.assertEqual(set(bundle["submissions"]), {"ABC"})
        self.assertEqual(bundle["submissions"]["ABC"]["sha256"],
                         canonical_sha256(submission))
        validated = validate_official_bundle(bundle, ASOF, ["ABC"])
        self.assertEqual(validated["provenance"]["mapped_symbols"], 1)
        self.assertEqual(validated["provenance"]["submissions_available"], 1)
        self.assertFalse(validated["provenance"]["sec_clearance"])

    def test_builder_rejects_missing_capture_manifest(self):
        with self.assertRaisesRegex(ValueError, "sec_capture_manifest_required"):
            build({}, {}, ["ABC"], ASOF)

    def test_validator_rejects_missing_capture_manifest(self):
        bundle = captured_bundle({"0": {"ticker": "ABC", "cik_str": 123,
                                       "title": "ABC"}}, {}, ["ABC"])
        del bundle["capture_manifest"]
        with self.assertRaisesRegex(ValueError, "sec_bundle_capture_manifest_required"):
            validate_official_bundle(bundle, ASOF, ["ABC"])

    def test_builder_rejects_submission_cik_mismatch(self):
        ticker_payload = {
            "0": {"ticker": "ABC", "cik_str": 123, "title": "ABC Inc."},
        }
        bundle = captured_bundle(ticker_payload, {"ABC": {"cik": 123}}, ["ABC"])
        bundle["submissions"]["ABC"]["payload"]["cik"] = 456
        with self.assertRaisesRegex(ValueError, "submission_payload_invalid"):
            validate_official_bundle(bundle, ASOF, ["ABC"])

    def test_validator_rejects_unexpected_submission_even_with_valid_hash(self):
        ticker_payload = {
            "0": {"ticker": "ABC", "cik_str": 123, "title": "ABC Inc."},
            "1": {"ticker": "XYZ", "cik_str": 456, "title": "XYZ Inc."},
        }
        submission = {"cik": 456, "filings": {"recent": {}}}
        bundle = captured_bundle(ticker_payload, {}, ["ABC"])
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
        bundle = captured_bundle(ticker_payload, {"ABC": submission}, ["ABC"])
        bundle["submissions"]["ABC"]["retrieved_at_utc"] = (
            ASOF - timedelta(hours=73)).isoformat()
        with self.assertRaisesRegex(ValueError, "sec_bundle_submission_stale"):
            validate_official_bundle(bundle, ASOF, ["ABC"])

    def test_validator_rejects_duplicate_expected_symbols(self):
        ticker_payload = {
            "0": {"ticker": "ABC", "cik_str": 123, "title": "ABC Inc."},
        }
        bundle = captured_bundle(ticker_payload, {}, ["ABC"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_official_bundle(bundle, ASOF + timedelta(minutes=1),
                                     ["ABC", "ABC"])


if __name__ == "__main__":
    unittest.main()
