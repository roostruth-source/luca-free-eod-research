import copy
from datetime import datetime, timedelta, timezone
import urllib.error
import unittest

from run_live_research import assemble, collect, render_html
from sec_document_review import fetch_filing, review_text
from sec_access import fetch_sec_json, validate_user_agent
from sec_official_bundle import canonical_sha256, validate_official_bundle

URL = "https://www.sec.gov/Archives/edgar/data/123/000000012326000001/filing.htm"
ASOF = datetime(2026, 11, 18, tzinfo=timezone.utc)


def official_bundle(*, collected_at=None):
    collected_at = collected_at or ASOF - timedelta(minutes=5)
    ticker_map = {"ABC": 123}
    payload = {
        "cik": 123,
        "filings": {"recent": {
            "form": ["8-K"],
            "accessionNumber": ["0000000123-26-000001"],
            "acceptanceDateTime": ["2026-11-17T12:00:00Z"],
            "filingDate": ["2026-11-17"],
            "primaryDocument": ["filing.htm"],
        }},
    }
    return {
        "schema_version": "LUCA_V10_SEC_OFFICIAL_BUNDLE_1",
        "source": "SEC_OFFICIAL",
        "collected_at_utc": collected_at.isoformat(),
        "ticker_map_source_url": "https://www.sec.gov/files/company_tickers.json",
        "ticker_map": ticker_map,
        "ticker_map_sha256": canonical_sha256(ticker_map),
        "submissions": {"ABC": {
            "source_url": "https://data.sec.gov/submissions/CIK0000000123.json",
            "retrieved_at_utc": (collected_at - timedelta(minutes=1)).isoformat(),
            "payload": payload,
            "sha256": canonical_sha256(payload),
        }},
    }


def bundle_enrichment():
    return {
        "schema": "LUCA_V03_IEX_CANDIDATE_ENRICHMENT_V1",
        "status": "COLLECTED_UNVERIFIED",
        "collected_at_utc": ASOF.isoformat(),
        "validation_status": "NOT_VALIDATED",
        "real_trades_allowed": False,
        "rows": [{
            "symbol": "ABC", "price_band_0_20_to_20": True,
            "iex_last_trade_price": 1.0,
            "screener_groups": {"active_volume": 3, "gainers": 2},
            "iex_quote_spread_pct": 1.5,
            "research_status": "WATCH_ONLY_FRESH_IEX",
            "buy_allowed": False,
        }],
    }


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
                 "iex_last_trade_price": 1.0,
                 "research_status": "PENDING_STALE_OR_MISSING"} for i in range(55)
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
        self.assertEqual(result["rows"][0]["iex_status"], "PENDING_STALE_OR_MISSING")
        self.assertTrue(all(row["state"] == "WATCH_ONLY_BLOCKED" for row in result["rows"]))

    def test_missing_declared_sec_contact_keeps_alpaca_candidates(self):
        enrichment = {"status": "COLLECTED_UNVERIFIED", "rows": [
            {"symbol": "ABC", "price_band_0_20_to_20": True,
             "iex_last_trade_price": 1.0, "research_status": "WATCH_ONLY_FRESH_IEX"}]}
        result = collect("key", "secret", now=ASOF,
                         enrichment_runner=lambda *a, **kw: enrichment, delay=0)
        self.assertEqual(result["source_status"], "SEC_CONTACT_NOT_CONFIGURED")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["rows"][0]["sec_status"], "SEC_NOT_CHECKED_CONTACT_REQUIRED")

    def test_declared_sec_user_agent_and_allowlist(self):
        self.assertEqual(validate_user_agent("LUCA-Research contact@example.com"),
                         "LUCA-Research contact@example.com")
        with self.assertRaisesRegex(ValueError, "sec_declared_contact_required"):
            validate_user_agent("LUCA-Research x@example.com\r\nSecret: leaked")
        with self.assertRaisesRegex(ValueError, "sec_json_url_not_allowed"):
            fetch_sec_json("https://example.com/x", "LUCA-Research contact@example.com")

    def test_official_bundle_is_used_only_after_live_sec_denial(self):
        def blocked(url):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        result = collect("key", "secret", now=ASOF,
                         enrichment_runner=lambda *a, **kw: bundle_enrichment(),
                         sec_json=blocked, fetcher=lambda url: "", delay=0,
                         sec_bundle=official_bundle())
        self.assertEqual(result["source_status"],
                         "SEC_OFFICIAL_BUNDLE_PARTIAL_NOT_CLEARED")
        self.assertEqual(result["sec_live_fetch_status"],
                         "SEC_TICKER_MAP_HTTP_403")
        self.assertEqual(result["rows"][0]["sec_status"],
                         "RECENT_FILINGS_REQUIRE_REVIEW")
        self.assertEqual(result["sec_bundle_provenance"]["source"],
                         "SEC_OFFICIAL")
        self.assertEqual(result["rows"][0]["screener_groups"],
                         {"active_volume": 3, "gainers": 2})
        self.assertEqual(result["rows"][0]["iex_quote_spread_pct"], 1.5)
        self.assertFalse(result["sec_bundle_provenance"]["independently_refetched_in_this_run"])
        self.assertFalse(result["sec_clearance"])
        self.assertTrue(result["NO_ORDERS"])

    def test_invalid_candidate_context_fails_closed(self):
        enrichment = bundle_enrichment()
        enrichment["rows"][0]["screener_groups"] = {"invented_source": 1}
        def blocked(url):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        with self.assertRaisesRegex(ValueError, "invalid_screener_context"):
            collect("key", "secret", now=ASOF,
                    enrichment_runner=lambda *a, **kw: enrichment,
                    sec_json=blocked, delay=0)

    def test_official_bundle_hash_tampering_fails_closed(self):
        bundle = official_bundle()
        bundle["ticker_map"]["ABC"] = 456
        def blocked(url):
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        result = collect("key", "secret", now=ASOF,
                         enrichment_runner=lambda *a, **kw: bundle_enrichment(),
                         sec_json=blocked, delay=0, sec_bundle=bundle)
        self.assertEqual(result["source_status"],
                         "SEC_TICKER_MAP_HTTP_403_BUNDLE_VALUEERROR")
        self.assertEqual(result["rows"][0]["sec_status"],
                         "SEC_NOT_CHECKED_SOURCE_UNAVAILABLE")
        self.assertFalse(result["sec_clearance"])

    def test_official_bundle_rejects_future_stale_and_non_sec_sources(self):
        future = official_bundle(collected_at=ASOF + timedelta(seconds=1))
        with self.assertRaisesRegex(ValueError, "future_collection"):
            validate_official_bundle(future, ASOF, ["ABC"])
        stale = official_bundle(collected_at=ASOF - timedelta(hours=73))
        with self.assertRaisesRegex(ValueError, "stale"):
            validate_official_bundle(stale, ASOF, ["ABC"])
        wrong_source = official_bundle()
        wrong_source["submissions"]["ABC"]["source_url"] = "https://example.com/x"
        with self.assertRaisesRegex(ValueError, "source_not_official"):
            validate_official_bundle(wrong_source, ASOF, ["ABC"])

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
