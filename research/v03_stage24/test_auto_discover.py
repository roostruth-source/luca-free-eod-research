"""Offline unit tests; no Alpaca credentials and no live market calls."""
import datetime as dt
import io
import json
import unittest
import urllib.error
from auto_discover import SOURCES, collect, discover, fetch_screener, parse_source

T=dt.datetime(2026,10,27,14,0,tzinfo=dt.timezone.utc)
RESP={
 "active_volume":{"most_actives":[{"symbol":"GPUS","volume":1000},{"symbol":"AAPL","volume":500}]},
 "active_trades":{"most_actives":[{"symbol":"LAES","trade_count":100},{"symbol":"GPUS","trade_count":50}]},
 "movers":{"gainers":[{"symbol":"LAES","percent_change":4.2}],"losers":[{"symbol":"VCIG","percent_change":-3.5}]},
}


class FakeResponse:
    def __init__(self, body):self.body=body
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.body[:n]


class DiscoverTests(unittest.TestCase):
    def test_merge_and_dedup(self):
        out=discover(RESP,T)
        self.assertEqual(out["candidate_count"],4)
        self.assertEqual({x["symbol"] for x in out["candidates"]},{"GPUS","AAPL","LAES","VCIG"})
        self.assertEqual(out["candidates"][0]["symbol"],"GPUS")
        self.assertTrue(all(not x["buy_allowed"] for x in out["candidates"]))
        self.assertFalse(out["all_us_stocks_scanned"])
        self.assertFalse(out["early_spike_predicted"])
        self.assertEqual(out["validation_status"],"NOT_VALIDATED")

    def test_no_manual_symbols_required(self):
        out=discover(RESP,T)
        self.assertTrue(out["missing_symbol_manual_input"])

    def test_afterhours_stale_not_claimed_live(self):
        out=discover(RESP,T)
        self.assertEqual(out["new_york_session_hint"],"REGULAR_WEEKDAY_NOT_HOLIDAY_VERIFIED")
        self.assertEqual(out["freshness"],"NOT_PROVEN")
        weekend=discover(RESP,dt.datetime(2026,10,31,14,0,tzinfo=dt.timezone.utc))
        self.assertEqual(weekend["new_york_session_hint"],"OUTSIDE_REGULAR_OR_WEEKEND")

    def test_missing_source_rejected(self):
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_SCREENER_SOURCES"):
            discover({"movers":RESP["movers"]},T)

    def test_empty_universe_rejected(self):
        r={"active_volume":{"most_actives":[]},"active_trades":{"most_actives":[]},
           "movers":{"gainers":[],"losers":[]}}
        with self.assertRaisesRegex(ValueError,"EMPTY_SCREENER_UNIVERSE"):
            discover(r,T)

    def test_malformed_symbol_rejected(self):
        r={"most_actives":[{"symbol":"GPUS,FAKE"}]}
        with self.assertRaisesRegex(ValueError,"INVALID_SYMBOL"):
            parse_source("active_volume",r)

    def test_malformed_payload_rejected(self):
        with self.assertRaisesRegex(ValueError,"MISSING_MOVERS"):
            parse_source("movers",{"gainers":[]})

    def test_nonallowlisted_api_path_rejected(self):
        with self.assertRaisesRegex(ValueError,"NON_ALLOWLISTED_API_PATH"):
            fetch_screener("/v2/orders","key","secret")

    def test_get_only_and_credentials_not_in_url(self):
        def opener(req,timeout):
            self.assertEqual(req.get_method(),"GET")
            self.assertTrue(req.full_url.startswith("https://data.alpaca.markets/"))
            self.assertNotIn("SECRET",req.full_url)
            self.assertEqual(timeout,25)
            return FakeResponse(json.dumps(RESP["movers"]).encode())
        self.assertEqual(fetch_screener(SOURCES["movers"],"KEY","SECRET",opener),RESP["movers"])

    def test_permission_denied_fail_closed(self):
        def opener(req,timeout):
            if "movers" in req.full_url:
                raise urllib.error.HTTPError(req.full_url,403,"forbidden",{},None)
            return FakeResponse(json.dumps(RESP["active_volume"]).encode())
        out=collect("key","secret",opener,T)
        self.assertEqual(out["discovery_status"],"UNAVAILABLE")
        self.assertEqual(out["candidate_count"],0)
        self.assertEqual(out["source_status"]["movers"],"HTTP_403")

    def test_rate_limit_fail_closed(self):
        def opener(req,timeout):
            raise urllib.error.HTTPError(req.full_url,429,"rate",{},None)
        out=collect("key","secret",opener,T)
        self.assertEqual(out["discovery_status"],"UNAVAILABLE")
        self.assertEqual(out["candidate_count"],0)

    def test_successful_collection(self):
        def opener(req,timeout):
            key=("movers" if "/movers" in req.full_url else
                 "active_trades" if "by=trades" in req.full_url else "active_volume")
            return FakeResponse(json.dumps(RESP[key]).encode())
        out=collect("key","secret",opener,T)
        self.assertEqual(out["candidate_count"],4)
        self.assertEqual(out["discovery_status"],"COLLECTED_UNVERIFIED")
        self.assertTrue(all(v=="OK" for v in out["source_status"].values()))

    def test_duplicate_symbol_does_not_double_count(self):
        r=dict(RESP)
        r["active_volume"]={"most_actives":[{"symbol":"GPUS"},{"symbol":"GPUS"}]}
        out=discover(r,T)
        self.assertEqual(out["candidate_count"],3)

    def test_invalid_time_rejected(self):
        with self.assertRaisesRegex(ValueError,"RECEIPT_TIMESTAMP_REQUIRED"):
            discover(RESP,dt.datetime(2026,10,27,14,0))


if __name__=="__main__":
    unittest.main()
