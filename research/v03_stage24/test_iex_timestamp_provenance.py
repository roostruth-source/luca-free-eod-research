"""Synthetic-only tests of future IEX timestamp capture, never market results."""
import copy
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from iex_timestamp_provenance import build_minute_provenance,write_new
from test_prospective_iex_research import make_bar,T1
from test_live_trial_contract import make_synthetic

UTC=dt.timezone.utc

def pair():
    frozen,review=make_synthetic()
    bars={"GPUS":[make_bar(i,low=1.0+i*0.01,volume=300 if i==5 else 20)
                  for i in range(12)]}
    return frozen,review,bars

def get(f,r,b,api=None):
    return build_minute_provenance(f,r,b,T1+dt.timedelta(seconds=2),api)

class TimestampProvenanceTests(unittest.TestCase):
    def test_exact_timestamp_grid_not_fake_backfill(self):
        f,r,b=pair();x=get(f,r,b)
        row=x["rows"][0]
        self.assertEqual(row["observed_minutes"],12)
        self.assertEqual(len(row["missing_iex_bar_start_utc"]),3)
        self.assertEqual(x["expected_minutes_per_symbol"],15)
        self.assertFalse(x["api_fetch"]["captured"])
        self.assertTrue(x["missing_iex_bar_cause_unknown"])
        self.assertFalse(x["real_trades_allowed"])

    def test_explicit_successful_http_page_evidence(self):
        f,r,b=pair()
        x=get(f,r,b,{"get_only":True,"http_statuses":[200,200],
                     "final_page_token_absent":True})
        self.assertEqual(x["api_fetch"]["page_count"],2)
        self.assertTrue(x["api_fetch"]["all_pages_successful"])
        self.assertTrue(x["missing_iex_bar_cause_unknown"])

    def test_no_invented_http_evidence(self):
        f,r,b=pair();x=get(f,r,b)
        self.assertIsNone(x["api_fetch"]["all_pages_successful"])

    def test_bad_http_or_partial_pages_blocked(self):
        f,r,b=pair()
        for api in ({"get_only":True,"http_statuses":[200,429],"final_page_token_absent":True},
                    {"get_only":True,"http_statuses":[200],"final_page_token_absent":False},
                    {"get_only":False,"http_statuses":[200],"final_page_token_absent":True}):
            with self.subTest(api=api),self.assertRaisesRegex(ValueError,"INCOMPLETE_API_FETCH_EVIDENCE"):
                get(f,r,b,api)

    def test_changed_bar_count_blocks(self):
        f,r,b=pair();b["GPUS"].pop()
        with self.assertRaisesRegex(ValueError,"REVIEW_BAR_COUNT_MISMATCH"):
            get(f,r,b)

    def test_duplicate_bar_blocks(self):
        f,r,b=pair();b["GPUS"].append(copy.deepcopy(b["GPUS"][0]))
        with self.assertRaisesRegex(ValueError,"DUPLICATE_OR_NONMINUTE_BAR"):
            get(f,r,b)

    def test_pre_t0_bar_blocks(self):
        f,r,b=pair();b["GPUS"][0]["t"]=f["selected_at_utc"]
        with self.assertRaises(ValueError):
            get(f,r,b)

    def test_wrong_symbol_blocks(self):
        f,r,b=pair();b["AAPL"]=b.pop("GPUS")
        with self.assertRaisesRegex(ValueError,"BAR_UNIVERSE_DRIFT"):
            get(f,r,b)

    def test_tampered_t0_hash_blocks(self):
        f,r,b=pair();f["candidates"]=["AAPL"]
        with self.assertRaises(ValueError):
            get(f,r,b)

    def test_unsafe_review_grade_blocks(self):
        f,r,b=pair();r["results"][0]["grade"]="A"
        with self.assertRaisesRegex(ValueError,"UNSAFE_RESEARCH_GRADE"):
            get(f,r,b)

    def test_old_recording_time_blocks(self):
        f,r,b=pair()
        with self.assertRaisesRegex(ValueError,"INVALID_RECORDING_TIME"):
            build_minute_provenance(f,r,b,T1-dt.timedelta(seconds=2))

    def test_immutable_write(self):
        f,r,b=pair();x=get(f,r,b)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"timestamp.json"
            write_new(path,x)
            self.assertTrue(path.is_file())
            with self.assertRaises(FileExistsError):
                write_new(path,x)

    def test_no_trading_or_ohlcv_in_export(self):
        f,r,b=pair();x=get(f,r,b)
        self.assertFalse(x["raw_ohlcv_archived"])
        self.assertFalse(x["prediction_accuracy_verified"])
        self.assertEqual(x["sec_status"],"SEC_UNVERIFIED")
        self.assertNotIn("c",x["rows"][0])
        self.assertNotIn("price",x["rows"][0])

if __name__=="__main__":
    unittest.main()
