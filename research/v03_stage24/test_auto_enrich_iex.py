"""No-network tests for candidate price enrichment and stale-data safety."""
import datetime as dt
import io
import json
import unittest
import urllib.error
from auto_enrich_iex import annotate, fetch_iex_snapshots, run, MAX_AGE_SECONDS

T=dt.datetime(2026,10,27,14,0,tzinfo=dt.timezone.utc)
D={
 "schema":"LUCA_V03_AUTODISCOVERY_RESEARCH_V1",
 "discovery_status":"COLLECTED_UNVERIFIED","validation_status":"NOT_VALIDATED",
 "real_trades_allowed":False,
 "candidates":[{"symbol":"GPUS","source_groups":{"active_volume":1}},
               {"symbol":"LAES","source_groups":{"gainers":1}}]
}
S={
 "GPUS":{"latestTrade":{"p":1.5,"t":"2026-10-27T13:59:00Z"},
         "latestQuote":{"bp":1.48,"ap":1.52,"t":"2026-10-27T13:59:00Z"}},
 "LAES":{"latestTrade":{"p":2.1,"t":"2026-10-20T13:59:00Z"},
         "latestQuote":{"bp":2.0,"ap":2.2,"t":"2026-10-20T13:59:00Z"}}
}


class FakeResponse:
    def __init__(self,body):self.body=body
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.body[:n]


class EnrichmentTests(unittest.TestCase):
    def test_freshness_and_spread(self):
        r=annotate(D,S,T)
        by={x["symbol"]:x for x in r["rows"]}
        self.assertEqual(r["discovered_count"],2)
        self.assertEqual(r["priced_count"],2)
        self.assertEqual(r["fresh_iex_watch_count"],1)
        self.assertEqual(by["GPUS"]["research_status"],"WATCH_ONLY_FRESH_IEX")
        self.assertEqual(by["LAES"]["research_status"],"PENDING_STALE_OR_MISSING")
        self.assertEqual(by["GPUS"]["iex_quote_spread_pct"],2.667)
        self.assertFalse(by["GPUS"]["buy_allowed"])
        self.assertFalse(r["market_cap_verified"])
        self.assertFalse(r["float_verified"])
        self.assertEqual(r["validation_status"],"NOT_VALIDATED")

    def test_outside_market_is_not_fresh(self):
        r=annotate(D,S,dt.datetime(2026,10,27,8,0,tzinfo=dt.timezone.utc))
        self.assertEqual(r["fresh_iex_watch_count"],0)

    def test_future_print_rejected_as_stale(self):
        s=json.loads(json.dumps(S));s["GPUS"]["latestTrade"]["t"]="2026-10-27T14:15:00Z"
        r=annotate(D,s,T)
        self.assertEqual(r["fresh_iex_watch_count"],0)

    def test_price_is_not_market_cap(self):
        r=annotate(D,S,T)
        self.assertIsNone(r["rows"][0]["market_cap"])
        self.assertIsNone(r["rows"][0]["float_shares"])

    def test_missing_snapshot_pending(self):
        r=annotate(D,{},T)
        self.assertEqual(r["snapshots_present"],0)
        self.assertEqual(r["fresh_iex_watch_count"],0)

    def test_unverified_discovery_rejected(self):
        d=json.loads(json.dumps(D));d["validation_status"]="VALIDATED"
        with self.assertRaisesRegex(ValueError,"UNSAFE_DISCOVERY"):
            annotate(d,S,T)

    def test_order_flag_rejected(self):
        d=json.loads(json.dumps(D));d["real_trades_allowed"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_DISCOVERY"):
            annotate(d,S,T)

    def test_duplicate_universe_rejected(self):
        d=json.loads(json.dumps(D));d["candidates"].append(d["candidates"][0])
        with self.assertRaisesRegex(ValueError,"INVALID_CANDIDATE_SYMBOLS"):
            annotate(d,S,T)

    def test_unexpected_snapshot_symbol_rejected(self):
        s=json.loads(json.dumps(S));s["TSLA"]={}
        with self.assertRaisesRegex(ValueError,"SNAPSHOT_SYMBOL_NOT_IN_UNIVERSE"):
            annotate(D,s,T)

    def test_bad_iex_batch_rejected(self):
        with self.assertRaisesRegex(ValueError,"INVALID_BATCH"):
            fetch_iex_snapshots(["GPUS","GPUS"],"k","s")

    def test_get_only_feed_iex(self):
        def opener(req,timeout):
            self.assertEqual(req.get_method(),"GET")
            self.assertIn("feed=iex",req.full_url)
            self.assertNotIn("/orders",req.full_url)
            return FakeResponse(json.dumps({"GPUS":S["GPUS"]}).encode())
        self.assertEqual(fetch_iex_snapshots(["GPUS"],"k","s",opener),{"GPUS":S["GPUS"]})

    def test_403_no_fallback_to_sip(self):
        def opener(req,timeout):
            if "/snapshots" in req.full_url:
                self.assertIn("feed=iex",req.full_url)
                raise urllib.error.HTTPError(req.full_url,403,"forbidden",{},None)
            if "most-actives" in req.full_url:
                return FakeResponse(json.dumps({"most_actives":[{"symbol":"GPUS"}]}).encode())
            return FakeResponse(json.dumps({"gainers":[],"losers":[]}).encode())
        r=run("k","s",opener,T)
        self.assertEqual(r["status"],"SNAPSHOTS_UNAVAILABLE")
        self.assertEqual(r["rows"],[])
        self.assertFalse(r["real_trades_allowed"])

    def test_end_to_end_fake_api(self):
        def opener(req,timeout):
            if "/snapshots" in req.full_url:
                return FakeResponse(json.dumps(S).encode())
            if "most-actives" in req.full_url:
                return FakeResponse(json.dumps({"most_actives":[{"symbol":"GPUS"},{"symbol":"LAES"}]}).encode())
            return FakeResponse(json.dumps({"gainers":[{"symbol":"GPUS"}],"losers":[]}).encode())
        r=run("k","s",opener,T)
        self.assertEqual(r["status"],"COLLECTED_UNVERIFIED")
        self.assertEqual(r["discovered_count"],2)
        self.assertEqual(r["fresh_iex_watch_count"],1)


if __name__=="__main__":
    unittest.main()
