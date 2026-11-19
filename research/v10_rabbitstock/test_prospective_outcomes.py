import unittest

from prospective_outcomes import build_outcomes


def event(observed="2026-11-18T15:00:00Z", status="FRESH_WATCH_ONLY"):
    return {"ticker": "ABC", "observed_at": observed, "iex_reference_price": 1.0,
            "observation_status": status, "chain_hash": "a" * 64, "NO_ORDERS": True}


def ledger(item):
    return {"schema_version": "LUCA_V10_PROSPECTIVE_LEDGER_1", "events": [item],
            "NO_ORDERS": True}


def ledger_many(*items):
    return {"schema_version": "LUCA_V10_PROSPECTIVE_LEDGER_1", "events": list(items),
            "NO_ORDERS": True}


BARS = {"ABC": [
    {"session_date": "2026-11-18", "o": 1.0, "h": 1.2, "l": .9, "c": 1.1},
    {"session_date": "2026-11-19", "o": 1.1, "h": 1.4, "l": 1.0, "c": 1.3},
]}


class ProspectiveOutcomesTests(unittest.TestCase):
    def test_regular_session_observation_uses_same_day_close(self):
        result = build_outcomes(ledger(event()), BARS, "2026-11-19T22:00:00Z")
        first = result["records"][0]["outcomes"]
        self.assertAlmostEqual(first["1"]["close_return_pct"], 10.0)
        self.assertEqual(first["3"]["completed_sessions"], 2)
        self.assertEqual(result["mature_fresh_horizons"]["1"], 1)
        self.assertFalse(result["prediction_accuracy_verified"])

    def test_after_close_observation_starts_next_session(self):
        result = build_outcomes(ledger(event("2026-11-18T22:00:00Z")), BARS,
                                "2026-11-19T22:00:00Z")
        outcome = result["records"][0]["outcomes"]["1"]
        self.assertEqual(outcome["exit_session"], "2026-11-19")
        self.assertAlmostEqual(outcome["close_return_pct"], 30.0)

    def test_current_incomplete_session_is_excluded(self):
        result = build_outcomes(ledger(event()), BARS, "2026-11-19T19:00:00Z")
        self.assertEqual(result["records"][0]["outcomes"]["3"]["completed_sessions"], 1)

    def test_stale_observation_never_enters_validation_cohort(self):
        result = build_outcomes(ledger(event(status="STALE_OR_MISSING_PRICE_BLOCKED")),
                                BARS, "2026-11-19T22:00:00Z")
        self.assertEqual(result["fresh_observation_count"], 0)
        self.assertFalse(result["records"][0]["eligible_for_model_validation"])

    def test_descriptive_scorecard_uses_only_mature_fresh_candidates(self):
        second = event()
        second["ticker"] = "DEF"
        second["chain_hash"] = "b" * 64
        stale = event(status="STALE_OR_MISSING_PRICE_BLOCKED")
        stale["ticker"] = "STALE"
        stale["chain_hash"] = "c" * 64
        bars = {
            **BARS,
            "DEF": [
                {"session_date": "2026-11-18", "o": 1.0, "h": 1.05, "l": .80, "c": .90},
                {"session_date": "2026-11-19", "o": .90, "h": 1.00, "l": .85, "c": .95},
            ],
            "STALE": BARS["ABC"],
        }
        result = build_outcomes(ledger_many(event(), second, stale), bars,
                                "2026-11-19T22:00:00Z")
        one_day = result["descriptive_candidate_scorecard"]["1"]
        self.assertEqual(one_day["sample_size"], 2)
        self.assertAlmostEqual(one_day["positive_close_rate_pct"], 50.0)
        self.assertAlmostEqual(one_day["mfe_hit_rates_pct"]["5"], 100.0)
        self.assertAlmostEqual(one_day["mfe_hit_rates_pct"]["10"], 50.0)
        self.assertAlmostEqual(one_day["mfe_hit_rates_pct"]["20"], 50.0)
        self.assertAlmostEqual(one_day["mae_minus_10_or_worse_rate_pct"], 50.0)
        self.assertEqual(result["scorecard_scope"],
                         "FIRST_FRESH_OBSERVATION_PER_TICKER_NOT_BUY_SIGNALS")
        self.assertFalse(result["prediction_accuracy_verified"])

    def test_scorecard_does_not_count_immature_horizon(self):
        result = build_outcomes(ledger(event()), BARS, "2026-11-19T22:00:00Z")
        three_day = result["descriptive_candidate_scorecard"]["3"]
        self.assertEqual(three_day["sample_size"], 0)
        self.assertIsNone(three_day["mfe_hit_rates_pct"]["10"])

    def test_repeated_ticker_is_not_counted_as_independent_sample(self):
        repeat = event("2026-11-18T15:30:00Z")
        repeat["chain_hash"] = "d" * 64
        result = build_outcomes(ledger_many(event(), repeat), BARS,
                                "2026-11-19T22:00:00Z")
        self.assertEqual(result["fresh_observation_count"], 2)
        self.assertEqual(result["independent_fresh_ticker_count"], 1)
        self.assertEqual(result["repeated_fresh_observation_count"], 1)
        self.assertEqual(result["descriptive_candidate_scorecard"]["1"]["sample_size"], 1)
        self.assertEqual(result["independent_cohort_rule"],
                         "FIRST_FRESH_OBSERVATION_PER_TICKER")

    def test_segment_scorecards_separate_frozen_candidate_context(self):
        first = event()
        first.update({
            "screener_groups": {"active_volume": 3, "gainers": 2},
            "iex_quote_spread_pct": 1.5,
            "sec_status": "RECENT_FILINGS_REQUIRE_REVIEW",
        })
        second = event()
        second.update({
            "ticker": "DEF", "chain_hash": "b" * 64,
            "screener_groups": {"active_volume": 20, "losers": 4},
            "iex_quote_spread_pct": 8.0,
            "sec_status": "SEC_NOT_CHECKED_SOURCE_UNAVAILABLE",
        })
        result = build_outcomes(ledger_many(first, second), {
            **BARS,
            "DEF": BARS["ABC"],
        }, "2026-11-19T22:00:00Z")
        segments = result["descriptive_segment_scorecards"]
        self.assertEqual(segments["volume:rank_1_10"]["independent_ticker_count"], 1)
        self.assertEqual(segments["volume:rank_11_40"]["independent_ticker_count"], 1)
        self.assertEqual(segments["mover:gainer"]["horizons"]["1"]["sample_size"], 1)
        self.assertEqual(segments["mover:loser"]["horizons"]["1"]["sample_size"], 1)
        self.assertIn("spread:0_2_pct", segments)
        self.assertIn("spread:over_5_pct", segments)
        self.assertIn("sec:recent_filings_require_review", segments)
        self.assertIn("sec:source_unavailable_or_unchecked", segments)
        self.assertFalse(segments["volume:rank_1_10"]["comparison_ready"])


if __name__ == "__main__":
    unittest.main()
