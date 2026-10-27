"""Offline-only tests of the isolated future review path; no network calls."""
import copy
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from future_iex_review import review_future_session
from test_live_trial_contract import make_synthetic
from test_prospective_iex_research import T1,make_bar


class Response:
    status=200
    def __init__(self,data):
        self.data=json.dumps(data).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.data[:n]


class FutureReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.frozen,_=make_synthetic()
        (self.root/"frozen_t0.json").write_text(json.dumps(self.frozen),encoding="utf8")
        self.bars=[make_bar(i,low=1+i*0.01,
                            volume=300 if i==5 else 20) for i in range(12)]
        self.env=patch.dict(os.environ,{"ALPACA_KEY":"test-key","ALPACA_SECRET":"test-secret"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def opener(self,req,timeout):
        self.assertEqual(req.get_method(),"GET")
        self.assertIn("feed=iex",req.full_url)
        return Response({"bars":{"GPUS":self.bars},"next_page_token":None})

    def run_future(self,opener=None):
        with patch("iex_provenance_adapter.dt.datetime") as clock:
            clock.now.return_value=T1+dt.timedelta(seconds=1)
            return review_future_session(self.root,T1,opener or self.opener)

    def test_writes_both_original_schema_and_timestamp_evidence(self):
        result,evidence=self.run_future()
        old=json.loads((self.root/"forward_review.json").read_text())
        extra=json.loads((self.root/"iex_timestamp_provenance.json").read_text())
        self.assertEqual(old,result)
        self.assertEqual(extra,evidence)
        self.assertEqual(old["schema"],"LUCA_V03_PROSPECTIVE_IEX_REVIEW_V1")
        self.assertEqual(extra["schema"],"LUCA_V03_IEX_TIMESTAMP_PROVENANCE_V1")
        self.assertEqual(extra["api_fetch"]["page_count"],1)
        self.assertEqual(extra["rows"][0]["observed_minutes"],12)
        self.assertEqual(len(extra["rows"][0]["missing_iex_bar_start_utc"]),3)
        self.assertEqual(old["results"][0]["grade"],"D")
        self.assertFalse(old["real_trades_allowed"])
        self.assertFalse(extra["real_trades_allowed"])
        self.assertEqual(json.loads((self.root/"frozen_t0.json").read_text()),self.frozen)

    def test_refuses_repeat_without_new_http_request(self):
        self.run_future()
        def no_http(req,timeout):raise AssertionError("DUPLICATE_HTTP_CALL")
        with self.assertRaisesRegex(FileExistsError,"REVIEW_ALREADY_ARCHIVED"):
            self.run_future(no_http)

    def test_refuses_existing_original(self):
        (self.root/"forward_review.json").write_text("{}")
        with self.assertRaises(FileExistsError):
            self.run_future()

    def test_refuses_existing_provenance(self):
        (self.root/"iex_timestamp_provenance.json").write_text("{}")
        with self.assertRaises(FileExistsError):
            self.run_future()

    def test_bad_frozen_hash_blocks_before_http(self):
        frozen=copy.deepcopy(self.frozen)
        frozen["candidates"]=["AAPL"]
        (self.root/"frozen_t0.json").write_text(json.dumps(frozen))
        with self.assertRaisesRegex(ValueError,"FROZEN_HASH_MISMATCH"):
            self.run_future(lambda req,timeout: self.fail("HTTP SHOULD NOT RUN"))

    def test_api_failure_leaves_no_partial_artifact(self):
        def failed(req,timeout):return Response({"bars":{"GPUS":self.bars},"next_page_token":"invalid"})
        with self.assertRaises(ValueError):
            self.run_future(failed)
        self.assertFalse((self.root/"forward_review.json").exists())
        self.assertFalse((self.root/"iex_timestamp_provenance.json").exists())

    def test_empty_iex_is_not_zero_return_or_signal(self):
        result,evidence=self.run_future(lambda req,timeout:Response(
            {"bars":{},"next_page_token":None}))
        self.assertEqual(result["observed_iex_bars"],0)
        self.assertEqual(result["forward_pattern_symbols"],0)
        self.assertTrue(evidence["missing_iex_bar_cause_unknown"])
        self.assertTrue(evidence["api_fetch"]["all_pages_successful"])

    def test_missing_credentials_blocks(self):
        with patch.dict(os.environ,{"ALPACA_KEY":"","ALPACA_SECRET":""}):
            with self.assertRaisesRegex(ValueError,"MISSING_READONLY_DATA_CREDENTIALS"):
                self.run_future()

    def test_before_forward_window_blocks(self):
        with self.assertRaisesRegex(ValueError,"WRONG_FORWARD_OBSERVATION_INTERVAL"):
            review_future_session(self.root,self.frozen_time())

    def frozen_time(self):
        return dt.datetime.fromisoformat(self.frozen["selected_at_utc"])

    def test_does_not_create_any_other_file(self):
        self.run_future()
        self.assertEqual(sorted(p.name for p in self.root.iterdir()),[
            "forward_review.json","frozen_t0.json","iex_timestamp_provenance.json"])

if __name__=="__main__":
    unittest.main()
