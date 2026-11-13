import copy
import unittest

from build_cb_reset_cohort import build_cb_reset_cohort


def contract(contract_id, ticker, effective, *, window=15, floor="NONE", events=None):
    return {
        "contract_id": contract_id,
        "ticker": ticker,
        "terms_effective_date": effective,
        "reset_after_trading_sessions": 16,
        "event_market_price_window_sessions": window,
        "lowest_vwap_count": 5,
        "reduction_only": True,
        "floor_constraint": floor,
        "evidence_available_at": "2026-09-18T16:00:00-04:00",
        "source_url": f"https://www.sec.gov/Archives/edgar/data/1/{contract_id}.htm",
        "share_combination_events": events or [],
    }


def official_event(date, elapsed):
    return {
        "event_date": date,
        "ratio": "1-for-10",
        "trading_sessions_elapsed_asof": elapsed,
        "verification_status": "OFFICIAL_VERIFIED",
        "evidence_available_at": "2026-10-10T16:00:00-04:00",
        "source_url": "https://www.sec.gov/Archives/edgar/data/1/split.htm",
    }


def payload():
    return {
        "evaluation_asof": "2026-11-13T08:00:00-05:00",
        "reference_contract_id": "zbao",
        "contracts": [
            contract("zbao", "ZBAO", "2026-09-17", events=[official_event("2026-10-09", 24)]),
            contract("husa", "HUSA", "2025-07-10", events=[official_event("2025-06-06", 300)]),
            contract("gctk", "GCTK", "2026-09-10", window=20, floor="PRESENT"),
        ],
    }


class BuildCbResetCohortTests(unittest.TestCase):
    def test_exact_contract_does_not_make_pre_contract_split_eligible(self):
        result = build_cb_reset_cohort(payload())
        husa = next(item for item in result["contracts"] if item["contract_id"] == "husa")
        self.assertTrue(husa["mechanics_match"])
        self.assertFalse(husa["outcome_cohort_eligible"])
        self.assertIn("EVENT_PRECEDES_TERMS_NOT_ELIGIBLE", husa["block_reasons"])
        self.assertEqual(result["independent_comparator_count"], 0)
        self.assertEqual(result["hypothesis_status"], "NO_INDEPENDENT_COMPARATOR_EVENT")

    def test_window_and_floor_mismatches_are_separate(self):
        result = build_cb_reset_cohort(payload())
        gctk = next(item for item in result["contracts"] if item["contract_id"] == "gctk")
        self.assertEqual(
            gctk["fingerprint_mismatches"],
            ["event_market_price_window_sessions", "floor_constraint"],
        )

    def test_post_contract_mature_exact_event_is_comparator(self):
        data = payload()
        data["contracts"][1]["share_combination_events"] = [official_event("2025-08-01", 16)]
        result = build_cb_reset_cohort(data)
        self.assertEqual(result["independent_comparator_count"], 1)
        self.assertEqual(result["hypothesis_status"], "COMPARATOR_OUTCOMES_AVAILABLE")

    def test_event_must_reach_contract_session_count(self):
        data = payload()
        data["contracts"][1]["share_combination_events"] = [official_event("2025-08-01", 15)]
        result = build_cb_reset_cohort(data)
        husa = next(item for item in result["contracts"] if item["contract_id"] == "husa")
        self.assertIn("RESET_DATE_NOT_REACHED", husa["block_reasons"])

    def test_future_contract_evidence_is_rejected(self):
        data = copy.deepcopy(payload())
        data["contracts"][0]["evidence_available_at"] = "2026-11-14T09:00:00-05:00"
        with self.assertRaisesRegex(ValueError, "future_contract_evidence_not_allowed"):
            build_cb_reset_cohort(data)


if __name__ == "__main__":
    unittest.main()
