import copy
import unittest

from run_research_build import build_report
from render_report import render_report


def snapshot(ticker="SAFE"):
    return {
        "ticker": ticker,
        "snapshot_at": "2026-11-13T00:08:00+09:00",
        "data_asof": "2026-11-11T16:00:00-05:00",
        "source_type": "RABBITSTOCK_AUTHORIZED_SCREEN",
        "entry": 1.0,
        "engine_hits": {"preview": {"rank": 2}, "signal": {"rank": 4}, "best": {"rank": 1}},
        "exchange_status": {
            "status": "TRADING",
            "effective_at": "2026-11-11T09:30:00-05:00",
            "evidence_available_at": "2026-11-11T09:30:00-05:00",
            "source_url": "https://www.nasdaqtrader.com/safe",
        },
        "official_supply_checks": {
            "atm": "CLEAR", "eloc": "CLEAR", "toxic_financing": "CLEAR",
            "cb": "CLEAR", "warrant": "CLEAR", "lockup": "CLEAR",
            "reverse_split": "CLEAR", "shelf": "CLEAR",
        },
        "supply_evidence_asof": "2026-11-11T16:00:00-05:00",
        "split_basis_verified": True,
        "float_verified": True,
    }


def volume_event(ticker="SAFE"):
    def bar(day, volume, prior_return=0.0, close=1.0):
        return {
            "date": day, "close": close, "return_pct": prior_return,
            "session_complete": True, "available_at": "2026-11-12T12:00:00-05:00",
            "volume_observations": [
                {"provider_id": "a", "source_url": "https://a.example/history", "volume": volume},
                {"provider_id": "b", "source_url": "https://b.example/history", "volume": volume},
            ],
        }
    days = ["2026-10-28", "2026-10-29", "2026-10-30", "2026-11-02",
            "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06",
            "2026-11-09", "2026-11-10"]
    return {
        "ticker": ticker, "evaluation_asof": "2026-11-12T13:00:00-05:00",
        "price_volume_basis": "SPLIT_ADJUSTED_TO_EVENT",
        "float_verified": True, "float_shares": 1000,
        "prior_bars": [bar(day, 100, 25 if i == 9 else 0, 1.25 if i == 9 else 1.0)
                       for i, day in enumerate(days)],
        "current_bar": bar("2026-11-11", 10000),
    }


class ResearchBuildTests(unittest.TestCase):
    def test_consensus_sorting_is_deterministic(self):
        three = snapshot("THREE")
        two = snapshot("TWO")
        del two["engine_hits"]["best"]
        result = build_report([two, three], "2026-11-14T00:30:00+09:00")
        self.assertEqual([x["ticker"] for x in result["candidates"]], ["THREE", "TWO"])
        self.assertEqual(result["ranking_rule"], "engine_count_desc_then_best_rank_asc_not_probability")

    def test_china_profile_requires_sec_evidence(self):
        item = snapshot("CN")
        item.update({"detector_profile": "CHINA_1_0", "issuer_region": "PRC_OPERATIONS"})
        result = build_report([item], "2026-11-14T00:30:00+09:00")
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["errors"][0]["error"], "china_profile_evidence_timestamp_required")

    def test_verified_china_profile_routes_separately(self):
        item = snapshot("CN")
        item.update({
            "detector_profile": "CHINA_1_0",
            "issuer_region": "PRC_OPERATIONS",
            "issuer_region_evidence_at": "2026-05-01T16:00:00-04:00",
            "issuer_region_source_url": "https://www.sec.gov/Archives/cn.htm",
        })
        result = build_report([item], "2026-11-14T00:30:00+09:00")
        self.assertEqual(result["profile_counts"]["CHINA_1_0"], 1)
        self.assertIn("SEC_VERIFIED_PRC_OPERATIONS", result["candidates"][0]["profile_reasons"])

    def test_future_china_evidence_is_rejected(self):
        item = snapshot("CN")
        item.update({
            "detector_profile": "CHINA_1_0",
            "issuer_region": "PRC_OPERATIONS",
            "issuer_region_evidence_at": "2026-11-14T00:00:00+09:00",
            "issuer_region_source_url": "https://www.sec.gov/Archives/cn.htm",
        })
        result = build_report([item], "2026-11-14T00:30:00+09:00")
        self.assertEqual(result["errors"][0]["error"], "future_china_profile_evidence_not_allowed")

    def test_no_orders_are_always_forced(self):
        result = build_report([snapshot()], "2026-11-14T00:30:00+09:00")
        self.assertTrue(result["WATCH_ONLY"])
        self.assertTrue(result["NO_ORDERS"])
        self.assertEqual(result["validation_status"], "NOT_VALIDATED")
        self.assertTrue(result["candidates"][0]["NO_ORDERS"])

    def test_future_snapshot_is_rejected(self):
        item = copy.deepcopy(snapshot())
        item["snapshot_at"] = "2026-11-14T00:31:00+09:00"
        result = build_report([item], "2026-11-14T00:30:00+09:00")
        self.assertEqual(result["errors"][0]["error"], "future_snapshot_not_allowed")

    def test_volume_events_are_integrated(self):
        volume = {
            "event_type": "VOLUME_ANOMALY", "ticker": "VOL",
            "evaluation_asof": "2026-11-11T23:00:00-05:00",
            "price_volume_basis": "SPLIT_ADJUSTED_TO_EVENT", "float_verified": False,
            "prior_bars": [], "current_bar": {},
        }
        result = build_report([snapshot()], "2026-11-14T00:30:00+09:00", [volume])
        self.assertEqual(result["errors"][0]["error"], "exactly_ten_prior_sessions_required")

    def test_late_surge_blocks_matching_snapshot(self):
        item = snapshot()
        item["snapshot_at"] = "2026-11-13T04:08:00+09:00"
        result = build_report([item], "2026-11-14T00:30:00+09:00", [volume_event()])
        candidate = result["candidates"][0]
        self.assertEqual(result["error_count"], 0)
        self.assertEqual(candidate["state"], "WATCH_ONLY_BLOCKED")
        self.assertIn("ALREADY_SURGED_PREVIOUS_SESSION", candidate["block_reasons"])
        self.assertEqual(candidate["volume_evidence"]["volume_vs_average_multiple"], 100)

    def test_later_volume_cannot_backfill_snapshot(self):
        item = snapshot()
        result = build_report([item], "2026-11-14T00:30:00+09:00", [volume_event()])
        self.assertEqual(result["candidates"][0]["state"], "WATCH_ONLY_STRONG")
        self.assertIsNone(result["candidates"][0]["volume_evidence"])

    def test_future_volume_evaluation_is_rejected_at_build_cutoff(self):
        item = volume_event()
        item["evaluation_asof"] = "2026-11-14T00:31:00+09:00"
        result = build_report([], "2026-11-14T00:30:00+09:00", [item])
        self.assertEqual(result["errors"][0]["error"], "future_volume_evaluation_not_allowed")

    def test_mobile_report_escapes_untrusted_ticker(self):
        result = build_report([snapshot("<img src=x onerror=alert(1)>")],
                              "2026-11-14T00:30:00+09:00")
        rendered = render_report(result)
        self.assertNotIn("<img", rendered)
        self.assertIn("&lt;IMG", rendered)
        self.assertIn("주문 없음", rendered)


if __name__ == "__main__":
    unittest.main()
