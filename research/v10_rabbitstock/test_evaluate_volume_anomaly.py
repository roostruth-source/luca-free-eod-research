import copy
import unittest

from evaluate_volume_anomaly import evaluate_volume_anomaly


def bar(day, close, ret, volume):
    return {
        "date": day,
        "close": close,
        "return_pct": ret,
        "session_complete": True,
        "available_at": f"{day}T21:00:00-05:00",
        "volume_observations": [
            {"provider_id": "a", "source_url": "https://a.example/x", "volume": volume},
            {"provider_id": "b", "source_url": "https://b.example/x", "volume": volume + 1},
        ],
    }


def payload():
    days = ["2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-11-02",
            "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09"]
    return {
        "event_type": "VOLUME_ANOMALY",
        "ticker": "TEST",
        "evaluation_asof": "2026-11-11T23:00:00-05:00",
        "price_volume_basis": "SPLIT_ADJUSTED_TO_EVENT",
        "float_verified": True,
        "float_shares": 1_000_000,
        "prior_bars": [bar(day, 1.0, 0.0, 100_000) for day in days],
        "current_bar": bar("2026-11-10", 1.0, 0.0, 1_000_000),
    }


class VolumeAnomalyTests(unittest.TestCase):
    def test_confirmed_volume_first_candidate(self):
        result = evaluate_volume_anomaly(payload())
        self.assertTrue(result["volume_anomaly_confirmed"])
        self.assertTrue(result["early_volume_candidate"])
        self.assertAlmostEqual(result["volume_vs_average_multiple"], 9.999955)

    def test_prior_surge_blocks_early_label(self):
        data = payload()
        data["prior_bars"][-1]["return_pct"] = 24.2
        result = evaluate_volume_anomaly(data)
        self.assertFalse(result["early_volume_candidate"])
        self.assertIn("ALREADY_SURGED_PREVIOUS_SESSION", result["block_reasons"])

    def test_unverified_float_blocks_early_label(self):
        data = payload()
        data["float_verified"] = False
        del data["float_shares"]
        result = evaluate_volume_anomaly(data)
        self.assertIn("FLOAT_TURNOVER_UNVERIFIED", result["block_reasons"])

    def test_single_provider_is_rejected(self):
        data = copy.deepcopy(payload())
        data["current_bar"]["volume_observations"] = data["current_bar"]["volume_observations"][:1]
        with self.assertRaisesRegex(ValueError, "two_independent_volume_providers_required"):
            evaluate_volume_anomaly(data)

    def test_future_bar_is_rejected(self):
        data = payload()
        data["current_bar"]["available_at"] = "2026-11-12T00:00:00-05:00"
        with self.assertRaisesRegex(ValueError, "future_bar_not_allowed"):
            evaluate_volume_anomaly(data)

    def test_source_conflict_is_rejected(self):
        data = payload()
        data["current_bar"]["volume_observations"][1]["volume"] = 500_000
        with self.assertRaisesRegex(ValueError, "volume_source_conflict"):
            evaluate_volume_anomaly(data)

