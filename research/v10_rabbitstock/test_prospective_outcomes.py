from datetime import date
import json
import unittest
import urllib.parse

from prospective_outcomes import build_outcomes, fetch_daily_bars, render_html


def event(observed="2026-11-18T15:00:00Z", status="FRESH_WATCH_ONLY"):
    return {"ticker": "ABC", "observed_at": observed, "iex_reference_price": 1.0,
            "observation_status": status, "chain_hash": "a" * 64, "NO_ORDERS": True,
            "security_scope": {"status": "COMMON_EQUITY_CANDIDATE_SCOPE",
                               "financial_status": "N"}}


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
    def test_mobile_readiness_html_is_korean_safe_and_escapes_untrusted_text(self):
        report = build_outcomes(ledger(event()), BARS, "2026-11-19T22:00:00Z")
        report["independent_observation_date_counts"] = {"<script>x</script>": 1}
        report["readiness_blockers"].append("<img src=x onerror=alert(1)>")
        page = render_html(report)
        self.assertIn("LUCA V10 성과 준비도", page)
        self.assertIn("아직 성능 검증 전", page)
        self.assertIn("Slippage(주문 미끄러짐)", page)
        self.assertIn("Spread stress (호가 차이 부담 가정)", page)
        self.assertIn("실제 Fill(체결)", page)
        self.assertIn("NO_ORDERS", page)
        self.assertIn("&lt;script&gt;x&lt;/script&gt;", page)
        self.assertNotIn("<script>x</script>", page)
        self.assertNotIn("<img src=x onerror=alert(1)>", page)

    def test_daily_bar_request_freezes_requested_adjustment_mode(self):
        requests = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps({"bars": {"ABC": [{
                    "t": "2026-11-18T05:00:00Z", "o": 1, "h": 1.2,
                    "l": .9, "c": 1.1,
                }]}, "next_page_token": None}).encode()

        def opener(request, timeout):
            requests.append((request, timeout))
            return Response()

        rows = fetch_daily_bars(["ABC"], date(2026, 11, 18), date(2026, 11, 18),
                                "key", "secret", opener, adjustment="split")
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(requests[0][0].full_url).query)
        self.assertEqual(query["adjustment"], ["split"])
        self.assertEqual(query["feed"], ["iex"])
        self.assertEqual(len(rows["ABC"]), 1)
        with self.assertRaisesRegex(ValueError, "invalid_bar_adjustment"):
            fetch_daily_bars(["ABC"], date(2026, 11, 18), date(2026, 11, 18),
                             "key", "secret", opener, adjustment="all")

    def test_regular_session_observation_starts_next_day_to_avoid_pre_signal_ohlc(self):
        result = build_outcomes(ledger(event()), BARS, "2026-11-19T22:00:00Z")
        first = result["records"][0]["outcomes"]
        self.assertAlmostEqual(first["1"]["close_return_pct"], 30.0)
        self.assertEqual(first["3"]["completed_sessions"], 1)
        self.assertEqual(result["mature_fresh_horizons"]["1"], 1)
        self.assertEqual(result["records"][0]["outcome_session_anchor"],
                         "NEXT_SESSION_REQUIRED_REGULAR_OR_LATER_OBSERVATION")
        self.assertFalse(result["prediction_accuracy_verified"])

    def test_after_close_observation_starts_next_session(self):
        result = build_outcomes(ledger(event("2026-11-18T22:00:00Z")), BARS,
                                "2026-11-19T22:00:00Z")
        outcome = result["records"][0]["outcomes"]["1"]
        self.assertEqual(outcome["exit_session"], "2026-11-19")
        self.assertAlmostEqual(outcome["close_return_pct"], 30.0)

    def test_current_incomplete_session_is_excluded(self):
        result = build_outcomes(ledger(event()), BARS, "2026-11-19T19:00:00Z")
        self.assertEqual(result["records"][0]["outcomes"]["3"]["completed_sessions"], 0)

    def test_premarket_can_use_same_day_because_full_regular_bar_is_forward(self):
        premarket = event("2026-11-18T12:00:00Z", status="FRESH_PREMARKET_WATCH_ONLY")
        result = build_outcomes(ledger(premarket), BARS, "2026-11-19T22:00:00Z")
        first = result["records"][0]
        self.assertEqual(first["outcome_session_anchor"],
                         "SAME_SESSION_ALLOWED_PREMARKET_OBSERVATION")
        self.assertAlmostEqual(first["outcomes"]["1"]["close_return_pct"], 10.0)
        self.assertEqual(first["outcomes"]["3"]["completed_sessions"], 2)

    def test_raw_split_parity_keeps_descriptive_record_but_is_not_official_verification(self):
        result = build_outcomes(ledger(event()), BARS, "2026-11-19T22:00:00Z", BARS)
        record = result["records"][0]
        self.assertTrue(record["eligible_for_model_validation"])
        self.assertEqual(
            record["corporate_action_basis_guard"]["status"],
            "PROVIDER_RAW_SPLIT_PARITY_OBSERVED_NOT_OFFICIAL_VERIFICATION")
        self.assertEqual(result["corporate_action_basis_guard"]
                         ["raw_split_parity_observed_record_count"], 1)
        self.assertFalse(result["corporate_action_basis_verified"])

    def test_split_adjustment_difference_is_quarantined_from_scorecards(self):
        split = {"ABC": [
            {"session_date": "2026-11-18", "o": .1, "h": .12, "l": .09, "c": .11},
            {"session_date": "2026-11-19", "o": .11, "h": .14, "l": .10, "c": .13},
        ]}
        result = build_outcomes(ledger(event()), BARS, "2026-11-19T22:00:00Z", split)
        record = result["records"][0]
        self.assertFalse(record["eligible_for_model_validation"])
        self.assertEqual(record["corporate_action_basis_guard"]["status"],
                         "PROVIDER_SPLIT_ADJUSTMENT_DETECTED")
        self.assertEqual(record["outcomes"]["1"]["status"],
                         "CORPORATE_ACTION_BASIS_BLOCKED")
        self.assertEqual(result["fresh_price_observation_count"], 1)
        self.assertEqual(result["corporate_action_basis_blocked_fresh_observation_count"], 1)
        self.assertEqual(result["fresh_observation_count"], 0)
        self.assertEqual(result["descriptive_candidate_scorecard"]["1"]["sample_size"], 0)
        self.assertEqual(result["corporate_action_basis_guard"]
                         ["split_adjustment_blocked_record_count"], 1)

    def test_regular_outcome_skips_observation_day_but_split_guard_keeps_it(self):
        split = {"ABC": [
            {"session_date": "2026-11-18", "o": .1, "h": .12, "l": .09, "c": .11},
            BARS["ABC"][1],
        ]}
        result = build_outcomes(ledger(event()), BARS, "2026-11-19T22:00:00Z", split)
        record = result["records"][0]
        self.assertEqual(record["outcome_session_anchor"],
                         "NEXT_SESSION_REQUIRED_REGULAR_OR_LATER_OBSERVATION")
        self.assertEqual(record["corporate_action_basis_guard"]["status"],
                         "PROVIDER_SPLIT_ADJUSTMENT_DETECTED")
        self.assertEqual(record["corporate_action_basis_guard"]["changed_session_dates"],
                         ["2026-11-18"])
        self.assertEqual(record["outcomes"]["1"]["status"],
                         "CORPORATE_ACTION_BASIS_BLOCKED")

    def test_raw_split_session_mismatch_is_quarantined(self):
        split = {"ABC": BARS["ABC"][:1]}
        result = build_outcomes(ledger(event()), BARS, "2026-11-19T22:00:00Z", split)
        record = result["records"][0]
        self.assertFalse(record["eligible_for_model_validation"])
        self.assertEqual(record["corporate_action_basis_guard"]["status"],
                         "RAW_SPLIT_SESSION_SET_MISMATCH")
        self.assertEqual(record["outcomes"]["1"]["status"],
                         "CORPORATE_ACTION_BASIS_BLOCKED")

    def test_stale_observation_never_enters_validation_cohort(self):
        result = build_outcomes(ledger(event(status="STALE_OR_MISSING_PRICE_BLOCKED")),
                                BARS, "2026-11-19T22:00:00Z")
        self.assertEqual(result["fresh_observation_count"], 0)
        self.assertFalse(result["records"][0]["eligible_for_model_validation"])

    def test_etf_and_financial_status_risk_are_not_model_cohort_samples(self):
        etf = event()
        etf["security_scope"] = {"status": "EXCLUDED_ETF_OR_ETP",
                                 "financial_status": "NOT_AVAILABLE"}
        deficient = event()
        deficient["ticker"] = "DEF"
        deficient["chain_hash"] = "b" * 64
        deficient["security_scope"] = {"status": "COMMON_EQUITY_CANDIDATE_SCOPE",
                                       "financial_status": "D"}
        result = build_outcomes(ledger_many(etf, deficient), {
            **BARS, "DEF": BARS["ABC"],
        }, "2026-11-19T22:00:00Z")
        self.assertEqual(result["fresh_price_observation_count"], 2)
        self.assertEqual(result["candidate_scope_blocked_fresh_observation_count"], 2)
        self.assertEqual(result["fresh_observation_count"], 0)
        self.assertFalse(result["records"][0]["eligible_for_model_validation"])
        self.assertEqual(result["records"][0]["candidate_scope_guard"]["status"],
                         "SECURITY_NOT_COMMON_EQUITY_SCOPE")
        self.assertEqual(result["records"][1]["candidate_scope_guard"]["status"],
                         "FINANCIAL_STATUS_NOT_ELIGIBLE")
        audit = result["descriptive_scope_audit_segment_scorecards"]
        self.assertIn("security_scope:excluded_etf_or_etp", audit)
        self.assertIn("financial_status:d", audit)

    def test_legacy_missing_scope_is_audit_only_not_model_cohort(self):
        legacy = event()
        del legacy["security_scope"]
        result = build_outcomes(ledger(legacy), BARS, "2026-11-19T22:00:00Z")
        self.assertFalse(result["records"][0]["eligible_for_model_validation"])
        self.assertEqual(result["records"][0]["candidate_scope_guard"]["status"],
                         "LEGACY_SCOPE_MISSING")
        self.assertEqual(result["fresh_observation_count"], 0)
        self.assertIn("security_scope:legacy_context_missing",
                      result["descriptive_scope_audit_segment_scorecards"])

    def test_premarket_observation_has_own_eligible_segment(self):
        premarket = event("2026-11-18T12:05:00Z", status="FRESH_PREMARKET_WATCH_ONLY")
        result = build_outcomes(ledger(premarket), BARS, "2026-11-19T22:00:00Z")
        self.assertEqual(result["fresh_observation_count"], 1)
        self.assertTrue(result["records"][0]["eligible_for_model_validation"])
        self.assertIn("session:premarket", result["descriptive_segment_scorecards"])
        self.assertEqual(
            result["descriptive_segment_scorecards"]["session:premarket"]
            ["horizons"]["1"]["sample_size"], 1)

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
        self.assertAlmostEqual(one_day["mfe_hit_rates_pct"]["5"], 50.0)
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

    def test_sample_gate_alone_never_claims_performance_validation_ready(self):
        sessions = ["2026-11-16", "2026-11-17", "2026-11-18",
                    "2026-11-19", "2026-11-20"]
        events = []
        bars = {}
        for index in range(30):
            ticker = f"T{index:02d}"
            item = event("2026-11-16T12:00:00Z", status="FRESH_PREMARKET_WATCH_ONLY")
            item["ticker"] = ticker
            events.append(item)
            bars[ticker] = [
                {"session_date": day, "o": 1.0, "h": 1.1,
                 "l": .9, "c": 1.0} for day in sessions]
        result = build_outcomes(ledger_many(*events), bars,
                                "2026-11-20T22:00:00Z")
        self.assertTrue(result["sample_size_gate_met"])
        self.assertEqual(result["independent_mature_fresh_horizons"]["5"], 30)
        self.assertEqual(result["independent_observation_date_count"], 1)
        self.assertFalse(result["temporal_diversity_gate_met"])
        self.assertIn("INDEPENDENT_OBSERVATION_DATES_BELOW_5",
                      result["readiness_blockers"])
        self.assertFalse(result["corporate_action_basis_verified"])
        self.assertFalse(result["performance_validation_ready"])
        self.assertIn("CORPORATE_ACTION_BASIS_UNVERIFIED",
                      result["readiness_blockers"])
        self.assertIn("REAL_FILL_AND_SLIPPAGE_NOT_MEASURED",
                      result["readiness_blockers"])

    def test_temporal_diversity_requires_five_distinct_et_observation_dates(self):
        events = []
        days = ["2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12", "2026-11-13"]
        for index, day in enumerate(days):
            item = event(day + "T15:00:00Z")
            item["ticker"] = f"D{index}"
            item["chain_hash"] = f"{index + 1:064x}"
            events.append(item)
        result = build_outcomes(ledger_many(*events), {}, "2026-11-20T22:00:00Z")
        self.assertEqual(result["independent_observation_date_count"], 5)
        self.assertTrue(result["temporal_diversity_gate_met"])
        self.assertNotIn("INDEPENDENT_OBSERVATION_DATES_BELOW_5",
                         result["readiness_blockers"])
        self.assertFalse(result["sample_size_gate_met"])

    def test_segment_scorecards_separate_frozen_candidate_context(self):
        first = event()
        first.update({
            "screener_groups": {"active_volume": 3, "gainers": 2},
            "iex_quote_spread_pct": 1.5,
            "sec_status": "RECENT_FILINGS_REQUIRE_REVIEW",
            "volume_first_context": {"status": "RECENT_VOLUME_FIRST_PATTERN_RESEARCH_ONLY",
                                     "volume_first_recent": True, "NO_ORDERS": True},
            "research_priority": {"status": "PREDECLARED_RESEARCH_ORDER_NOT_BUY_SIGNAL",
                                  "score": 80, "rank": 1,
                                  "label": "PRIORITY_1_RESEARCH",
                                  "priority_is_buy_signal": False},
            "security_scope": {"status": "COMMON_EQUITY_CANDIDATE_SCOPE",
                               "financial_status": "N"},
            "listing_action_context": {
                "status": "SEC_TEXT_LISTING_OR_SPLIT_RISK_REVIEW_REQUIRED",
                "risk_detected": True,
                "signals": [{"code": "REVERSE_SPLIT"}],
            },
            "sec_supply_context": {
                "status": "SEC_TEXT_SUPPLY_RISK_REVIEW_REQUIRED",
                "dilution_risk_detected": True,
                "os_verified": True,
                "os_stale": False,
                "signals": [{"code": "ATM"}, {"code": "WARRANT"}],
            },
            "issuer_region_context": {"detector_profile": "CHINA_1_0"},
        })
        second = event()
        second.update({
            "ticker": "DEF", "chain_hash": "b" * 64,
            "screener_groups": {"active_volume": 20, "losers": 4},
            "iex_quote_spread_pct": 8.0,
            "sec_status": "SEC_NOT_CHECKED_SOURCE_UNAVAILABLE",
            "volume_first_context": {"status": "NO_RECENT_VOLUME_FIRST_PATTERN",
                                     "volume_first_recent": False, "NO_ORDERS": True},
            "research_priority": {"status": "PREDECLARED_RESEARCH_ORDER_NOT_BUY_SIGNAL",
                                  "score": 45, "rank": 2,
                                  "label": "PRIORITY_2_WATCH",
                                  "priority_is_buy_signal": False},
            "security_scope": {"status": "EXCLUDED_ETF_OR_ETP",
                               "financial_status": "D"},
            "listing_action_context": {
                "status": "SEC_LISTING_TEXT_UNAVAILABLE",
                "risk_detected": False, "signals": [],
            },
            "sec_supply_context": {
                "status": "SEC_SUPPLY_TEXT_UNAVAILABLE",
                "dilution_risk_detected": False, "signals": [],
            },
            "issuer_region_context": {"detector_profile": "NASDAQ_7_0"},
        })
        result = build_outcomes(ledger_many(first, second), {
            **BARS,
            "DEF": BARS["ABC"],
        }, "2026-11-19T22:00:00Z")
        segments = result["descriptive_scope_audit_segment_scorecards"]
        self.assertEqual(segments["volume:rank_1_10"]["independent_ticker_count"], 1)
        self.assertEqual(segments["volume:rank_11_40"]["independent_ticker_count"], 1)
        self.assertEqual(segments["mover:gainer"]["horizons"]["1"]["sample_size"], 1)
        self.assertEqual(segments["mover:loser"]["horizons"]["1"]["sample_size"], 1)
        self.assertIn("spread:0_2_pct", segments)
        self.assertIn("spread:over_5_pct", segments)
        self.assertIn("sec:recent_filings_require_review", segments)
        self.assertIn("sec:source_unavailable_or_unchecked", segments)
        self.assertIn("volume_first:recent_pattern", segments)
        self.assertIn("volume_first:no_recent_pattern", segments)
        self.assertIn("priority:priority_1_research", segments)
        self.assertIn("priority:priority_2_watch", segments)
        self.assertIn("security_scope:common_equity_candidate_scope", segments)
        self.assertIn("security_scope:excluded_etf_or_etp", segments)
        self.assertIn("financial_status:n", segments)
        self.assertIn("financial_status:d", segments)
        self.assertIn("listing_action:reverse_split", segments)
        self.assertIn("listing_action:unavailable_or_partial", segments)
        self.assertIn("sec_supply:atm", segments)
        self.assertIn("sec_supply:warrant", segments)
        self.assertIn("sec_supply:unavailable_or_partial", segments)
        self.assertIn("os:verified_point_in_time_180d_or_less", segments)
        self.assertIn("os:unverified", segments)
        self.assertIn("profile:china_1_0", segments)
        self.assertIn("profile:nasdaq_7_0", segments)
        self.assertIn("session:regular", segments)
        self.assertFalse(segments["volume:rank_1_10"]["comparison_ready"])
        self.assertNotIn("security_scope:excluded_etf_or_etp",
                         result["descriptive_segment_scorecards"])

    def test_spread_friction_stress_is_scenario_only_and_never_real_fill(self):
        first = event()
        first["iex_quote_spread_pct"] = 2.0
        second = event()
        second.update({"ticker": "DEF", "chain_hash": "b" * 64,
                       "iex_quote_spread_pct": 10.0})
        result = build_outcomes(ledger_many(first, second), {
            **BARS, "DEF": BARS["ABC"],
        }, "2026-11-19T22:00:00Z")
        stress = result["spread_friction_stress"]
        self.assertEqual(stress["spread_recorded_ticker_count"], 2)
        self.assertEqual(stress["spread_missing_ticker_count"], 0)
        self.assertAlmostEqual(stress["spread_distribution_pct"]["median"], 6.0)
        self.assertAlmostEqual(stress["spread_distribution_pct"]["p90_nearest_rank"], 10.0)
        self.assertEqual(stress["spread_distribution_pct"]["over_5_pct_count"], 1)
        half = stress["scenarios"]["HALF_SPREAD_ENTRY"]["horizons"]["1"]
        full = stress["scenarios"]["FULL_SPREAD_ENTRY"]["horizons"]["1"]
        self.assertEqual(half["sample_size"], 2)
        self.assertAlmostEqual(half["average_close_return_pct"], 26.2611975483)
        self.assertAlmostEqual(full["average_close_return_pct"], 22.8163992870)
        self.assertFalse(stress["real_fill_measured"])
        self.assertFalse(stress["commission_measured"])
        self.assertFalse(stress["market_impact_measured"])
        self.assertIn("REAL_FILL_AND_SLIPPAGE_NOT_MEASURED",
                      result["readiness_blockers"])

    def test_missing_spread_is_not_imputed_into_friction_stress(self):
        result = build_outcomes(ledger(event()), BARS, "2026-11-19T22:00:00Z")
        stress = result["spread_friction_stress"]
        self.assertEqual(stress["spread_recorded_ticker_count"], 0)
        self.assertEqual(stress["spread_missing_ticker_count"], 1)
        self.assertIsNone(stress["spread_distribution_pct"]["median"])
        self.assertEqual(
            stress["scenarios"]["HALF_SPREAD_ENTRY"]["horizons"]["1"]["sample_size"], 0)


if __name__ == "__main__":
    unittest.main()
