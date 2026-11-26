import unittest

from unified_observer_report import render_html, validate_inputs


def live_report():
    return {
        "schema_version": "LUCA_V10_LIVE_WATCHLIST_1",
        "collected_at": "2026-11-25T14:00:00+00:00",
        "source_status": "SEC_TICKER_MAP_HTTP_403",
        "coverage": "ALPACA_SCREENER_CANDIDATES_ONLY_NOT_FULL_MARKET",
        "candidate_count": 1,
        "priority_summary": {"HOLD_INSUFFICIENT_EVIDENCE": 1},
        "rows": [{
            "ticker": "<ABC>", "NO_ORDERS": True, "buy_allowed": False,
            "priority_is_buy_signal": False, "research_priority_rank": 1,
            "research_priority_score": 0,
            "research_priority_label": "HOLD_INSUFFICIENT_EVIDENCE",
            "research_priority_ko": "근거 부족으로 보류",
            "priority_reasons": [{"ko": "<가격 자료 부족>"}],
            "risk_flags": ["SEC_UNVERIFIED", "FLOAT_UNVERIFIED"],
            "iex_price": None, "iex_quote_spread_pct": None,
            "detector_profile": "NASDAQ_7_0",
        }],
        "WATCH_ONLY": True, "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def outcomes_report():
    empty = {"status": "NO_MATURE_FRESH_OBSERVATIONS", "sample_size": 0,
             "mfe_hit_rates_pct": {"5": None, "10": None, "20": None}}
    return {
        "schema_version": "LUCA_V10_PROSPECTIVE_OUTCOMES_1",
        "ledger_event_count": 10, "independent_fresh_ticker_count": 1,
        "independent_mature_fresh_horizons": {"1": 1, "3": 0, "5": 0, "10": 0},
        "descriptive_candidate_scorecard": {key: dict(empty) for key in ("1", "3", "5", "10")},
        "spread_friction_stress": {"scenarios": {}},
        "daily_bar_integrity_guard": {
            "missing_trading_session_record_count": 2,
            "missing_trading_session_unique_ticker_count": 1,
            "model_eligible_missing_trading_session_unique_ticker_count": 0,
        },
        "readiness_blockers": ["INDEPENDENT_MATURE_5_SESSION_OUTCOMES_BELOW_30"],
        "performance_validation_ready": False, "prediction_accuracy_verified": False,
        "WATCH_ONLY": True, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
    }


def validation_report():
    return {
        "schema_version": "LUCA_V10_REFERENCE_VALIDATION_1",
        "verified_signals": 1, "coverage_status": "INSUFFICIENT_VERIFIED_SAMPLE",
        "trade_accuracy_validated": False,
        "WATCH_ONLY": True, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
    }


class UnifiedObserverReportTests(unittest.TestCase):
    def test_one_page_contains_candidates_results_costs_and_easy_explanations(self):
        page = render_html(live_report(), outcomes_report(), validation_report())
        self.assertIn("LUCA V10 통합 관찰 보고서", page)
        self.assertIn("한때 +5%", page)
        self.assertIn("한때 +10%", page)
        self.assertIn("Slippage(주문 미끄러짐)", page)
        self.assertIn("신호가 약하거나 자료가 없는 종목", page)
        self.assertIn("WATCH_ONLY · NOT_VALIDATED · SEC_UNVERIFIED · D · NO_ORDERS", page)
        self.assertIn("&lt;ABC&gt;", page)
        self.assertIn("&lt;가격 자료 부족&gt;", page)
        self.assertNotIn("<ABC>", page)
        self.assertNotIn("<가격 자료 부족>", page)

    def test_candidate_order_or_buy_claim_fails_closed(self):
        live = live_report()
        live["rows"][0]["buy_allowed"] = True
        with self.assertRaisesRegex(ValueError, "candidate_buy_flag"):
            validate_inputs(live, outcomes_report(), validation_report())

    def test_performance_claim_fails_closed(self):
        outcomes = outcomes_report()
        outcomes["performance_validation_ready"] = True
        with self.assertRaisesRegex(ValueError, "unvalidated_performance_claim"):
            validate_inputs(live_report(), outcomes, validation_report())

    def test_candidate_count_mismatch_fails_closed(self):
        live = live_report()
        live["candidate_count"] = 2
        with self.assertRaisesRegex(ValueError, "candidate_count_mismatch"):
            validate_inputs(live, outcomes_report(), validation_report())

    def test_no_candidate_and_unavailable_outcomes_remain_visible(self):
        live = live_report()
        live["candidate_count"] = 0
        live["rows"] = []
        live["priority_summary"] = {}
        outcomes = outcomes_report()
        outcomes.pop("descriptive_candidate_scorecard")
        outcomes.pop("spread_friction_stress")
        page = render_html(live, outcomes, validation_report())
        self.assertIn("신호 없음도 정상 기록", page)
        self.assertIn("표본 없음", page)


if __name__ == "__main__":
    unittest.main()
