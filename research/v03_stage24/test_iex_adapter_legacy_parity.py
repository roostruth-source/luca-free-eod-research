"""Strict offline parity contract: optional provenance MUST NOT change legacy review.

Synthetic IEX bars only. Never fetches live market data or changes production.
"""
import copy
import datetime as dt
import json
import unittest

from prospective_iex_research import fetch_after_freeze,review,digest_frozen
from iex_provenance_adapter import fetch_review_with_provenance
from test_prospective_iex_research import T1,make_bar
from test_live_trial_contract import make_synthetic

class Response:
    status=200
    def __init__(self,data):self.payload=json.dumps(data).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.payload[:n]


def one_page(data):
    return lambda req,timeout:Response({"bars":data,"next_page_token":None})


def two_pages(data):
    calls=[]
    def opener(req,timeout):
        calls.append(req.full_url)
        if len(calls)==1:
            return Response({"bars":{s:b[:len(b)//2] for s,b in data.items()},
                             "next_page_token":"p2"})
        return Response({"bars":{s:b[len(b)//2:] for s,b in data.items()},
                         "next_page_token":None})
    return opener,calls


def compare(f,old_opener,new_opener):
    before=copy.deepcopy(f)
    original=review(f,fetch_after_freeze(f,T1,"key","secret",old_opener),T1)
    new,provenance=fetch_review_with_provenance(
        f,T1,"key","secret",T1+dt.timedelta(seconds=1),new_opener)
    if f!=before:
        raise AssertionError("FROZEN_T0_MUTATED")
    return original,new,provenance


class LegacyParityTests(unittest.TestCase):
    def setUp(self):
        self.frozen,_=make_synthetic()

    def assert_parity(self,old,new,provenance):
        self.assertEqual(old,new,"ORIGINAL_REVIEW_CHANGED")
        self.assertEqual(old["schema"],"LUCA_V03_PROSPECTIVE_IEX_REVIEW_V1")
        self.assertEqual(old["results"][0]["grade"],"D")
        self.assertFalse(old["results"][0]["buy_allowed"])
        self.assertFalse(provenance["real_trades_allowed"])
        self.assertEqual(provenance["frozen_t0_sha256"],self.frozen["sha256"])

    def test_empty_data_parity(self):
        a,b,p=compare(self.frozen,one_page({}),one_page({}))
        self.assert_parity(a,b,p)
        self.assertEqual(a["forward_pattern_symbols"],0)
        self.assertEqual(p["rows"][0]["observed_minutes"],0)

    def test_sparse_bars_parity(self):
        data={"GPUS":[make_bar(i) for i in [0,2,4,8]]}
        a,b,p=compare(self.frozen,one_page(data),one_page(data))
        self.assert_parity(a,b,p)
        self.assertEqual(a["observed_iex_bars"],4)
        self.assertEqual(len(p["rows"][0]["missing_iex_bar_start_utc"]),11)

    def test_complete_15_minutes_parity(self):
        data={"GPUS":[make_bar(i) for i in range(15)]}
        a,b,p=compare(self.frozen,one_page(data),one_page(data))
        self.assert_parity(a,b,p)
        self.assertTrue(p["rows"][0]["complete"])

    def test_actual_pattern_detection_parity(self):
        data={"GPUS":[make_bar(i,low=1+i*0.01,
                               volume=300 if i==5 else 20) for i in range(6)]}
        a,b,p=compare(self.frozen,one_page(data),one_page(data))
        self.assert_parity(a,b,p)
        self.assertEqual(a["forward_pattern_symbols"],1)
        self.assertEqual(a["results"][0]["grade"],"D")
        self.assertFalse(p["prediction_accuracy_verified"])

    def test_two_page_data_parity(self):
        data={"GPUS":[make_bar(i) for i in range(15)]}
        old,old_calls=two_pages(data)
        new,new_calls=two_pages(data)
        a,b,p=compare(self.frozen,old,new)
        self.assert_parity(a,b,p)
        self.assertEqual(len(old_calls),2)
        self.assertEqual(len(new_calls),2)
        self.assertEqual(p["api_fetch"]["page_count"],2)

    def test_multi_symbol_parity_and_order(self):
        self.frozen["candidates"]=["GPUS","LAES"]
        self.frozen["candidate_count"]=2
        self.frozen["sha256"]=digest_frozen(self.frozen)
        data={"GPUS":[make_bar(i) for i in [0,1,3]],
              "LAES":[make_bar(i) for i in range(10)]}
        a,b,p=compare(self.frozen,one_page(data),one_page(data))
        self.assert_parity(a,b,p)
        self.assertEqual([r["symbol"] for r in b["results"]],["GPUS","LAES"])
        self.assertEqual([r["symbol"] for r in p["rows"]],["GPUS","LAES"])
        self.assertEqual(a["observed_iex_bars"],13)

    def test_original_and_adapter_both_block_pre_t0(self):
        data={"GPUS":[make_bar(0)]}
        data["GPUS"][0]["t"]=self.frozen["selected_at_utc"]
        with self.assertRaises(ValueError):
            fetch_after_freeze(self.frozen,T1,"key","secret",one_page(data))
        with self.assertRaises(ValueError):
            fetch_review_with_provenance(self.frozen,T1,"key","secret",
                                         T1+dt.timedelta(seconds=1),one_page(data))

    def test_original_and_adapter_both_block_duplicate_bar(self):
        item=make_bar(0)
        data={"GPUS":[item,copy.deepcopy(item)]}
        with self.assertRaisesRegex(ValueError,"DUPLICATE_BAR"):
            fetch_after_freeze(self.frozen,T1,"key","secret",one_page(data))
        with self.assertRaisesRegex(ValueError,"DUPLICATE_BAR"):
            fetch_review_with_provenance(self.frozen,T1,"key","secret",
                                         T1+dt.timedelta(seconds=1),one_page(data))

    def test_original_and_adapter_both_block_tampered_freeze(self):
        self.frozen["candidates"]=["AAPL"]
        data={"GPUS":[make_bar(0)]}
        with self.assertRaisesRegex(ValueError,"FROZEN_HASH_MISMATCH"):
            fetch_after_freeze(self.frozen,T1,"key","secret",one_page(data))
        with self.assertRaisesRegex(ValueError,"FROZEN_HASH_MISMATCH"):
            fetch_review_with_provenance(self.frozen,T1,"key","secret",
                                         T1+dt.timedelta(seconds=1),one_page(data))

    def test_recorded_time_must_follow_review(self):
        data={"GPUS":[make_bar(0)]}
        with self.assertRaisesRegex(ValueError,"INVALID_RECORDING_TIME"):
            fetch_review_with_provenance(self.frozen,T1,"key","secret",
                                         T1-dt.timedelta(seconds=1),one_page(data))

if __name__=="__main__":
    unittest.main()
