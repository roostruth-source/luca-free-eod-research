import copy
from datetime import datetime, timezone
import urllib.error
import unittest

from run_live_research import assemble, collect, render_html
from sec_document_review import fetch_filing, review_text

URL = "https://www.sec.gov/Archives/edgar/data/123/000000012326000001/filing.htm"
ASOF = datetime(2026, 11, 18, tzinfo=timezone.utc)


def triage():
    return {"status": "COLLECTED_PARTIAL_NOT_CLEARED", "rows": [{
        "symbol": "ABC", "iex_price": 1.0, "sec_status": "RECENT_FILINGS_REQUIRE_REVIEW",
        "review_filings": [{"url": URL, "form": "8-K",
                            "accepted_at_utc": "2026-11-17T12:00:00+00:00"}],
    }]}


class LiveResearchTests(unittest.TestCase):
    def test_sec_text_is_tentative_and_has_provenance(self):
        result = assemble(triage(), ASOF,
                          fetcher=lambda url: "<p>Convertible note and warrants</p>", delay=0)
        review = result["rows"][0]["review_filings"][0]
        self.assertEqual({x["term"] for x in review["matched_terms"]}, {"CB", "WARRANT"})
        self.assertEqual(review["source_url"], URL)
        self.assertFalse(review["supply_clearance"])
        self.assertEqual(result["rows"][0]["state"], "WATCH_ONLY_BLOCKED")

    def test_future_sec_filing_is_not_backfilled(self):
        item = triage()
        item["rows"][0]["review_filings"][0]["accepted_at_utc"] = "2026-11-19T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "future_or_naive_sec_acceptance_not_allowed"):
            assemble(item, ASOF, fetcher=lambda url: "", delay=0)

    def test_sec_403_remains_blocked(self):
        def blocked(url):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        result = assemble(triage(), ASOF, fetcher=blocked, delay=0)
        self.assertEqual(result["rows"][0]["review_filings"][0]["status"], "HTTP_403_NOT_CLEARED")
        self.assertFalse(result["sec_clearance"])

    def test_missing_credentials_still_creates_honest_report(self):
        result = collect("", "", now=ASOF, delay=0)
        self.assertEqual(result["source_status"], "NO_ALPACA_KEYS")
        self.assertEqual(result["candidate_count"], 0)

    def test_more_than_fifty_watch_candidates_are_preserved_and_capped(self):
        enrichment = {
            "status": "COLLECTED_UNVERIFIED", "rows": [
                {"symbol": f"T{i:02d}", "price_band_0_20_to_20": True,
                 "iex_last_trade_price": 1.0} for i in range(55)
            ],
        }
        def forbidden(url):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        result = collect("key", "secret", now=ASOF,
                         enrichment_runner=lambda *a, **kw: enrichment,
                         sec_json=forbidden, delay=0)
        self.assertEqual(result["candidate_count"], 50)
        self.assertEqual(result["truncated_candidates"], 5)
        self.assertEqual(result["source_status"], "SEC_TICKER_MAP_HTTP_403")
        self.assertEqual(result["rows"][0]["ticker"], "T00")
        self.assertEqual(result["rows"][-1]["ticker"], "T49")
        self.assertTrue(all(row["state"] == "WATCH_ONLY_BLOCKED" for row in result["rows"]))

    def test_html_escapes_ticker(self):
        item = triage()
        item["rows"][0]["symbol"] = "<script>"
        result = assemble(item, ASOF, fetcher=lambda url: "", delay=0)
        rendered = render_html(result)
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_only_sec_archive_documents_are_fetched(self):
        with self.assertRaisesRegex(ValueError, "sec_archive_url_not_allowed"):
            fetch_filing("https://example.com/secrets")
        with self.assertRaisesRegex(ValueError, "sec_archive_url_not_allowed"):
            review_text("", "https://www.sec.gov.evil.test/Archives/x")


if __name__ == "__main__":
    unittest.main()
