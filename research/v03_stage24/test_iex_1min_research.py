"""Research-only offline tests: IEX minute continuity and retrospective bias controls."""
import datetime as dt
import json
import unittest
import urllib.error
from unittest.mock import patch
from zoneinfo import ZoneInfo
from iex_1min_research import (
    latest_completed_session_date,session_window,valid_bar,find_patterns,
    fetch_iex_morning,report,run,
)

UTC=dt.timezone.utc
DAY=dt.date(2026,10,26)
NOW=dt.datetime(2026,10,27,8,30,tzinfo=UTC)
START=dt.datetime(2026,10,26,13,30,tzinfo=UTC)
def sample(minute,low=1.0,volume=10,close=1.5):
    return {"t":(START+dt.timedelta(minutes=minute)).isoformat(),
            "o":close,"h":max(close,low)+0.1,"l":low,"c":close,"v":volume}

def raw_bar(minute,low=1.0,volume=10,close=1.5):
    row=sample(minute,low,volume,close)
    row["t"]=row["t"].replace("+00:00","Z")
    return row

ENRICH={
    "schema":"LUCA_V03_IEX_CANDIDATE_ENRICHMENT_V1",
    "status":"COLLECTED_UNVERIFIED",
    "validation_status":"NOT_VALIDATED","real_trades_allowed":False,
    "collected_at_utc":NOW.isoformat(),
    "price_band_count":1,
    "rows":[{"symbol":"GPUS","price_band_0_20_to_20":True},
            {"symbol":"AAPL","price_band_0_20_to_20":False}],
}

class FakeResponse:
    def __init__(self,body):self.body=body
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.body[:n]


