import unittest

from reconcile_supply_bundles import reconcile_supply_bundles


def cdt_payload():
    return {
        "evaluation_asof": "2026-08-12T18:00:00-04:00",
        "reference_at": "2026-08-12T17:29:38-04:00",
        "tolerance_pct": 0.01,
        "reverse_splits": [
            {
                "action_id": "cdt_july_1_for_10",
                "effective_at": "2026-07-17T17:00:00-04:00",
                "evidence_available_at": "2026-07-16T08:05:43-04:00",
                "shares_before_per_after": 10,
                "source_url": "https://www.sec.gov/july",
            }
        ],
        "before_snapshot": {
            "bundle_id": "cdt_q2_financing_activity",
            "split_basis_effective_through": "2026-03-26T17:00:00-04:00",
            "evidence_available_at": "2026-07-15T16:46:03-04:00",
            "source_url": "https://www.sec.gov/q1",
            "components": [
                {"component_id": "ELOC", "share_count": 39907, "coverage_start": "2026-04-01", "coverage_end": "2026-04-30", "scope_label": "MONTH_ACTIVITY"},
                {"component_id": "ATM", "share_count": 275121, "coverage_start": "2026-05-01", "coverage_end": "2026-05-31", "scope_label": "MONTH_ACTIVITY"},
            ],
        },
        "after_snapshot": {
            "bundle_id": "cdt_q2_financing_activity",
            "split_basis_effective_through": "2026-07-17T17:00:00-04:00",
            "evidence_available_at": "2026-08-12T17:29:38-04:00",
            "source_url": "https://www.sec.gov/q2",
            "components": [
                {"component_id": "ELOC", "share_count": 3000, "coverage_start": "2026-04-01", "coverage_end": "2026-04-30", "scope_label": "MONTH_ACTIVITY"},
                {"component_id": "ATM", "share_count": 28501, "coverage_start": "2026-01-01", "coverage_end": "2026-06-30", "scope_label": "YTD_ACTIVITY"},
            ],
        },
    }


class SupplyBundleTests(unittest.TestCase):
    def test_cdt_components_shift_while_aggregate_nearly_matches(self):
        result = reconcile_supply_bundles(cdt_payload())
        self.assertEqual(result["cumulative_split_factor"], 10)
        self.assertAlmostEqual(
            result["aggregate_diagnostic"]["mechanical_adjusted_before_total"],
            31502.8,
        )
        self.assertEqual(result["aggregate_diagnostic"]["after_total"], 31501)
        self.assertAlmostEqual(result["aggregate_diagnostic"]["difference"], -1.8)
        self.assertTrue(result["aggregate_diagnostic"]["within_tolerance"])
        self.assertIn("BUNDLE_SCOPE_NOT_COMPARABLE", result["block_reasons"])
        self.assertIn("COMPONENT_BASIS_CONFLICT", result["block_reasons"])
        self.assertIn("COMPONENT_CLASSIFICATION_SHIFT_POSSIBLE", result["block_reasons"])

    def test_exact_scope_and_basis_match_passes(self):
        payload = cdt_payload()
        payload["before_snapshot"]["components"] = [
            {"component_id": "ATM", "share_count": 1000, "coverage_start": "2026-05-01", "coverage_end": "2026-05-31", "scope_label": "MONTH_ACTIVITY"}
        ]
        payload["after_snapshot"]["components"] = [
            {"component_id": "ATM", "share_count": 100, "coverage_start": "2026-05-01", "coverage_end": "2026-05-31", "scope_label": "MONTH_ACTIVITY"}
        ]
        result = reconcile_supply_bundles(payload)
        self.assertEqual(result["block_reasons"], [])

    def test_different_bundle_ids_are_rejected(self):
        payload = cdt_payload()
        payload["after_snapshot"]["bundle_id"] = "different"
        with self.assertRaisesRegex(ValueError, "bundle_id_mismatch"):
            reconcile_supply_bundles(payload)

    def test_future_evidence_is_rejected(self):
        payload = cdt_payload()
        payload["before_snapshot"]["evidence_available_at"] = "2026-08-13T00:00:00-04:00"
        with self.assertRaisesRegex(ValueError, "future_snapshot_evidence_not_allowed"):
            reconcile_supply_bundles(payload)


if __name__ == "__main__":
    unittest.main()
