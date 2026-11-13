import copy
import unittest

from evaluate_cb_reset_event import evaluate_cb_reset_event


def bar(date, open_, high, low, close, volume):
    return {
        "date": date,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "session_complete": True,
        "available_at": f"{date}T20:30:00-05:00",
        "verification_status": "TWO_PROVIDER_RECONCILED",
        "provider_ids": ["chartexchange", "ft_markit"],
        "source_urls": ["https://chartexchange.com/zbao", "https://ft.com/zbao"],
        "max_field_disagreement_pct": 0.01,
    }


def zbao_payload():
    return {
        "evaluation_asof": "2026-11-09T21:00:00-05:00",
        "reference_at": "2026-11-09T21:00:00-05:00",
        "ticker": "ZBAO",
        "contract": {
            "share_combination_event_date": "2026-10-09",
            "reset_after_trading_sessions": 16,
            "event_market_price_window_sessions": 15,
            "lowest_vwap_count": 5,
            "reduction_only": True,
            "evidence_available_at": "2026-09-18T16:00:00-04:00",
            "source_url": "https://www.sec.gov/zbao-note",
        },
        "trading_sessions_after_event": [
            "2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15",
            "2026-10-16", "2026-10-19", "2026-10-20", "2026-10-21",
            "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27",
            "2026-10-28", "2026-10-29", "2026-10-30", "2026-11-02",
        ],
        "pre_reset_vwap_values": [],
        "horizons": [1, 3, 5, 10],
        "bars": [
            bar("2026-11-02", 0.2562, 0.2636, 0.2500, 0.2600, 115360),
            bar("2026-11-03", 0.2605, 0.4520, 0.2201, 0.2600, 26394349),
            bar("2026-11-04", 0.2467, 0.2763, 0.2350, 0.2400, 717224),
            bar("2026-11-05", 0.2421, 0.2480, 0.2200, 0.2270, 449007),
            bar("2026-11-06", 0.2304, 0.2675, 0.2270, 0.2300, 707643),
            bar("2026-11-09", 0.2299, 0.2378, 0.2232, 0.2298, 283047),
        ],
    }


class ConvertibleResetEventTests(unittest.TestCase):
    def test_zbao_reset_date_and_descriptive_followups(self):
        result = evaluate_cb_reset_event(zbao_payload())
        self.assertEqual(result["derived_reset_date"], "2026-11-02")
        self.assertEqual(result["reset_price_status"], "UNVERIFIED")
        self.assertAlmostEqual(result["first_post_session_volume_multiple"], 228.7998353)
        self.assertEqual(result["horizons"]["1"]["close_return_pct"], 0.0)
        self.assertAlmostEqual(result["horizons"]["1"]["MFE_pct"], 73.84615385)
        self.assertAlmostEqual(result["horizons"]["3"]["close_return_pct"], -12.69230769)
        self.assertAlmostEqual(result["horizons"]["5"]["close_return_pct"], -11.61538462)
        self.assertEqual(result["horizons"]["10"]["status"], "NOT_MATURE")
        self.assertEqual(result["causality_status"], "NOT_ESTABLISHED_SINGLE_EVENT")

    def test_vwap_derived_reset_price_requires_full_window(self):
        payload = zbao_payload()
        payload["pre_reset_vwap_values"] = [1.0] * 14
        result = evaluate_cb_reset_event(payload)
        self.assertEqual(result["reset_price_status"], "UNVERIFIED")
        payload["pre_reset_vwap_values"] = [1.0] * 10 + [0.5] * 5
        result = evaluate_cb_reset_event(payload)
        self.assertEqual(result["reset_price_status"], "VERIFIED")
        self.assertEqual(result["reset_price"], 0.5)

    def test_future_contract_evidence_is_rejected(self):
        payload = zbao_payload()
        payload["contract"]["evidence_available_at"] = "2026-11-10T09:00:00-05:00"
        with self.assertRaisesRegex(ValueError, "future_contract_evidence_not_allowed"):
            evaluate_cb_reset_event(payload)

    def test_single_provider_bar_is_rejected(self):
        payload = copy.deepcopy(zbao_payload())
        payload["bars"][0]["provider_ids"] = ["chartexchange"]
        with self.assertRaisesRegex(ValueError, "two_independent_providers_required"):
            evaluate_cb_reset_event(payload)

    def test_ten_day_horizon_becomes_mature_only_with_ten_bars(self):
        payload = zbao_payload()
        for offset, date in enumerate(["2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13", "2026-11-16"]):
            payload["bars"].append(bar(date, 0.23, 0.24, 0.20, 0.22, 300000 + offset))
        payload["evaluation_asof"] = "2026-11-16T21:00:00-05:00"
        payload["reference_at"] = "2026-11-16T21:00:00-05:00"
        result = evaluate_cb_reset_event(payload)
        self.assertEqual(result["horizons"]["10"]["status"], "MATURE")


if __name__ == "__main__":
    unittest.main()
