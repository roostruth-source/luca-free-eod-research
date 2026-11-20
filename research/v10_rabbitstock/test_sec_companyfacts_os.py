from datetime import datetime, timezone
import copy
import unittest

from sec_companyfacts_os import extract


ASOF = datetime(2026, 11, 18, 15, tzinfo=timezone.utc)
URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000000123.json"


def payload():
    return {
        "cik": 123,
        "facts": {"dei": {"EntityCommonStockSharesOutstanding": {
            "units": {"shares": [
                {"val": 1_000_000, "end": "2026-08-01",
                 "filed": "2026-08-02", "form": "10-Q",
                 "accn": "0000000123-26-000010"},
                {"val": 1_250_000, "end": "2026-11-15",
                 "filed": "2026-11-17", "form": "8-K",
                 "accn": "0000000123-26-000020"},
            ]}
        }}},
    }


class SecCompanyFactsOsTests(unittest.TestCase):
    def test_latest_knowable_point_in_time_os_is_selected(self):
        result = extract(payload(), URL, "2026-11-18T14:00:00Z", ASOF)
        self.assertTrue(result["os_verified"])
        self.assertEqual(result["shares_outstanding"], 1_250_000)
        self.assertEqual(result["os_asof_date"], "2026-11-15")
        self.assertEqual(result["os_knowable_at_utc"],
                         "2026-11-18T00:00:00+00:00")
        self.assertFalse(result["float_verified"])
        self.assertIsNone(result["float_shares"])

    def test_same_day_filing_is_not_used_before_next_utc_day(self):
        result = extract(payload(), URL, "2026-11-17T14:00:00Z",
                         datetime(2026, 11, 17, 15, tzinfo=timezone.utc))
        self.assertEqual(result["shares_outstanding"], 1_000_000)

    def test_missing_concept_stays_explicitly_unverified(self):
        result = extract({"cik": 123, "facts": {}}, URL,
                         "2026-11-18T14:00:00Z", ASOF)
        self.assertFalse(result["os_verified"])
        self.assertEqual(result["status"],
                         "SEC_COMPANYFACTS_OS_CONCEPT_UNAVAILABLE")

    def test_conflicting_duplicate_and_spoofed_source_fail_closed(self):
        conflict = payload()
        duplicate = copy.deepcopy(conflict["facts"]["dei"][
            "EntityCommonStockSharesOutstanding"]["units"]["shares"][-1])
        duplicate["val"] = 9_999_999
        conflict["facts"]["dei"]["EntityCommonStockSharesOutstanding"][
            "units"]["shares"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "conflicting_duplicate"):
            extract(conflict, URL, "2026-11-18T14:00:00Z", ASOF)
        with self.assertRaisesRegex(ValueError, "source_not_official"):
            extract(payload(), "https://data.sec.gov.evil.test/x",
                    "2026-11-18T14:00:00Z", ASOF)

    def test_future_retrieval_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "future_companyfacts_retrieval"):
            extract(payload(), URL, "2026-11-19T14:00:00Z", ASOF)

    def test_fact_period_cannot_end_after_its_filing_date(self):
        future_end = payload()
        future_end["facts"]["dei"]["EntityCommonStockSharesOutstanding"][
            "units"]["shares"][-1]["end"] = "2026-11-18"
        with self.assertRaisesRegex(ValueError, "end_after_filing"):
            extract(future_end, URL, "2026-11-18T14:00:00Z", ASOF)


if __name__ == "__main__":
    unittest.main()
