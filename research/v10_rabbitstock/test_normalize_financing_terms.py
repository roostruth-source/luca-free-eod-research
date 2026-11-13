import unittest

from normalize_financing_terms import normalize_financing_terms


def base_payload():
    return {
        "evaluation_asof": "2026-11-09T18:00:00-05:00",
        "reference_at": "2026-11-09T08:05:17-05:00",
        "reverse_splits": [
            {
                "action_id": "march_1_for_25",
                "effective_at": "2026-03-26T17:00:00-04:00",
                "evidence_available_at": "2026-03-25T08:15:25-04:00",
                "shares_before_per_after": 25,
                "source_url": "https://www.sec.gov/march",
            },
            {
                "action_id": "july_1_for_10",
                "effective_at": "2026-07-17T17:00:00-04:00",
                "evidence_available_at": "2026-07-16T08:05:43-04:00",
                "shares_before_per_after": 10,
                "source_url": "https://www.sec.gov/july",
            },
            {
                "action_id": "september_1_for_25",
                "effective_at": "2026-09-28T17:00:00-04:00",
                "evidence_available_at": "2026-09-25T08:15:15-04:00",
                "shares_before_per_after": 25,
                "source_url": "https://www.sec.gov/september",
            },
            {
                "action_id": "november_1_for_20",
                "effective_at": "2026-11-05T17:00:00-05:00",
                "evidence_available_at": "2026-11-04T23:59:59-05:00",
                "shares_before_per_after": 20,
                "source_url": "https://www.sec.gov/november",
            },
        ],
        "terms": [
            {
                "term_id": "cdt_eloc_floor",
                "instrument_type": "ELOC",
                "term_type": "PRICE_TERM",
                "observed_at": "2026-03-03T12:00:00-05:00",
                "value": 0.60,
                "split_adjustment_contract": "DOES_NOT_ADJUST",
                "source_url": "https://www.sec.gov/eloc",
                "evidence_available_at": "2026-03-09T16:05:49-04:00",
                "official_comparison_value": 0.60,
                "official_comparison_source_url": "https://www.sec.gov/later",
                "official_comparison_evidence_available_at": "2026-08-12T23:59:59-04:00",
            }
        ],
    }


class FinancingTermTests(unittest.TestCase):
    def test_non_adjusting_floor_does_not_multiply_by_125000(self):
        result = normalize_financing_terms(base_payload())
        term = result["normalized_terms"][0]
        self.assertEqual(term["cumulative_split_factor"], 125000)
        self.assertEqual(term["naive_mechanical_value"], 75000)
        self.assertEqual(term["normalized_value"], 0.60)
        self.assertEqual(term["block_reasons"], [])
        self.assertTrue(result["WATCH_ONLY"])
        self.assertTrue(result["NO_ORDERS"])

    def test_unknown_contract_is_blocked(self):
        payload = base_payload()
        payload["terms"][0]["split_adjustment_contract"] = "UNKNOWN"
        result = normalize_financing_terms(payload)
        term = result["normalized_terms"][0]
        self.assertIsNone(term["normalized_value"])
        self.assertIn("SPLIT_ADJUSTMENT_CONTRACT_UNKNOWN", term["block_reasons"])

    def test_conflicting_later_official_value_is_blocked(self):
        payload = base_payload()
        payload["terms"][0]["official_comparison_value"] = 15.0
        result = normalize_financing_terms(payload)
        term = result["normalized_terms"][0]
        self.assertIn("TERM_BASIS_CONFLICT", term["block_reasons"])

    def test_future_evidence_is_rejected(self):
        payload = base_payload()
        payload["terms"][0]["evidence_available_at"] = "2026-11-10T00:00:00-05:00"
        with self.assertRaisesRegex(ValueError, "future_term_evidence_not_allowed"):
            normalize_financing_terms(payload)


if __name__ == "__main__":
    unittest.main()
