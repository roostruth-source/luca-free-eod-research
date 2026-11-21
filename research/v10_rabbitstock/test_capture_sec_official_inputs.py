from datetime import datetime, timezone
import json
import unittest

from capture_sec_official_inputs import capture
from build_sec_official_bundle import build
from sec_official_bundle import validate_official_bundle

NOW = datetime(2026, 11, 19, 9, 0, tzinfo=timezone.utc)
DATE = "Thu, 19 Nov 2026 09:00:00 GMT"


class Response:
    def __init__(self, payload, date=DATE, final_url=None):
        self.raw = json.dumps(payload).encode()
        self.headers = {"Date": date}
        self.final_url = final_url
    def geturl(self):
        return self.final_url
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size=-1):
        return self.raw[:size]


def opener(request, timeout):
    if "company_tickers" in request.full_url:
        return Response({"0": {"ticker": "ABC", "cik_str": 123, "title": "ABC"}}, final_url=request.full_url)
    if "/companyfacts/" in request.full_url:
        return Response({"cik": 123, "facts": {"us-gaap": {
            "LargeUnrelatedConcept": {"units": {"USD": [{"val": 1}]}}}}}, final_url=request.full_url)
    return Response({"cik": 123, "filings": {"recent": {}}}, final_url=request.full_url)


class CaptureSecOfficialInputsTests(unittest.TestCase):
    def test_direct_capture_records_server_date_hashes_and_no_contact_value(self):
        result = capture(["ABC"], "LUCA-Research contact@example.com",
                         opener=opener, clock=lambda: NOW, sleeper=lambda _: None)
        manifest = result["manifest"]
        self.assertEqual(manifest["timestamp_basis"],
                         "SEC_HTTP_DATE_PLUS_LOCAL_UTC_CLOCK")
        self.assertEqual(manifest["ticker_map"]["http_date_utc"], NOW.isoformat())
        self.assertEqual(set(manifest["submissions"]), {"ABC"})
        self.assertEqual(set(manifest["companyfacts"]), {"ABC"})
        self.assertNotIn("contact@example.com", json.dumps(manifest))
        self.assertTrue(manifest["NO_ORDERS"])
        self.assertFalse(manifest["independent_timestamp_fully_verified"])

    def test_redirect_to_non_sec_host_fails_closed(self):
        def redirected(request, timeout):
            response = opener(request, timeout)
            response.final_url = "https://example.org/redirected.json"
            return response
        with self.assertRaisesRegex(ValueError, "final_url_mismatch"):
            capture(["ABC"], "LUCA-Research contact@example.com",
                    opener=redirected, clock=lambda: NOW, sleeper=lambda _: None)

    def test_redirect_to_different_sec_endpoint_fails_closed(self):
        def redirected(request, timeout):
            response = opener(request, timeout)
            response.final_url = "https://www.sec.gov/files/other.json"
            return response
        with self.assertRaisesRegex(ValueError, "final_url_mismatch"):
            capture(["ABC"], "LUCA-Research contact@example.com",
                    opener=redirected, clock=lambda: NOW, sleeper=lambda _: None)

    def test_missing_http_date_fails_closed(self):
        def missing(request, timeout):
            response = opener(request, timeout)
            response.headers = {}
            return response
        with self.assertRaisesRegex(ValueError, "http_date_required"):
            capture(["ABC"], "LUCA-Research contact@example.com",
                    opener=missing, clock=lambda: NOW, sleeper=lambda _: None)

    def test_excessive_clock_skew_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "clock_skew_excessive"):
            capture(["ABC"], "LUCA-Research contact@example.com",
                    opener=opener,
                    clock=lambda: datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc),
                    sleeper=lambda _: None)

    def test_get_only_official_urls(self):
        seen = []
        def checking(request, timeout):
            seen.append(request.full_url)
            self.assertEqual(request.get_method(), "GET")
            return opener(request, timeout)
        capture(["ABC"], "LUCA-Research contact@example.com",
                opener=checking, clock=lambda: NOW, sleeper=lambda _: None)
        self.assertEqual(seen[0], "https://www.sec.gov/files/company_tickers.json")
        self.assertEqual(seen[1],
                         "https://data.sec.gov/submissions/CIK0000000123.json")
        self.assertEqual(seen[2],
                         "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000123.json")
        self.assertTrue(all("orders" not in url for url in seen))

    def test_capture_manifest_builds_bundle_with_revalidated_time_provenance(self):
        result = capture(["ABC"], "LUCA-Research contact@example.com",
                         opener=opener, clock=lambda: NOW, sleeper=lambda _: None)
        bundle = build(result["ticker_payload"], result["submission_payloads"],
                       ["ABC"], NOW, capture_manifest=result["manifest"],
                       companyfacts_payloads=result["companyfacts_payloads"])
        validated = validate_official_bundle(bundle, NOW, ["ABC"])
        provenance = validated["provenance"]
        self.assertEqual(provenance["retrieval_time_provenance"],
                         "SEC_HTTP_DATE_PLUS_LOCAL_UTC_CLOCK")
        self.assertTrue(provenance["capture_manifest_revalidated"])
        self.assertEqual(provenance["companyfacts_available"], 1)
        self.assertNotIn("us-gaap", bundle["companyfacts"]["ABC"]["payload"]["facts"])
        self.assertNotEqual(bundle["companyfacts"]["ABC"]["sha256"],
                            bundle["companyfacts"]["ABC"]["source_sha256"])
        self.assertFalse(provenance["independent_timestamp_fully_verified"])

    def test_validator_rejects_receipt_outside_capture_window(self):
        result = capture(["ABC"], "LUCA-Research contact@example.com",
                         opener=opener, clock=lambda: NOW, sleeper=lambda _: None)
        bundle = build(result["ticker_payload"], result["submission_payloads"],
                       ["ABC"], NOW, capture_manifest=result["manifest"],
                       companyfacts_payloads=result["companyfacts_payloads"])
        # A consistent hash and HTTP Date cannot justify a receipt timestamp
        # outside the capture's own started/completed window.
        earlier = "2026-11-19T08:00:00+00:00"
        bundle["submissions"]["ABC"]["retrieved_at_utc"] = earlier
        receipt = bundle["capture_manifest"]["submissions"]["ABC"]
        receipt["retrieved_at_utc"] = earlier
        receipt["http_date_utc"] = earlier
        with self.assertRaisesRegex(ValueError, "submission_outside_window"):
            validate_official_bundle(bundle, NOW, ["ABC"])

    def test_tampered_capture_receipt_is_rejected_by_builder(self):
        result = capture(["ABC"], "LUCA-Research contact@example.com",
                         opener=opener, clock=lambda: NOW, sleeper=lambda _: None)
        result["manifest"]["submissions"]["ABC"]["http_date_utc"] = (
            "2026-11-19T07:00:00+00:00")
        with self.assertRaisesRegex(ValueError, "receipt_time_invalid"):
            build(result["ticker_payload"], result["submission_payloads"],
                  ["ABC"], NOW, capture_manifest=result["manifest"],
                  companyfacts_payloads=result["companyfacts_payloads"])


if __name__ == "__main__":
    unittest.main()
