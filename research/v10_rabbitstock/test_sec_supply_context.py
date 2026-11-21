from datetime import datetime, timezone
import unittest

from sec_supply_context import build


ASOF = datetime(2026, 11, 18, 15, tzinfo=timezone.utc)
URL = "https://www.sec.gov/Archives/edgar/data/123/000000012326000001/filing.htm"


def review(*terms):
    return {
        "source_url": URL, "accepted_at_utc": "2026-11-17T12:00:00Z",
        "form": "8-K", "matched_terms": [
            {"term": term, "context": term + " context"} for term in terms],
    }


class SecSupplyContextTests(unittest.TestCase):
    def test_supply_terms_create_hold_context_without_inventing_share_counts(self):
        result = build([review("ATM", "CB", "WARRANT")], 0, ASOF)
        self.assertTrue(result["dilution_risk_detected"])
        self.assertEqual({signal["code"] for signal in result["signals"]},
                         {"ATM", "CB", "WARRANT"})
        self.assertIsNone(result["shares_outstanding"])
        self.assertIsNone(result["float_shares"])
        self.assertFalse(result["os_verified"])
        self.assertFalse(result["float_verified"])
        self.assertFalse(result["registration_effectiveness_verified"])
        self.assertFalse(result["remaining_capacity_verified"])
        self.assertFalse(result["sec_clearance"])

    def test_partial_or_unavailable_text_never_becomes_clearance(self):
        missing = build([], 1, ASOF)
        self.assertEqual(missing["status"], "SEC_SUPPLY_TEXT_UNAVAILABLE")
        partial = build([review("LOCKUP")], 2, ASOF)
        self.assertEqual(partial["status"],
                         "PARTIAL_TEXT_REVIEW_NO_SUPPLY_TERM_NOT_CLEARED")
        self.assertFalse(partial["sec_clearance"])

    def test_future_and_spoofed_sources_are_rejected(self):
        future = review("ELOC")
        future["accepted_at_utc"] = "2026-11-19T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "future_supply_evidence"):
            build([future], 0, ASOF)
        spoofed = review("ELOC")
        spoofed["source_url"] = "https://www.sec.gov.evil.test/Archives/edgar/data/x"
        with self.assertRaisesRegex(ValueError, "official_sec_supply_source"):
            build([spoofed], 0, ASOF)

    def test_verified_companyfacts_os_is_carried_without_inventing_float(self):
        os_context = {
            "schema_version": "LUCA_V10_SEC_OS_CONTEXT_1",
            "status": "SEC_COMPANYFACTS_OS_VERIFIED_POINT_IN_TIME",
            "shares_outstanding": 1_250_000, "os_verified": True,
            "os_asof_date": "2026-11-15", "os_filed_date": "2026-11-17",
            "os_knowable_at_utc": "2026-11-18T00:00:00Z", "os_form": "8-K",
            "os_accession": "0000000123-26-000020",
            "os_source_url": (
                "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000123.json"),
            "os_retrieved_at_utc": "2026-11-18T14:00:00Z",
            "os_basis": "SEC_COMPANYFACTS_POINT_IN_TIME",
            "os_age_days": 3, "os_stale": False,
            "os_current_enough_for_ratio": True,
            "float_shares": None, "float_verified": False,
            "float_basis": "NOT_DERIVED_ENTITY_PUBLIC_FLOAT_IS_USD_VALUE",
            "NO_ORDERS": True,
        }
        result = build([], 0, ASOF, os_context)
        self.assertEqual(result["shares_outstanding"], 1_250_000)
        self.assertTrue(result["os_verified"])
        self.assertFalse(result["float_verified"])
        self.assertEqual(result["os_age_days"], 3)
        self.assertTrue(result["os_current_enough_for_ratio"])
        self.assertEqual(result["source"],
                         "SEC_FILING_TEXT_PLUS_COMPANYFACTS")


if __name__ == "__main__":
    unittest.main()
