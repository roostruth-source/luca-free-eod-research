from datetime import datetime, timezone
import unittest

from listing_action_context import build


ASOF = datetime(2026, 11, 18, 15, tzinfo=timezone.utc)
URL = "https://www.sec.gov/Archives/edgar/data/123/000000012326000001/filing.htm"


def review(*terms):
    return {
        "source_url": URL,
        "accepted_at_utc": "2026-11-17T12:00:00+00:00",
        "form": "8-K",
        "matched_terms": [{"term": term, "context": term + " context"}
                          for term in terms],
    }


class ListingActionContextTests(unittest.TestCase):
    def test_official_sec_terms_create_conservative_hold_context(self):
        result = build([review("REVERSE_SPLIT", "MINIMUM_BID")], 0, ASOF)
        self.assertTrue(result["risk_detected"])
        self.assertEqual({signal["code"] for signal in result["signals"]},
                         {"REVERSE_SPLIT", "MINIMUM_BID"})
        self.assertFalse(result["current_status_confirmed"])
        self.assertFalse(result["effective_date_confirmed"])
        self.assertFalse(result["sec_clearance"])
        self.assertTrue(result["NO_ORDERS"])

    def test_missing_or_partial_text_never_claims_clearance(self):
        missing = build([], 2, ASOF)
        self.assertEqual(missing["status"], "SEC_LISTING_TEXT_UNAVAILABLE")
        self.assertFalse(missing["risk_detected"])
        partial = build([review("ATM")], 1, ASOF)
        self.assertEqual(partial["status"],
                         "PARTIAL_TEXT_REVIEW_NO_LISTING_TERM_NOT_CLEARED")
        self.assertFalse(partial["sec_clearance"])

    def test_spoofed_sec_origin_is_rejected(self):
        for url in (
            "https://www.sec.gov.evil.example/Archives/edgar/data/123/x",
            "https://www.sec.gov@evil.example/Archives/edgar/data/123/x",
            "https://www.sec.gov/Archives/edgar/data/123/x?untrusted=1",
            "http://www.sec.gov/Archives/edgar/data/123/x",
        ):
            with self.subTest(url=url):
                item = review("REVERSE_SPLIT")
                item["source_url"] = url
                with self.assertRaisesRegex(ValueError, "official_sec_listing_source"):
                    build([item], 0, ASOF)

    def test_future_or_non_sec_evidence_is_rejected(self):
        future = review("LISTING_DEFICIENCY")
        future["accepted_at_utc"] = "2026-11-19T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "future_listing_evidence"):
            build([future], 0, ASOF)
        wrong = review("LISTING_DEFICIENCY")
        wrong["source_url"] = "https://example.com/filing.htm"
        with self.assertRaisesRegex(ValueError, "official_sec_listing_source"):
            build([wrong], 0, ASOF)


if __name__ == "__main__":
    unittest.main()
