"""Offline SEC mapping, as-of timestamps, and fail-closed auto-triage tests."""
import datetime as dt
import json
import unittest
from sec_auto_triage import (TICKERS_URL, SUBMISSIONS_ROOT, get_json,
                             ticker_cik_map, recent_filings, triage)

T=dt.datetime(2026,10,27,7,0,tzinfo=dt.timezone.utc)
ENRICH={
    "schema":"LUCA_V03_IEX_CANDIDATE_ENRICHMENT_V1",
    "validation_status":"NOT_VALIDATED","real_trades_allowed":False,
    "collected_at_utc":T.isoformat(),
    "rows":[{"symbol":"GPUS","price_band_0_20_to_20":True,
             "iex_last_trade_price":1.25,"research_status":"PENDING_STALE_OR_MISSING",
             "buy_allowed":False},
            {"symbol":"AAPL","price_band_0_20_to_20":False,
             "iex_last_trade_price":300.0,"research_status":"PENDING_STALE_OR_MISSING",
             "buy_allowed":False},
            {"symbol":"LAES","price_band_0_20_to_20":True,
             "iex_last_trade_price":1.5,"research_status":"PENDING_STALE_OR_MISSING",
             "buy_allowed":False}]
}
SUB={"cik":123,"filings":{"recent":{
    "form":["8-K","424B5","10-Q","S-3"],
    "accessionNumber":["0000000123-26-000001","0000000123-26-000002",
                       "0000000123-26-000003","0000000123-26-000004"],
    "acceptanceDateTime":["2026-10-26T14:00:00Z","2026-10-27T08:00:00Z",
                          "2026-10-27T06:00:00Z","2026-09-01T00:00:00Z"],
    "filingDate":["2026-10-26","2026-10-27","2026-10-27","2026-09-01"],
    "primaryDocument":["filing.htm","prospectus.htm","10q.htm","s3.htm"]
}}}


class FakeResponse:
    def __init__(self,body):self.body=body
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.body[:n]


class SECTriageTests(unittest.TestCase):
    def test_asof_excludes_future_filing_and_older_than_30_days(self):
        r=recent_filings(SUB,T)
        self.assertEqual(len(r["review_filings"]),1)
        self.assertEqual(r["review_filings"][0]["form"],"8-K")
        self.assertIn("000000012326000001",r["review_filings"][0]["url"])
        self.assertEqual(r["review_filings"][0]["accepted_at_utc"],"2026-10-26T14:00:00+00:00")

    def test_no_buy_or_sec_clearance(self):
        r=triage(ENRICH,{"GPUS":123,"LAES":124},{"GPUS":SUB},T)
        self.assertEqual(r["price_band_watchlist"],2)
        self.assertEqual(r["cik_mapped"],2)
        self.assertEqual(r["submissions_available"],1)
        self.assertEqual(r["recent_review_forms"],1)
        self.assertFalse(r["market_cap_verified"])
        self.assertFalse(r["float_verified"])
        self.assertTrue(all(not x["buy_allowed"] and not x["sec_clearance"] for x in r["rows"]))
        self.assertEqual(r["rows"][1]["sec_status"],"SEC_SUBMISSIONS_UNAVAILABLE")

    def test_unknown_cik_stays_blocked(self):
        r=triage(ENRICH,{"GPUS":123},{"GPUS":SUB},T)
        self.assertEqual(r["rows"][1]["sec_status"],"CIK_NOT_MAPPED")
        self.assertEqual(r["rows"][1]["grade"],"D")

    def test_wrong_cik_not_treated_as_evidence(self):
        r=triage(ENRICH,{"GPUS":555},{"GPUS":SUB},T)
        self.assertEqual(r["rows"][0]["sec_status"],"SEC_DATA_INVALID")

    def test_asof_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,"ASOF_ENRICHMENT_MISMATCH"):
            triage(ENRICH,{}, {},T+dt.timedelta(minutes=1))

    def test_trade_permission_override_rejected(self):
        e=json.loads(json.dumps(ENRICH));e["real_trades_allowed"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_ENRICHMENT"):
            triage(e,{}, {},T)

    def test_approved_candidate_override_rejected(self):
        e=json.loads(json.dumps(ENRICH));e["rows"][0]["buy_allowed"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_CANDIDATE"):
            triage(e,{}, {},T)

    def test_future_filing_not_included_even_same_day(self):
        sub=json.loads(json.dumps(SUB))
        sub["filings"]["recent"]["acceptanceDateTime"][0]="2026-10-27T07:01:00Z"
        r=recent_filings(sub,T)
        self.assertEqual(r["review_filings"],[])

    def test_invalid_acceptance_timestamp_not_silently_cleared(self):
        sub=json.loads(json.dumps(SUB))
        sub["filings"]["recent"]["acceptanceDateTime"][0]="2026-10-26T14:00:00"
        r=triage(ENRICH,{"GPUS":123},{"GPUS":sub},T)
        self.assertEqual(r["rows"][0]["sec_status"],"SEC_TIMESTAMPS_INCOMPLETE")

    def test_invalid_accession_fails_closed(self):
        sub=json.loads(json.dumps(SUB))
        sub["filings"]["recent"]["accessionNumber"][0]="../../etc/passwd"
        r=triage(ENRICH,{"GPUS":123},{"GPUS":sub},T)
        self.assertEqual(r["rows"][0]["sec_status"],"SEC_DATA_INVALID")

    def test_mapping_parser(self):
        r=ticker_cik_map({"0":{"ticker":"GPUS","cik_str":123},
                          "1":{"ticker":"LAES","cik_str":456}})
        self.assertEqual(r,{"GPUS":123,"LAES":456})

    def test_duplicate_conflicting_cik_rejected(self):
        with self.assertRaisesRegex(ValueError,"AMBIGUOUS_CIK_MAPPING"):
            ticker_cik_map({"0":{"ticker":"GPUS","cik_str":123},
                            "1":{"ticker":"GPUS","cik_str":456}})

    def test_sec_url_allowlist_blocks_orders(self):
        with self.assertRaisesRegex(ValueError,"SEC_URL_NOT_ALLOWLISTED"):
            get_json("https://data.alpaca.markets/v2/orders")

    def test_sec_get_only(self):
        def opener(req,timeout):
            self.assertEqual(req.get_method(),"GET")
            self.assertEqual(req.full_url,TICKERS_URL)
            self.assertIn("LUCA-Research",req.get_header("User-agent"))
            return FakeResponse(json.dumps({"0":{"ticker":"GPUS","cik_str":123}}).encode())
        self.assertEqual(get_json(TICKERS_URL,opener)["0"]["ticker"],"GPUS")

    def test_recent_list_length_mismatch(self):
        sub=json.loads(json.dumps(SUB))
        sub["filings"]["recent"]["form"].append("8-K")
        with self.assertRaisesRegex(ValueError,"FILINGS_LENGTH_MISMATCH"):
            recent_filings(sub,T)


if __name__=="__main__":
    unittest.main()