class Tests(unittest.TestCase):
    def test_last_session_previous_day(self):
        self.assertEqual(latest_completed_session_date(NOW),DAY)

    def test_weekend_previous_friday(self):
        t=dt.datetime(2026,11,1,13,tzinfo=UTC)
        self.assertEqual(latest_completed_session_date(t),dt.date(2026,10,30))

    def test_timezone_dst(self):
        a,b=session_window(dt.date(2026,10,26))
        self.assertEqual(a.hour,13) # EDT
        x,y=session_window(dt.date(2026,11,2))
        self.assertEqual(x.hour,14) # EST

    def test_detect_pattern_no_future_bars(self):
        rows=[sample(i,1.0+0.01*i,300 if i==5 else 10,1.5) for i in range(6)]
        out=find_patterns(rows)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["iex_volume_ratio"],30.0)
        self.assertEqual(out[0]["bar_knowable_after_utc"],(START+dt.timedelta(minutes=6)).isoformat())
        self.assertFalse(out[0]["buy_allowed"])

    def test_missing_minute_does_not_fill(self):
        rows=[sample(i,1.0+i*0.01,300 if i==6 else 10) for i in (0,1,2,3,4,6)]
        self.assertEqual(find_patterns(rows),[])

    def test_insufficient_history(self):
        rows=[sample(i,1.0+i*0.01,200) for i in range(5)]
        self.assertEqual(find_patterns(rows),[])

    def test_nonrising_lows_rejected(self):
        rows=[sample(i,1.0,300 if i==5 else 10) for i in range(6)]
        self.assertEqual(find_patterns(rows),[])

    def test_volume_spike_rejected_if_small(self):
        rows=[sample(i,1.0+i*.01,20) for i in range(6)]
        self.assertEqual(find_patterns(rows),[])

    def test_negative_price_change_rejected(self):
        rows=[sample(i,1.0+i*.01,300 if i==5 else 10,1.50-i*.02) for i in range(6)]
        self.assertEqual(find_patterns(rows),[])

    def test_invalid_bar_ohlc_rejected(self):
        a,b=session_window(DAY)
        bar=raw_bar(0);bar["l"]=2.0
        with self.assertRaisesRegex(ValueError,"INVALID_OHLC_RANGE"):
            valid_bar(bar,a,b)

    def test_bar_outside_window_rejected(self):
        a,b=session_window(DAY)
        with self.assertRaisesRegex(ValueError,"BAR_OUTSIDE_WINDOW"):
            valid_bar(raw_bar(181),a,b)

    def test_get_iex_and_no_orders(self):
        def opener(req,timeout):
            self.assertEqual(req.get_method(),"GET")
            self.assertIn("feed=iex",req.full_url)
            self.assertNotIn("feed=sip",req.full_url)
            self.assertIn("timeframe=1Min",req.full_url)
            self.assertIn("sort=asc",req.full_url)
            self.assertNotIn("/orders",req.full_url)
            return FakeResponse(json.dumps({"bars":{"GPUS":[raw_bar(0)]},
                                            "next_page_token":None}).encode())
        res=fetch_iex_morning(["GPUS"],DAY,"key","secret",opener)
        self.assertEqual(len(res["GPUS"]),1)

    def test_duplicate_bar_rejected(self):
        def opener(req,timeout):
            return FakeResponse(json.dumps({"bars":{"GPUS":[raw_bar(0),raw_bar(0)]}}).encode())
        with self.assertRaisesRegex(ValueError,"DUPLICATE_MINUTE"):
            fetch_iex_morning(["GPUS"],DAY,"key","secret",opener)

    def test_unexpected_symbol_rejected(self):
        def opener(req,timeout):
            return FakeResponse(json.dumps({"bars":{"TSLA":[raw_bar(0)]}}).encode())
        with self.assertRaisesRegex(ValueError,"UNEXPECTED_SYMBOLS"):
            fetch_iex_morning(["GPUS"],DAY,"key","secret",opener)

    def test_biased_retrospective_is_never_approved(self):
        bars={"GPUS":[sample(i,1.0+0.01*i,300 if i==5 else 10) for i in range(6)]}
        out=report(ENRICH,bars,DAY,NOW)
        self.assertTrue(out["lookahead_selection_bias"])
        self.assertTrue(out["not_valid_prospective_backtest"])
        self.assertTrue(out["not_live_scanning"])
        self.assertEqual(out["retrospective_pattern_symbols"],1)
        self.assertFalse(out["rows"][0]["buy_allowed"])
        self.assertEqual(out["rows"][0]["grade"],"D")
        self.assertFalse(out["prediction_accuracy_verified"])

    def test_unfinished_window_rejected(self):
        bars={"GPUS":[sample(i) for i in range(6)]}
        with self.assertRaisesRegex(ValueError,"HISTORICAL_WINDOW_NOT_COMPLETED"):
            report(ENRICH,bars,DAY,dt.datetime(2026,10,26,14,0,tzinfo=UTC))

    def test_unsafe_enrichment_rejected(self):
        e=json.loads(json.dumps(ENRICH));e["real_trades_allowed"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_ENRICHMENT"):
            report(e,{"GPUS":[]},DAY,NOW)

    def test_http403_does_not_grant_buy(self):
        def blocked(*args,**kwargs):
            raise urllib.error.HTTPError("https://data.alpaca.markets/",403,"forbidden",{},None)
        with patch("iex_1min_research.enrich_run",return_value=ENRICH),patch(
                "iex_1min_research.fetch_iex_morning",side_effect=blocked):
            out=run("k","s",now=NOW)
        self.assertEqual(out["status"],"BAR_HTTP_403")
        self.assertEqual(out["observed_bars"],0)
        self.assertFalse(out["real_trades_allowed"])

    def test_end_to_end_stub(self):
        bars={"GPUS":[sample(i,1.0+0.01*i,300 if i==5 else 10) for i in range(6)]}
        with patch("iex_1min_research.enrich_run",return_value=ENRICH),patch(
                "iex_1min_research.fetch_iex_morning",return_value=bars):
            out=run("k","s",now=NOW)
        self.assertEqual(out["status"],"RETROSPECTIVE_RESEARCH_ONLY")
        self.assertEqual(out["observed_bars"],6)
        self.assertTrue(out["lookahead_selection_bias"])
        self.assertFalse(out["real_trades_allowed"])


if __name__=="__main__":
    unittest.main()
