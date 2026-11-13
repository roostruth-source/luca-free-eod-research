import unittest

from reconcile_os_timeline import reconcile_os_timeline


def cdt_payload():
    return {
        "evaluation_asof": "2026-10-27T17:00:00-04:00",
        "reference_at": "2026-10-27T16:58:52-04:00",
        "ticker": "CDT",
        "rapid_expansion_threshold_pct": 25.0,
        "reverse_splits": [
            {
                "action_id": "cdt_2026_09_1_for_25",
                "effective_at": "2026-09-28T17:00:00-04:00",
                "evidence_available_at": "2026-09-25T16:05:00-04:00",
                "shares_before_per_after": 25,
                "source_url": "https://www.sec.gov/september-split",
            }
        ],
        "checkpoints": [
            {
                "checkpoint_id": "aug12",
                "observation_date": "2026-08-12",
                "evidence_available_at": "2026-08-12T17:29:38-04:00",
                "shares_outstanding": 786670,
                "source_url": "https://www.sec.gov/aug12",
            },
            {
                "checkpoint_id": "aug31",
                "observation_date": "2026-08-31",
                "evidence_available_at": "2026-09-01T16:15:24-04:00",
                "shares_outstanding": 13693866,
                "source_url": "https://www.sec.gov/aug31",
            },
            {
                "checkpoint_id": "sep30",
                "observation_date": "2026-09-30",
                "evidence_available_at": "2026-10-07T16:05:14-04:00",
                "shares_outstanding": 1477789,
                "source_url": "https://www.sec.gov/sep30",
            },
            {
                "checkpoint_id": "oct23",
                "observation_date": "2026-10-23",
                "evidence_available_at": "2026-10-27T16:58:52-04:00",
                "shares_outstanding": 9322805,
                "source_url": "https://www.sec.gov/oct23",
            },
        ],
    }


class OutstandingTimelineTests(unittest.TestCase):
    def test_cdt_os_growth_is_split_normalized(self):
        result = reconcile_os_timeline(cdt_payload())
        first, second, third = result["intervals"]
        self.assertAlmostEqual(first["net_os_change_pct"], 1640.73830196)
        self.assertEqual(second["cumulative_split_factor"], 25)
        self.assertAlmostEqual(second["from_shares_on_to_basis"], 547754.64)
        self.assertAlmostEqual(second["net_os_change_pct"], 169.79032072)
        self.assertAlmostEqual(third["net_os_change_pct"], 530.86171301)
        self.assertTrue(all(i["not_gross_issuance"] for i in result["intervals"]))
        self.assertIn("RAPID_OS_EXPANSION", result["block_reasons"])
        self.assertIn("OS_MORE_THAN_DOUBLED", result["block_reasons"])

    def test_future_checkpoint_evidence_is_rejected(self):
        payload = cdt_payload()
        payload["checkpoints"][-1]["evidence_available_at"] = (
            "2026-10-28T09:00:00-04:00"
        )
        with self.assertRaisesRegex(ValueError, "future_checkpoint_evidence_not_allowed"):
            reconcile_os_timeline(payload)

    def test_non_sec_checkpoint_source_is_rejected(self):
        payload = cdt_payload()
        payload["checkpoints"][0]["source_url"] = "https://example.com/value"
        with self.assertRaisesRegex(
            ValueError, "official_sec_checkpoint_source_required"
        ):
            reconcile_os_timeline(payload)

    def test_evidence_cannot_precede_observation(self):
        payload = cdt_payload()
        payload["checkpoints"][1]["evidence_available_at"] = (
            "2026-08-30T16:00:00-04:00"
        )
        with self.assertRaisesRegex(ValueError, "evidence_precedes_observation"):
            reconcile_os_timeline(payload)

    def test_quiet_timeline_has_no_expansion_block(self):
        payload = cdt_payload()
        payload["reverse_splits"] = []
        payload["checkpoints"] = payload["checkpoints"][:2]
        payload["checkpoints"][0]["shares_outstanding"] = 1000
        payload["checkpoints"][1]["shares_outstanding"] = 1100
        result = reconcile_os_timeline(payload)
        self.assertEqual(result["block_reasons"], [])


if __name__ == "__main__":
    unittest.main()
