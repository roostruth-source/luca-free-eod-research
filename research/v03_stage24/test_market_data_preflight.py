"""Offline mocks; no real Alpaca calls or prospective trading."""
import datetime as dt
import io
import json
import unittest
import urllib.error
from market_data_preflight import audit,bars_access,UTC

NOW=dt.datetime(2026,10,27,11,0,tzinfo=UTC)

def discover(key,secret,now=None):
    return {"discovery_status":"COLLECTED_UNVERIFIED","candidate_count":1,
            "candidates":[{"symbol":"GPUS"}]}

def snap(symbols,key,secret):
    assert symbols==["GPUS"]
    return {"GPUS":{"latestTrade":{"p":1.0}}}

def bars(symbol,key,secret,now):
    assert symbol=="GPUS"
    return {"status":"GET_OK_SCHEMA_ONLY","bars_returned":0}

class Resp:
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,size):return json.dumps(self.data).encode()

class PreflightTests(unittest.TestCase):
    def test_all_endpoints_accessible_not_forward_signal(self):
        r=audit("k","s",NOW,discover,snap,bars)
        self.assertEqual(r["ready_for_later_t0"],"DATA_ENDPOINTS_ACCESSIBLE_ONLY")
        self.assertFalse(r["live_t0_test_executed"])
        self.assertFalse(r["real_trades_allowed"])
        self.assertEqual(r["actual_forward_results"],0)

    def test_zero_historical_bars_does_not_block_schema(self):
        r=audit("k","s",NOW,discover,snap,bars)
        self.assertEqual(r["historical_bars_returned"],0)
        self.assertEqual(r["iex_1min_bars_status"],"GET_OK_SCHEMA_ONLY")

    def test_no_keys_block(self):
        r=audit("","",NOW,discover,snap,bars)
        self.assertEqual(r["screener_status"],"NO_KEYS")
        self.assertEqual(r["ready_for_later_t0"],"UNCONFIRMED")

    def test_screener_403_blocks(self):
        def bad(k,s,now=None):
            return {"discovery_status":"UNAVAILABLE","source_status":{"movers":"HTTP_403"}}
        r=audit("k","s",NOW,bad,snap,bars)
        self.assertEqual(r["screener_status"],"UNAVAILABLE")
        self.assertEqual(r["iex_snapshot_status"],"NOT_TESTED")

    def test_snapshot_403_blocks(self):
        def bad(*a):raise urllib.error.HTTPError("url",403,"Forbidden",{},None)
        r=audit("k","s",NOW,discover,bad,bars)
        self.assertEqual(r["iex_snapshot_status"],"HTTP_403")
        self.assertEqual(r["ready_for_later_t0"],"UNCONFIRMED")

    def test_bar_403_blocks(self):
        def bad(*a):raise urllib.error.HTTPError("url",403,"Forbidden",{},None)
        r=audit("k","s",NOW,discover,snap,bad)
        self.assertEqual(r["iex_1min_bars_status"],"HTTP_403")

    def test_missing_snapshot_blocks(self):
        r=audit("k","s",NOW,discover,lambda *a:{},bars)
        self.assertEqual(r["iex_snapshot_status"],"ERROR_ValueError")

    def test_bad_clock_rejected(self):
        with self.assertRaisesRegex(ValueError,"AWARE_TIME_REQUIRED"):
            audit("k","s",dt.datetime(2026,10,27,11),discover,snap,bars)

    def test_bars_probe_get_only_iex(self):
        seen=[]
        def opener(req,timeout):
            seen.append(req)
            return Resp({"bars":{"GPUS":[]},"next_page_token":None})
        out=bars_access("GPUS","k","s",NOW,opener)
        self.assertEqual(out["status"],"GET_OK_SCHEMA_ONLY")
        self.assertEqual(seen[0].get_method(),"GET")
        self.assertIn("feed=iex",seen[0].full_url)
        self.assertNotIn("orders",seen[0].full_url)
        self.assertNotIn("k",json.dumps(out))

    def test_bars_probe_rejects_other_symbol(self):
        def opener(req,timeout):return Resp({"bars":{"TSLA":[]}})
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_SYMBOL"):
            bars_access("GPUS","k","s",NOW,opener)

    def test_bars_probe_rejects_schema(self):
        def opener(req,timeout):return Resp({"wrong":{}})
        with self.assertRaisesRegex(ValueError,"BAD_BAR_SCHEMA"):
            bars_access("GPUS","k","s",NOW,opener)

    def test_bars_probe_rejects_bad_symbol(self):
        with self.assertRaisesRegex(ValueError,"BAD_SYMBOL"):
            bars_access("../evil","k","s",NOW)

if __name__=="__main__":
    unittest.main()
