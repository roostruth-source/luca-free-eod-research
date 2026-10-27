"""Synthetic offline end-to-end tests: T0 -> GET -> review -> provenance."""
import copy
import datetime as dt
import json
import unittest

from iex_provenance_adapter import fetch_review_with_provenance
from test_prospective_iex_research import T1,make_bar
from test_live_trial_contract import make_synthetic

class FakeResponse:
    def __init__(self,data,status=200):
        self.data=json.dumps(data).encode() if type(data) is dict else data
        self.status=status
    def __enter__(self):return self
    def __exit__(self,*a):return False
    def read(self,n=-1):return self.data[:n]

def fixture():
    f,_=make_synthetic()
    bars=[make_bar(i,low=1+i*0.01,volume=300 if i==5 else 20)
          for i in range(12)]
    return f,bars

def do(f,opener):
    return fetch_review_with_provenance(f,T1,"key","secret",
                                        T1+dt.timedelta(seconds=1),opener)

class AdapterTests(unittest.TestCase):
    def test_single_page_real_status_and_timestamp_grid(self):
        f,b=fixture()
        def opener(req,timeout):
            self.assertEqual(req.get_method(),"GET")
            self.assertIn("feed=iex",req.full_url)
            self.assertNotIn("/orders",req.full_url)
            return FakeResponse({"bars":{"GPUS":b},"next_page_token":None})
        r,p=do(f,opener)
        self.assertEqual(r["observed_iex_bars"],12)
        self.assertEqual(p["rows"][0]["observed_minutes"],12)
        self.assertEqual(len(p["rows"][0]["missing_iex_bar_start_utc"]),3)
        self.assertEqual(p["api_fetch"]["page_count"],1)
        self.assertTrue(p["api_fetch"]["captured"])
        self.assertFalse(p["real_trades_allowed"])

    def test_two_pages_preserves_all_original_bars(self):
        f,b=fixture()
        calls=[]
        def opener(req,timeout):
            calls.append(req.full_url)
            if len(calls)==1:
                return FakeResponse({"bars":{"GPUS":b[:6]},"next_page_token":"p2"})
            return FakeResponse({"bars":{"GPUS":b[6:]},"next_page_token":None})
        r,p=do(f,opener)
        self.assertEqual(len(calls),2)
        self.assertIn("page_token=p2",calls[1])
        self.assertEqual(r["observed_iex_bars"],12)
        self.assertEqual(p["api_fetch"]["page_count"],2)

    def test_empty_bars_are_unknown_not_http_failure(self):
        f,_=fixture()
        r,p=do(f,lambda req,timeout:FakeResponse({"bars":{},"next_page_token":None}))
        self.assertEqual(r["observed_iex_bars"],0)
        self.assertEqual(p["rows"][0]["observed_minutes"],0)
        self.assertTrue(p["api_fetch"]["all_pages_successful"])
        self.assertTrue(p["missing_iex_bar_cause_unknown"])

    def test_http_429_blocks_without_success_artifact(self):
        f,b=fixture()
        with self.assertRaisesRegex(ValueError,"UNVERIFIED_HTTP_STATUS"):
            do(f,lambda req,timeout:FakeResponse({"bars":{"GPUS":b},"next_page_token":None},429))

    def test_missing_status_blocks_without_fake_success(self):
        f,b=fixture()
        class NoStatus(FakeResponse):
            def __init__(self,obj):
                super().__init__(obj)
                del self.status
        with self.assertRaisesRegex(ValueError,"UNVERIFIED_HTTP_STATUS"):
            do(f,lambda req,timeout:NoStatus({"bars":{"GPUS":b},"next_page_token":None}))

    def test_missing_page_token_in_middle_fails_closed(self):
        f,b=fixture()
        with self.assertRaisesRegex(ValueError,"BAD_PAGINATION"):
            do(f,lambda req,timeout:FakeResponse({"bars":{"GPUS":b[:6]},"next_page_token":""}))

    def test_duplicate_page_token_fails_closed(self):
        f,b=fixture()
        calls=[]
        def opener(req,timeout):
            calls.append(1)
            items=b[:6] if len(calls)==1 else b[6:]
            return FakeResponse({"bars":{"GPUS":items},"next_page_token":"same"})
        with self.assertRaisesRegex(ValueError,"BAD_PAGINATION"):
            do(f,opener)

    def test_duplicate_bar_across_pages_blocks(self):
        f,b=fixture()
        calls=[]
        def opener(req,timeout):
            calls.append(1)
            if len(calls)==1:
                return FakeResponse({"bars":{"GPUS":b[:6]},"next_page_token":"p2"})
            return FakeResponse({"bars":{"GPUS":b[:1]},"next_page_token":None})
        with self.assertRaisesRegex(ValueError,"DUPLICATE_BAR"):
            do(f,opener)

    def test_pre_t0_bar_blocks(self):
        f,b=fixture()
        b[0]["t"]=f["selected_at_utc"]
        with self.assertRaises(ValueError):
            do(f,lambda req,timeout:FakeResponse({"bars":{"GPUS":b},"next_page_token":None}))

    def test_tampered_frozen_universe_blocks_before_http(self):
        f,b=fixture()
        f["candidates"]=["AAPL"]
        def opener(req,timeout):
            raise AssertionError("NO_API_ALLOWED")
        with self.assertRaisesRegex(ValueError,"FROZEN_HASH_MISMATCH"):
            do(f,opener)

    def test_unsafe_grade_remains_d(self):
        f,b=fixture()
        r,p=do(f,lambda req,timeout:FakeResponse({"bars":{"GPUS":b},"next_page_token":None}))
        self.assertEqual(r["results"][0]["grade"],"D")
        self.assertFalse(r["results"][0]["buy_allowed"])
        self.assertEqual(p["sec_status"],"SEC_UNVERIFIED")

    def test_no_raw_price_or_secret_in_evidence(self):
        f,b=fixture()
        r,p=do(f,lambda req,timeout:FakeResponse({"bars":{"GPUS":b},"next_page_token":None}))
        serialized=json.dumps(p)
        self.assertNotIn("secret",serialized)
        self.assertNotIn('"o":',serialized)
        self.assertNotIn('"v":',serialized)
        self.assertNotIn("1.5",serialized)

if __name__=="__main__":
    unittest.main()
