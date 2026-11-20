from datetime import datetime, timezone
import unittest

from issuer_region_context import build
from sec_document_review import review_text


ASOF = datetime(2026, 11, 18, 15, tzinfo=timezone.utc)
URL = "https://www.sec.gov/Archives/edgar/data/123/000000012326000001/filing.htm"


def review(document: str) -> dict:
    result = review_text(document, URL)
    result["accepted_at_utc"] = "2026-11-17T12:00:00Z"
    result["form"] = "20-F"
    return result


class IssuerRegionContextTests(unittest.TestCase):
    def test_narrow_prc_operations_text_routes_to_china_research_cohort(self):
        item = review("""
            <p>Substantially all of our operations are conducted in the
            People's Republic of China through our PRC subsidiaries.</p>
        """)
        result = build([item], 0, ASOF)
        self.assertEqual(result["detector_profile"], "CHINA_1_0")
        self.assertEqual(result["issuer_region"], "PRC_OPERATIONS")
        self.assertTrue(result["official_sec_text_evidence"])
        self.assertFalse(result["current_operating_region_confirmed"])
        self.assertFalse(result["classification_is_buy_signal"])

    def test_generic_china_mention_does_not_classify(self):
        item = review("We buy a small amount of packaging from China.")
        result = build([item], 0, ASOF)
        self.assertEqual(result["detector_profile"], "NASDAQ_7_0")
        self.assertEqual(result["issuer_region"], "UNVERIFIED")
        self.assertFalse(result["official_sec_text_evidence"])

    def test_missing_or_partial_text_never_proves_non_china_status(self):
        missing = build([], 2, ASOF)
        self.assertEqual(missing["status"], "SEC_ISSUER_REGION_TEXT_UNAVAILABLE")
        self.assertEqual(missing["issuer_region"], "UNVERIFIED")
        partial = build([review("No relevant phrase here")], 1, ASOF)
        self.assertEqual(partial["status"],
                         "PARTIAL_TEXT_REVIEW_NO_PRC_OPERATIONS_NOT_PROOF")

    def test_future_and_spoofed_sources_fail_closed(self):
        future = review("Our principal operations in China")
        future["accepted_at_utc"] = "2026-11-19T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "future_issuer_region"):
            build([future], 0, ASOF)
        spoofed = review("Our principal operations in China")
        spoofed["source_url"] = "https://www.sec.gov.evil.test/Archives/x"
        with self.assertRaisesRegex(ValueError, "issuer_region_sec_source"):
            build([spoofed], 0, ASOF)


if __name__ == "__main__":
    unittest.main()
