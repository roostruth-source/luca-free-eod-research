"""Offline IEX coverage audit regression tests; never use synthetic as live result."""
import copy
import unittest
from iex_coverage_audit import audit
from test_live_trial_contract import make_synthetic,mature_synthetic,SOURCE

def fixture():
    frozen,review=make_synthetic()
    _,reference=mature_synthetic(frozen,review)
    return frozen,review,reference

class IexCoverageAuditTests(unittest.TestCase):
    def test_valid_complete_reference_and_sparse_initial(self):
        f,r,ref=fixture()
        x=audit(SOURCE,f,r,ref)
        self.assertEqual(x["initial"]["observed_iex_bars"],12)
        self.assertEqual(x["initial"]["expected_symbol_minutes"],14)
        self.assertEqual(x["initial"]["iex_minute_presence_pct"],85.71)
        self.assertEqual([h["fully_observed_symbols"] for h in x["fixed_clock_reference"]],[1,1,1,1])
        self.assertTrue(x["missing_bar_cause_unknown"])
        self.assertTrue(x["raw_bar_timestamps_not_in_source_artifact"])
        self.assertFalse(x["real_trades_allowed"])

    def test_missing_reference_rejected(self):
        f,r,ref=fixture()
        with self.assertRaises(ValueError):
            audit(SOURCE,f,r,None)

    def test_wrong_reference_t0_rejected(self):
        f,r,ref=fixture()
        ref["freeze_sha256"]="0"*64
        with self.assertRaises(ValueError):
            audit(SOURCE,f,r,ref)

    def test_wrong_source_run_rejected(self):
        f,r,ref=fixture()
        m=copy.deepcopy(SOURCE);m["conclusion"]="failure"
        with self.assertRaisesRegex(ValueError,"PROSPECTIVE_RUN_NOT_SUCCESSFUL"):
            audit(m,f,r,ref)

    def test_fake_trading_grade_rejected(self):
        f,r,ref=fixture()
        r["results"][0]["grade"]="A"
        with self.assertRaises(ValueError):
            audit(SOURCE,f,r,ref)

    def test_bad_horizon_count_rejected(self):
        f,r,ref=fixture()
        ref["rows"][0]["horizons"][0]["observed_bars"]=6
        with self.assertRaisesRegex(ValueError,"INVALID_HORIZON_COVERAGE"):
            audit(SOURCE,f,r,ref)

    def test_false_complete_status_rejected(self):
        f,r,ref=fixture()
        ref["rows"][0]["horizons"][0]["status"]="MISSING_IEX_MINUTES"
        with self.assertRaisesRegex(ValueError,"MISSING_HORIZON_HAS_RESULT"):
            audit(SOURCE,f,r,ref)

    def test_bad_initial_count_rejected(self):
        f,r,ref=fixture()
        r["results"][0]["observed_iex_bars"]=15
        with self.assertRaises(ValueError):
            audit(SOURCE,f,r,ref)

    def test_order_mismatch_rejected(self):
        f,r,ref=fixture()
        ref["rows"][0]["symbol"]="OTHER"
        with self.assertRaises(ValueError):
            audit(SOURCE,f,r,ref)

    def test_not_an_accuracy_statistic(self):
        f,r,ref=fixture()
        x=audit(SOURCE,f,r,ref)
        self.assertFalse(x["prediction_accuracy_verified"])
        self.assertTrue(x["not_full_us_market_coverage"])
        self.assertTrue(x["missing_bar_is_not_zero_return"])

if __name__=="__main__":
    unittest.main()
