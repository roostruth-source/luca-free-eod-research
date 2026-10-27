"""Offline prospective IEX time-lock and no-lookahead leakage regression tests."""
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from prospective_iex_research import (
    freeze, review, next_bar_start, check_frozen, fetch_after_freeze,
    ny_window, digest_frozen, run_freeze_phase,
)

UTC=dt.timezone.utc
T0=dt.datetime(2026,10,27,13,50,5,tzinfo=UTC)
T1=T0+dt.timedelta(minutes=17)
ENRICH={
    "schema":"LUCA_V03_IEX_CANDIDATE_ENRICHMENT_V1",
    "status":"COLLECTED_UNVERIFIED",
    "validation_status":"NOT_VALIDATED","real_trades_allowed":False,
    "collected_at_utc":(T0-dt.timedelta(seconds=12)).isoformat(),
    "rows":[
        {"symbol":"GPUS","price_band_0_20_to_20":True,
         "research_status":"WATCH_ONLY_FRESH_IEX","buy_allowed":False},
        {"symbol":"LAES","price_band_0_20_to_20":True,
         "research_status":"PENDING_STALE_OR_MISSING","buy_allowed":False},
        {"symbol":"NIKI","price_band_0_20_to_20":False,
         "research_status":"WATCH_ONLY_FRESH_IEX","buy_allowed":False},
    ],
}


def make_bar(minute,low=1.0,volume=20,close=1.5):
    t=next_bar_start(T0)+dt.timedelta(minutes=minute)
    return {"t":t.isoformat(),"o":close,"h":max(low,close)+0.1,
            "l":low,"c":close,"v":volume}


class FakeResponse:
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.data[:n]


