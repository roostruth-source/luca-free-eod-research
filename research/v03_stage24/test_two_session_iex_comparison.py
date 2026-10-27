"""Synthetic-only comparison tests; first real counts are fixed baseline, not simulated profits."""
import copy
import datetime as dt
import unittest

from prospective_iex_research import digest_frozen,review
from iex_timestamp_provenance import build_minute_provenance
from test_prospective_iex_research import T1,make_bar
from test_live_trial_contract import make_synthetic
from two_session_iex_comparison import compare,FIRST_ID

FIRST={"schema":"LUCA_V03_IEX_COVERAGE_AUDIT_V1",
       "source_run_id":FIRST_ID,"frozen_symbols":12,
       "initial":{"observed_iex_bars":94,"expected_symbol_minutes":168,
                  "iex_minute_presence_pct":55.95,
                  "fully_observed_symbols":1,"sparse_symbols":11},
       "no_signal_outcomes_because_no_pattern":True,
       "validation_status":"NOT_VALIDATED","real_trades_allowed":False}
API={"get_only":True,"http_statuses":[200],"final_page_token_absent":True}
SECOND_ID=40599999999
UTC=dt.timezone.utc


def fixture(bar_minutes=(0,1,2,3,4,5,7,9,11)):
    f,_=make_synthetic()
    f["selected_at_utc"]=(dt.datetime.fromisoformat(f["selected_at_utc"])+dt.timedelta(days=1)).isoformat()
    f["sha256"]=digest_frozen(f)
    at=T1+dt.timedelta(days=1)
    bars=[]
    for i in bar_minutes:
        b=make_bar(i,low=1+i*0.01,volume=300 if i==5 else 20)
        b["t"]=(dt.datetime.fromisoformat(b["t"])+dt.timedelta(days=1)).isoformat()
        bars.append(b)
    r=review(f,{"GPUS":bars},at)
    p=build_minute_provenance(f,r,{"GPUS":bars},at+dt.timedelta(seconds=2),API)
    return f,r,p


class TwoSessionTests(unittest.TestCase):
    def setUp(self):
        self.f,self.r,self.p=fixture()
        self.first=copy.deepcopy(FIRST)

    def compare(self):
        return compare(self.first,self.f,self.r,self.p,SECOND_ID)

    def test_compares_different_windows_as_rates_not_raw_counts(self):
        x=self.compare()
        self.assertEqual(x["first"]["expected_minutes_per_symbol"],14)
        self.assertEqual(x["second"]["expected_minutes_per_symbol"],15)
        self.assertEqual(x["second"]["observed"],9)
        self.assertEqual(x["second"]["presence_pct"],60.0)
        self.assertEqual(x["presence_change_percentage_points"],4.05)
        self.assertFalse(x["real_trades_allowed"])
        self.assertTrue(x["two_sessions_insufficient_for_predictive_validation"])

    def test_second_complete_bar_grid(self):
        self.f,self.r,self.p=fixture(tuple(range(15)))
        x=self.compare()
        self.assertEqual(x["second"]["complete_symbols"],1)
        self.assertEqual(x["second"]["presence_pct"],100.0)

    def test_second_empty_bars_are_missing_not_zero_return(self):
        self.f,self.r,self.p=fixture(())
        x=self.compare()
        self.assertEqual(x["second"]["observed"],0)
        self.assertEqual(x["second"]["pattern_symbols"],0)
        self.assertTrue(x["missing_iex_minute_cause_unknown"])

    def test_wrong_first_baseline_blocks(self):
        self.first["initial"]["observed_iex_bars"]=95
        with self.assertRaisesRegex(ValueError,"FIRST_REAL_BASELINE_MISMATCH"):
            self.compare()

    def test_duplicate_first_run_id_blocks(self):
        with self.assertRaisesRegex(ValueError,"INVALID_SECOND_RUN_ID"):
            compare(self.first,self.f,self.r,self.p,FIRST_ID)

    def test_tampered_second_t0_blocks(self):
        self.f["candidates"]=["AAPL"]
        with self.assertRaises(ValueError):
            self.compare()

    def test_tampered_second_bar_count_blocks(self):
        self.p["rows"][0]["observed_minutes"]=8
        with self.assertRaisesRegex(ValueError,"SECOND_REVIEW_COUNT_MISMATCH"):
            self.compare()

    def test_fake_timestamp_grid_blocks(self):
        self.p["rows"][0]["missing_iex_bar_start_utc"][0]=self.p["rows"][0]["observed_bar_start_utc"][0]
        with self.assertRaisesRegex(ValueError,"INCONSISTENT_TIMESTAMP_GRID"):
            self.compare()

    def test_http_evidence_required(self):
        self.p["api_fetch"]["captured"]=False
        with self.assertRaisesRegex(ValueError,"SECOND_HTTP_EVIDENCE_MISSING"):
            self.compare()

    def test_missing_http_terminal_blocks(self):
        self.p["api_fetch"]["final_page_token_absent"]=False
        with self.assertRaisesRegex(ValueError,"SECOND_HTTP_INCOMPLETE"):
            self.compare()

    def test_fake_gap_cause_blocks(self):
        self.p["rows"][0]["missing_cause"]="PROVEN_API_ERROR"
        with self.assertRaisesRegex(ValueError,"UNJUSTIFIED_GAP_CAUSE"):
            self.compare()

    def test_missing_iex_not_full_market(self):
        x=self.compare()
        self.assertTrue(x["not_full_us_market_coverage"])
        self.assertTrue(x["not_evidence_of_improved_api_or_prediction_accuracy"])

if __name__=="__main__":
    unittest.main()
