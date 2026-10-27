"""Offline evidence-grade tests: do NOT imply 155+ tests are market wins."""
import copy
import datetime as dt
import unittest
from evidence_quality_gate import summarize,check_horizons
from forward_outcomes_iex import build_report
from fixed_clock_reference import prepare_result
from test_fixed_clock_reference import pair, prices, READY
from test_forward_outcomes_iex import bars, LATER

UTC=dt.timezone.utc

def case(include_signal=True):
    frozen,review=pair()
    if not include_signal:
        review["results"][0]["first_pattern"]=None
        review["results"][0]["pattern_count"]=0
    return frozen,review

def downstream(frozen,review):
    outcomes=build_report(frozen,review,{"GPUS":bars()},LATER) if review["results"][0]["pattern_count"] else None
    ref=prepare_result(frozen,review,{"GPUS":prices(),"LAES":prices()},READY)
    return outcomes,ref


class QualityGateTests(unittest.TestCase):
    def test_review_alone_not_predictive(self):
        frozen,review=case()
        out=summarize(frozen,review)
        self.assertEqual(out["candidates_frozen"],2)
        self.assertEqual(out["pattern_observed_symbols"],1)
        self.assertEqual(out["no_pattern_observed_symbols"],1)
        self.assertEqual(out["first_window_sparse_symbols"],2)
        self.assertEqual(out["signal_outcome_evidence"],"AWAITING_OR_UNAVAILABLE")
        self.assertEqual(out["fixed_clock_reference_evidence"],"AWAITING_OR_UNAVAILABLE")
        self.assertEqual(out["all_grades"],{"A":0,"B":0,"C":0,"D":2})
        self.assertFalse(out["prediction_accuracy_verified"])

    def test_valid_complete_outcome_and_reference(self):
        f,r=case();o,b=downstream(f,r)
        report=summarize(f,r,o,b)
        self.assertEqual(report["signal_outcome_evidence"],"OBSERVED_COMPLETE_IEX_ONLY")
        self.assertEqual(report["fixed_clock_reference_evidence"],"OBSERVED_COMPLETE_IEX_ONLY")
        self.assertEqual(report["rows"][0]["signal_horizons_complete"],4)
        self.assertEqual(report["rows"][1]["signal_horizons_complete"],None)
        self.assertEqual(report["rows"][1]["reference_horizons_complete"],4)
        self.assertEqual(report["quality"],"INSUFFICIENT_FOR_PREDICTION")
        self.assertFalse(report["real_trades_allowed"])

    def test_zero_patterns_is_not_no_rise(self):
        f,r=case(False)
        b=prepare_result(f,r,{"GPUS":prices(),"LAES":prices()},READY)
        report=summarize(f,r,reference=b)
        self.assertEqual(report["pattern_observed_symbols"],0)
        self.assertEqual(report["no_pattern_observed_symbols"],2)
        self.assertTrue(report["no_pattern_is_not_proof_of_no_signal"])
        self.assertEqual(report["fixed_clock_reference_evidence"],"OBSERVED_COMPLETE_IEX_ONLY")

    def test_partial_reference_observation(self):
        f,r=case();_,b=downstream(f,r)
        b["rows"][1]["horizons"][2]["status"]="MISSING_IEX_MINUTES"
        b["rows"][1]["horizons"][2]["theoretical_iex_open_to_close_pct"]=None
        b["rows"][1]["horizons"][2]["observed_bars"]=0
        b["rows"][1]["horizons"][2].pop("entry_iex_next_bar_open",None)
        b["rows"][1]["horizons"][2].pop("exit_iex_nth_bar_close",None)
        b["observed_iex_prices_complete"]=7
        report=summarize(f,r,reference=b)
        self.assertEqual(report["fixed_clock_reference_evidence"],"OBSERVED_PARTIAL_IEX")
        self.assertEqual(report["rows"][1]["reference_horizons_complete"],3)

    def test_missing_iex_prices_never_count_as_zero(self):
        f,r=case()
        b=prepare_result(f,r,{"GPUS":[],"LAES":[]},READY)
        report=summarize(f,r,reference=b)
        self.assertEqual(report["fixed_clock_reference_evidence"],"OBSERVED_PARTIAL_IEX")
        self.assertEqual(report["rows"][1]["reference_horizons_complete"],0)

    def test_t0_mismatched_outcomes_rejected(self):
        f,r=case();o,b=downstream(f,r)
        o["frozen_t0_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"OUTCOMES_FROM_ANOTHER_T0"):
            summarize(f,r,o,b)

    def test_t0_mismatched_reference_rejected(self):
        f,r=case();o,b=downstream(f,r)
        b["freeze_sha256"]="bad"
        with self.assertRaisesRegex(ValueError,"REFERENCE_FROM_ANOTHER_T0"):
            summarize(f,r,o,b)

    def test_signal_universe_wrong_rejected(self):
        f,r=case();o,b=downstream(f,r)
        o["signals"][0]["symbol"]="AAPL"
        with self.assertRaisesRegex(ValueError,"OUTCOME_SIGNAL_UNIVERSE_DRIFT"):
            summarize(f,r,o,b)

    def test_missing_a_signal_universe_rejected(self):
        f,r=case();o,b=downstream(f,r)
        o["signals"]=[]
        with self.assertRaisesRegex(ValueError,"OUTCOME_SIGNAL_COUNT_DRIFT"):
            summarize(f,r,o,b)

    def test_reference_universe_mismatch_rejected(self):
        f,r=case();o,b=downstream(f,r)
        b["rows"][1]["symbol"]="TSLA"
        with self.assertRaisesRegex(ValueError,"REFERENCE_UNIVERSE_DRIFT"):
            summarize(f,r,o,b)

    def test_reference_clock_shift_rejected(self):
        f,r=case();o,b=downstream(f,r)
        b["reference_utc"]=(dt.datetime.fromisoformat(b["reference_utc"])+dt.timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError,"REFERENCE_CLOCK_CHANGED_AFTER_T0"):
            summarize(f,r,o,b)

    def test_reference_label_forgery_rejected(self):
        f,r=case();o,b=downstream(f,r)
        b["rows"][1]["initial_16min_pattern_observed"]=True
        with self.assertRaisesRegex(ValueError,"REFERENCE_SIGNAL_LABEL_DRIFT"):
            summarize(f,r,o,b)

    def test_bad_review_coverage_rejected(self):
        f,r=case()
        r["results"][0]["observed_iex_bars"]=999
        with self.assertRaisesRegex(ValueError,"INVALID_OBSERVED_BAR_COUNT"):
            summarize(f,r)

    def test_bad_review_pattern_count_rejected(self):
        f,r=case()
        r["results"][0]["pattern_count"]=55
        with self.assertRaisesRegex(ValueError,"INVALID_PATTERN_COUNT"):
            summarize(f,r)

    def test_no_data_separate_from_failure(self):
        f,r=case(False)
        r["results"][1]["observed_iex_bars"]=0
        out=summarize(f,r)
        self.assertEqual(out["rows"][1]["initial_pattern_status"],"NO_IEX_BARS")
        self.assertEqual(out["rows"][0]["initial_pattern_status"],"NO_PATTERN_WITH_GAPS")

    def test_full_observation_no_signal_does_not_imply_failure(self):
        f,r=case(False)
        r["results"][1]["observed_iex_bars"]=15
        out=summarize(f,r)
        self.assertEqual(out["rows"][1]["initial_pattern_status"],"NO_PATTERN_OBSERVED")
        self.assertFalse(out["prediction_accuracy_verified"])

    def test_outcome_complete_with_price_none_rejected(self):
        f,r=case();o,b=downstream(f,r)
        o["signals"][0]["horizons"][0]["theoretical_iex_open_to_close_pct"]=None
        with self.assertRaisesRegex(ValueError,"BAD_COMPLETE_HORIZON"):
            summarize(f,r,o,b)

    def test_falsely_verified_fills_rejected(self):
        f,r=case();o,b=downstream(f,r)
        o["signals"][0]["horizons"][0]["real_fill_verified"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_FILL_CLAIM"):
            summarize(f,r,o,b)

    def test_invalid_horizon_missing_with_fake_zero_return_rejected(self):
        f,r=case();o,b=downstream(f,r)
        x=o["signals"][0]["horizons"][3]
        x["status"]="MISSING_IEX_MINUTES"
        x["observed_bars"]=20
        # A missing horizon cannot expose a number as its return.
        with self.assertRaisesRegex(ValueError,"MISSING_HORIZON_HAS_RESULT"):
            summarize(f,r,o,b)

    def test_reference_complete_count_falsified_rejected(self):
        f,r=case();o,b=downstream(f,r)
        b["observed_iex_prices_complete"]=5
        with self.assertRaisesRegex(ValueError,"REFERENCE_COMPLETENESS_DRIFT"):
            summarize(f,r,o,b)

    def test_outcome_complete_count_falsified_rejected(self):
        f,r=case();o,b=downstream(f,r)
        o["complete_horizons"]=30
        with self.assertRaisesRegex(ValueError,"OUTCOME_COMPLETENESS_DRIFT"):
            summarize(f,r,o,b)

    def test_pre_review_outcome_rejected(self):
        f,r=case();o,b=downstream(f,r)
        o["outcomes_checked_at_utc"]=r["reviewed_at_utc"]
        with self.assertRaisesRegex(ValueError,"OUTCOMES_NOT_MATURE"):
            summarize(f,r,o,b)

    def test_wrong_market_feed_rejected(self):
        f,r=case();o,b=downstream(f,r)
        o["same_exchange_limit"]="SIP_REALTIME"
        with self.assertRaisesRegex(ValueError,"MIXED_MARKET_FEED"):
            summarize(f,r,o,b)

    def test_grade_a_in_research_rejected(self):
        f,r=case();o,b=downstream(f,r)
        b["rows"][0]["grade"]="A"
        with self.assertRaisesRegex(ValueError,"UNSAFE_REFERENCE_ROW"):
            summarize(f,r,o,b)

    def test_integrity_rejects_wrong_horizon_set(self):
        f,r=case();o,b=downstream(f,r)
        o["horizon_minutes"]=[5,15,60]
        with self.assertRaisesRegex(ValueError,"INVALID_HORIZON_SET"):
            summarize(f,r,o,b)


if __name__=="__main__":
    unittest.main()
