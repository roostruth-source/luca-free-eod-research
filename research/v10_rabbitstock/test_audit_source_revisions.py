import unittest

from audit_source_revisions import audit_revisions


def observation(asof, close, low=0.40):
    return {
        "source_name": "Yahoo Finance",
        "source_url": "https://finance.yahoo.com/quote/INLF/history/",
        "retrieved_at": "2026-11-13T10:05:00+09:00",
        "source_data_asof": asof,
        "open": 0.5299,
        "high": 0.5580,
        "low": low,
        "close": close,
        "volume": 7887046,
    }


def payload(*observations):
    return {
        "ticker": "INLF",
        "session_close_at": "2026-11-12T16:00:00-05:00",
        "evaluation_asof": "2026-11-13T10:05:00+09:00",
        "observations": list(observations),
    }


class SourceRevisionAuditTests(unittest.TestCase):
    def test_preclose_value_revised_to_final_value(self):
        first = observation("2026-11-12T14:11:19-05:00", 0.4285, 0.4150)
        second = observation("2026-11-12T16:00:00-05:00", 0.4110, 0.4000)
        result = audit_revisions(payload(first, second))
        self.assertEqual(result["unique_source_count"], 1)
        self.assertEqual(result["revision_count"], 1)
        self.assertEqual(result["final_candidate_count"], 1)
        self.assertTrue(result["revisions"][0]["old_was_pre_close"])
        self.assertAlmostEqual(
            result["revisions"][0]["changes"]["close"]["change_pct"],
            -4.084014002333714,
        )
        self.assertTrue(result["WATCH_ONLY"])
        self.assertTrue(result["NO_ORDERS"])

    def test_preclose_only_has_no_final_candidate(self):
        result = audit_revisions(
            payload(observation("2026-11-12T14:11:19-05:00", 0.4285))
        )
        self.assertEqual(result["status"], "NO_FINAL_SOURCE_SNAPSHOT")
        self.assertEqual(result["final_candidate_count"], 0)

    def test_same_url_is_never_two_independent_sources(self):
        first = observation("2026-11-12T16:00:00-05:00", 0.4110)
        second = observation("2026-11-12T16:05:00-05:00", 0.4110)
        result = audit_revisions(payload(first, second))
        self.assertEqual(result["unique_source_count"], 1)
        self.assertEqual(result["final_candidate_count"], 1)

    def test_future_data_timestamp_is_rejected(self):
        item = observation("2026-11-12T20:00:00-05:00", 0.4110)
        item["retrieved_at"] = "2026-11-12T18:07:00-05:00"
        with self.assertRaisesRegex(ValueError, "source_data_asof_after_retrieval"):
            audit_revisions(payload(item))


if __name__ == "__main__":
    unittest.main()