class TimeLockedTest(unittest.TestCase):
    def setUp(self):
        self.frozen=freeze(ENRICH,T0)

    def test_frozen_only_fresh_research_watch_not_buy(self):
        self.assertEqual(self.frozen["candidates"],["GPUS"])
        self.assertEqual(self.frozen["candidate_count"],1)
        self.assertFalse(self.frozen["real_trades_allowed"])
        self.assertEqual(self.frozen["sec_status"],"SEC_UNVERIFIED")
        self.assertTrue(self.frozen["not_nyse_holiday_verified"])

    def test_time_is_after_actual_selection(self):
        self.assertEqual(self.frozen["selected_at_utc"],T0.isoformat())
        self.assertEqual(next_bar_start(T0),dt.datetime(2026,10,27,13,51,tzinfo=UTC))

    def test_exact_minute_freeze_still_starts_next_bar(self):
        t=dt.datetime(2026,10,27,13,50,tzinfo=UTC)
        self.assertEqual(next_bar_start(t),dt.datetime(2026,10,27,13,51,tzinfo=UTC))

    def test_session_gate_offhours(self):
        self.assertTrue(ny_window(T0))
        self.assertFalse(ny_window(dt.datetime(2026,10,27,9,0,tzinfo=UTC)))
        self.assertFalse(ny_window(dt.datetime(2026,10,31,14,0,tzinfo=UTC)))

    def test_next_bar_at_least_13min_later(self):
        with self.assertRaisesRegex(ValueError,"WRONG_FORWARD_OBSERVATION_INTERVAL"):
            check_frozen(self.frozen,T0+dt.timedelta(minutes=12))
        names,start,end=check_frozen(self.frozen,T1)
        self.assertEqual(names,["GPUS"])
        self.assertEqual(start.hour,13)
        self.assertEqual(start.minute,51)
        self.assertEqual(end,dt.datetime(2026,10,27,14,5,tzinfo=UTC))

    def test_too_late_in_future_rejected(self):
        with self.assertRaisesRegex(ValueError,"WRONG_FORWARD_OBSERVATION_INTERVAL"):
            check_frozen(self.frozen,T0+dt.timedelta(minutes=36))

    def test_tampered_candidate_hash_rejected(self):
        frozen=json.loads(json.dumps(self.frozen))
        frozen["candidates"]=["AAPL"]
        with self.assertRaisesRegex(ValueError,"FROZEN_HASH_MISMATCH"):
            check_frozen(frozen,T1)

    def test_unsafe_trade_flag_rejected_even_with_recomputed_hash(self):
        frozen=json.loads(json.dumps(self.frozen))
        frozen["real_trades_allowed"]=True
        frozen["sha256"]=digest_frozen(frozen)
        with self.assertRaisesRegex(ValueError,"UNSAFE_FREEZE"):
            check_frozen(frozen,T1)

    def test_old_selection_timestamp_rejected(self):
        stale=json.loads(json.dumps(ENRICH))
        stale["collected_at_utc"]=(T0-dt.timedelta(minutes=6)).isoformat()
        with self.assertRaisesRegex(ValueError,"STALE_DISCOVERY"):
            freeze(stale,T0)

    def test_future_selection_timestamp_rejected(self):
        stale=json.loads(json.dumps(ENRICH))
        stale["collected_at_utc"]=(T0+dt.timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(ValueError,"FUTURE_SELECTION_TIMESTAMP"):
            freeze(stale,T0)

    def test_outside_market_freeze_blocked(self):
        with self.assertRaisesRegex(ValueError,"OUTSIDE_RESEARCH_SESSION"):
            freeze(ENRICH,T0-dt.timedelta(hours=4))

    def test_only_get_iex_and_strictly_post_frozen_t0(self):
        def opener(req,timeout):
            self.assertEqual(req.get_method(),"GET")
            self.assertIn("feed=iex",req.full_url)
            self.assertIn("13%3A51%3A00Z",req.full_url)
            self.assertIn("14%3A05%3A00Z",req.full_url)
            self.assertNotIn("feed=sip",req.full_url)
            self.assertNotIn("/orders",req.full_url)
            self.assertEqual(timeout,30)
            bars=[make_bar(i,low=1.0+i*0.01,
                           volume=300 if i==5 else 20) for i in range(6)]
            return FakeResponse(json.dumps({"bars":{"GPUS":bars},
                                           "next_page_token":None}).encode())
        output=fetch_after_freeze(self.frozen,T1,"k","s",opener)
        self.assertEqual(len(output["GPUS"]),6)
        r=review(self.frozen,output,T1)
        self.assertEqual(r["forward_pattern_symbols"],1)
        self.assertTrue(r["candidate_selection_before_bars"])
        self.assertFalse(r["prediction_accuracy_verified"])
        self.assertEqual(r["results"][0]["grade"],"D")
        self.assertFalse(r["results"][0]["buy_allowed"])
        self.assertFalse(r["real_trades_allowed"])

    def test_bar_before_t0_blocked(self):
        before=make_bar(0)
        before["t"]=T0.replace(second=0,microsecond=0).isoformat()
        with self.assertRaisesRegex(ValueError,"BAR_OUTSIDE_WINDOW"):
            review(self.frozen,{"GPUS":[before]},T1)

    def test_bar_too_recent_blocked(self):
        newer=make_bar(30)
        with self.assertRaisesRegex(ValueError,"BAR_OUTSIDE_WINDOW"):
            review(self.frozen,{"GPUS":[newer]},T1)

    def test_no_data_is_not_success_pattern(self):
        r=review(self.frozen,{"GPUS":[]},T1)
        self.assertEqual(r["observed_iex_bars"],0)
        self.assertEqual(r["forward_pattern_symbols"],0)
        self.assertEqual(r["results"][0]["grade"],"D")

    def test_no_substituted_universe(self):
        with self.assertRaisesRegex(ValueError,"FROZEN_UNIVERSE_DRIFT"):
            review(self.frozen,{"AAPL":[]},T1)

    def test_future_complete_bar_not_stretched_across_gap(self):
        data=[make_bar(i,low=1.0+i*0.01,
                       volume=300 if i==6 else 20) for i in [0,1,2,3,4,6]]
        r=review(self.frozen,{"GPUS":data},T1)
        self.assertEqual(r["forward_pattern_symbols"],0)

    def test_zero_fresh_candidates_stops_before_wait(self):
        blank=dict(ENRICH)
        blank["collected_at_utc"]=dt.datetime.now(UTC).isoformat()
        blank["rows"]=[]
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{
                "LUCA_FREEZE_DIR":d,"ALPACA_KEY":"offline","ALPACA_SECRET":"offline"
            }),patch("prospective_iex_research.ny_window",return_value=True),patch(
                "prospective_iex_research.enrich_run",return_value=blank):
            with self.assertRaises(SystemExit) as ctx:
                run_freeze_phase()
            self.assertEqual(ctx.exception.code,6)
            saved=json.loads((Path(d)/"frozen_t0.json").read_text())
            self.assertEqual(saved["candidate_count"],0)
            self.assertFalse(saved["real_trades_allowed"])

    def test_freeze_phase_out_of_market_does_not_call_api(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{"LUCA_FREEZE_DIR":d}),patch(
                "prospective_iex_research.ny_window",return_value=False),patch(
                "prospective_iex_research.enrich_run",side_effect=AssertionError("API MUST NOT BE CALLED")):
            with self.assertRaises(SystemExit) as ctx:
                run_freeze_phase()
            self.assertEqual(ctx.exception.code,4)
            doc=json.loads((Path(d)/"session_status.json").read_text())
            self.assertEqual(doc["status"],"OUTSIDE_RESEARCH_SESSION")
            self.assertFalse(doc["real_trades_allowed"])


if __name__=="__main__":
    unittest.main()
