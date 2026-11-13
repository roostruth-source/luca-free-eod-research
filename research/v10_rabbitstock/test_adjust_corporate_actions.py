import unittest

from adjust_corporate_actions import adjust_corporate_actions


def payload():
    return {
        "evaluation_asof": "2026-11-13T12:45:00+09:00",
        "reference_at": "2026-11-12T13:55:00+09:00",
        "reference_ticker": "YFOR",
        "actions": [
            {
                "action_id": "YFOR_RS_20260323_1_50",
                "action_type": "REVERSE_SPLIT",
                "effective_at": "2026-03-23T09:30:00-04:00",
                "evidence_available_at": "2026-03-19T23:59:59-04:00",
                "ticker": "YYGH",
                "shares_before_per_after": 50,
                "source_url": "https://www.sec.gov/example-1",
            },
            {
                "action_id": "YFOR_RS_20260623_1_30",
                "action_type": "REVERSE_SPLIT",
                "effective_at": "2026-06-23T09:30:00-04:00",
                "evidence_available_at": "2026-06-18T23:59:59-04:00",
                "ticker": "YYGH",
                "shares_before_per_after": 30,
                "source_url": "https://www.sec.gov/example-2",
            },
            {
                "action_id": "YFOR_TICKER_20260902",
                "action_type": "TICKER_CHANGE",
                "effective_at": "2026-09-02T09:30:00-04:00",
                "evidence_available_at": "2026-09-08T16:10:11-04:00",
                "from_ticker": "YYGH",
                "to_ticker": "YFOR",
                "same_security": True,
                "source_url": "https://www.sec.gov/example-3",
            },
        ],
        "observations": [
            {
                "observation_id": "price_probe",
                "metric_type": "PRICE",
                "ticker": "YYGH",
                "observed_at": "2026-03-20T16:00:00-04:00",
                "value": 1.0,
            },
            {
                "observation_id": "shares_probe",
                "metric_type": "SHARE_COUNT",
                "ticker": "YYGH",
                "observed_at": "2026-03-20T16:00:00-04:00",
                "value": 1500000,
            },
        ],
    }


class CorporateActionAdjustmentTests(unittest.TestCase):
    def test_yfor_cumulative_split_and_ticker_lineage(self):
        result = adjust_corporate_actions(payload())
        price, shares = result["adjusted_observations"]
        self.assertEqual(price["cumulative_split_factor"], 1500)
        self.assertEqual(price["adjusted_value"], 1500)
        self.assertEqual(shares["adjusted_value"], 1000)
        self.assertEqual(price["reference_ticker"], "YFOR")
        self.assertTrue(result["WATCH_ONLY"])
        self.assertTrue(result["NO_ORDERS"])

    def test_post_reference_evidence_is_rejected(self):
        item = payload()
        item["actions"][0]["evidence_available_at"] = "2026-11-12T14:00:00+09:00"
        with self.assertRaisesRegex(ValueError, "post_reference_action_evidence_not_allowed"):
            adjust_corporate_actions(item)

    def test_unlinked_ticker_is_rejected(self):
        item = payload()
        item["actions"] = item["actions"][:2]
        with self.assertRaisesRegex(ValueError, "ticker_lineage_not_resolved"):
            adjust_corporate_actions(item)

    def test_ticker_change_must_be_same_security(self):
        item = payload()
        item["actions"][2]["same_security"] = False
        with self.assertRaisesRegex(ValueError, "ticker_change_same_security_required"):
            adjust_corporate_actions(item)


if __name__ == "__main__":
    unittest.main()
