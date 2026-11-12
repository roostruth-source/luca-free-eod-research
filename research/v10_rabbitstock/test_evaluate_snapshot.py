import unittest

from evaluate_snapshot import evaluate_snapshot


def base_payload():
    return {
        "ticker": "test",
        "snapshot_at": "2026-11-12T13:55:00+09:00",
        "data_asof": "2026-11-11T16:00:00-05:00",
        "source_type": "RABBITSTOCK_AUTHORIZED_SCREEN",
        "entry": 1.0,
        "engine_hits": {
            "preview": {"rank": 2, "target": 1.2},
            "signal": {"rank": 4, "target": 1.4},
            "best": {"rank": 6, "target": 1.3},
        },
        "warnings": {},
        "official_supply_checks": {
            "atm": "CLEAR",
            "eloc": "CLEAR",
            "toxic_financing": "CLEAR",
            "cb": "CLEAR",
            "warrant": "CLEAR",
            "lockup": "CLEAR",
            "reverse_split": "CLEAR",
            "shelf": "CLEAR",
        },
        "supply_evidence_asof": "2026-11-12T13:50:00+09:00",
        "split_basis_verified": True,
        "float_verified": True,
        "scope_partial": False,
    }


class SnapshotGateTests(unittest.TestCase):
    def test_three_engines_clean_is_watch_only_strong(self):
        result = evaluate_snapshot(base_payload())
        self.assertEqual(result["state"], "WATCH_ONLY_STRONG")
        self.assertEqual(result["target_median"], 1.3)
        self.assertTrue(result["WATCH_ONLY"])
        self.assertTrue(result["NO_ORDERS"])
        self.assertEqual(result["validation_status"], "NOT_VALIDATED")

    def test_partial_scope_blocks_strength_claim(self):
        payload = base_payload()
        payload["scope_partial"] = True
        self.assertEqual(evaluate_snapshot(payload)["state"], "WATCH_ONLY_BLOCKED")

    def test_split_basis_or_float_gap_blocks(self):
        payload = base_payload()
        payload["split_basis_verified"] = False
        self.assertEqual(evaluate_snapshot(payload)["state"], "WATCH_ONLY_BLOCKED")
        payload = base_payload()
        payload["float_verified"] = False
        self.assertEqual(evaluate_snapshot(payload)["state"], "WATCH_ONLY_BLOCKED")

    def test_dilution_warning_prevents_strong_label(self):
        payload = base_payload()
        payload["warnings"] = {"atm": True}
        result = evaluate_snapshot(payload)
        self.assertEqual(result["state"], "WATCH_ONLY_BLOCKED")
        self.assertEqual(result["screen_supply_unreconciled"], ["atm"])
        self.assertIn("SCREEN_SUPPLY_LABEL_UNRECONCILED", result["block_reasons"])

    def test_matched_screen_and_official_atm_is_watch_only(self):
        payload = base_payload()
        payload["warnings"] = {"atm": True}
        payload["official_supply_checks"]["atm"] = "PRESENT"
        result = evaluate_snapshot(payload)
        self.assertEqual(result["state"], "WATCH_ONLY")
        self.assertEqual(result["screen_supply_unreconciled"], [])

    def test_empty_screen_warning_does_not_replace_official_checks(self):
        payload = base_payload()
        payload["official_supply_checks"]["atm"] = "UNKNOWN"
        result = evaluate_snapshot(payload)
        self.assertEqual(result["state"], "WATCH_ONLY_BLOCKED")
        self.assertFalse(result["screen_dilution_warning"])
        self.assertIn("atm", result["unknown_supply_checks"])

    def test_official_warrant_or_shelf_prevents_strong_label(self):
        payload = base_payload()
        payload["official_supply_checks"]["warrant"] = "PRESENT"
        payload["official_supply_checks"]["shelf"] = "PRESENT"
        result = evaluate_snapshot(payload)
        self.assertEqual(result["state"], "WATCH_ONLY")
        self.assertTrue(result["official_dilution_warning"])
        self.assertEqual(result["present_supply_checks"], ["warrant", "shelf"])

    def test_future_supply_evidence_is_rejected(self):
        payload = base_payload()
        payload["supply_evidence_asof"] = "2026-11-12T14:00:00+09:00"
        with self.assertRaisesRegex(ValueError, "future_supply_evidence_not_allowed"):
            evaluate_snapshot(payload)

    def test_future_information_is_rejected(self):
        payload = base_payload()
        payload["data_asof"] = "2026-11-13T00:00:00+09:00"
        with self.assertRaisesRegex(ValueError, "future_data_not_allowed"):
            evaluate_snapshot(payload)

    def test_high_fully_diluted_multiple_blocks(self):
        payload = base_payload()
        payload["official_os_baseline"] = 1_046_390
        payload["official_fully_diluted_shares"] = 30_458_162
        result = evaluate_snapshot(payload)
        self.assertEqual(result["state"], "WATCH_ONLY_BLOCKED")
        self.assertAlmostEqual(result["fully_diluted_multiple"], 29.1079, places=3)
        self.assertIn("HIGH_FULLY_DILUTED_MULTIPLE", result["block_reasons"])

    def test_extreme_serial_reverse_split_blocks(self):
        payload = base_payload()
        payload["reverse_split_factors"] = [16, 200]
        result = evaluate_snapshot(payload)
        self.assertEqual(result["state"], "WATCH_ONLY_BLOCKED")
        self.assertEqual(result["cumulative_reverse_split_factor"], 3_200)
        self.assertIn("SERIAL_REVERSE_SPLIT_EXTREME", result["block_reasons"])

    def test_dilution_share_counts_must_be_paired(self):
        payload = base_payload()
        payload["official_os_baseline"] = 1_000_000
        with self.assertRaisesRegex(ValueError, "dilution_share_pair_required"):
            evaluate_snapshot(payload)

    def test_cross_engine_float_mismatch_blocks(self):
        payload = base_payload()
        payload["engine_hits"]["preview"]["float"] = 239_842
        payload["engine_hits"]["signal"]["float"] = 239_842
        payload["engine_hits"]["best"]["float"] = 39_973
        payload["reverse_split_factors"] = [6]
        result = evaluate_snapshot(payload)
        self.assertEqual(result["state"], "WATCH_ONLY_BLOCKED")
        self.assertTrue(result["cross_engine_float_mismatch"])
        self.assertAlmostEqual(result["float_ratio"], 6.0, places=3)
        self.assertTrue(result["float_mismatch_matches_split_factor"])
        self.assertIn("CROSS_ENGINE_FLOAT_MISMATCH", result["block_reasons"])

    def test_small_float_rounding_difference_is_allowed(self):
        payload = base_payload()
        payload["engine_hits"]["preview"]["float"] = 100_000
        payload["engine_hits"]["signal"]["float"] = 101_000
        payload["engine_hits"]["best"]["float"] = 100_500
        result = evaluate_snapshot(payload)
        self.assertEqual(result["state"], "WATCH_ONLY_STRONG")
        self.assertFalse(result["cross_engine_float_mismatch"])

    def test_prefunded_warrants_are_treated_as_share_equivalent(self):
        payload = base_payload()
        payload["official_supply_checks"]["warrant"] = "PRESENT"
        payload["official_os_baseline"] = 26_785_848
        payload["official_fully_diluted_shares"] = 27_493_749
        payload["prefunded_warrants_unexercised_estimate"] = 707_901
        result = evaluate_snapshot(payload)
        self.assertEqual(result["state"], "WATCH_ONLY_BLOCKED")
        self.assertTrue(result["prefunded_share_equivalent"])
        self.assertEqual(result["economic_share_count"], 27_493_749)
        self.assertAlmostEqual(result["economic_share_uplift_pct"], 2.643, places=3)
        self.assertIn(
            "PREFUNDED_WARRANT_SHARE_EQUIVALENT", result["block_reasons"]
        )

    def test_prefunded_warrant_estimate_requires_os_baseline(self):
        payload = base_payload()
        payload["prefunded_warrants_unexercised_estimate"] = 1
        with self.assertRaisesRegex(ValueError, "prefunded_warrant_os_baseline_required"):
            evaluate_snapshot(payload)

    def test_significant_potential_dilution_blocks_below_two_x(self):
        payload = base_payload()
        payload["official_os_baseline"] = 32_002_370
        payload["official_fully_diluted_shares"] = 59_630_326
        result = evaluate_snapshot(payload)
        self.assertEqual(result["state"], "WATCH_ONLY_BLOCKED")
        self.assertAlmostEqual(result["potential_dilution_pct"], 86.33, places=2)
        self.assertTrue(result["significant_potential_dilution"])
        self.assertFalse(result["high_dilution_multiple"])
        self.assertIn("SIGNIFICANT_POTENTIAL_DILUTION", result["block_reasons"])


if __name__ == "__main__":
    unittest.main()
