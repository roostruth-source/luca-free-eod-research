"""Offline, deterministic tests for forward-only IEX 5/15/30/60m outcomes."""
import datetime as dt
import json
import unittest
import urllib.error
from unittest.mock import patch

from prospective_iex_research import digest_frozen, next_bar_start
from forward_outcomes_iex import (validate_origins,evaluation_window,
    fetch_forward_bars,horizon_result,build_report,parse_utc)

UTC=dt.timezone.utc
T0=dt.datetime(2026,10,27,13,45,11,tzinfo=UTC)
BASE=next_bar_start(T0)
KNOWN=BASE+dt.timedelta(minutes=6)
REVIEWED=T0+dt.timedelta(minutes=17)
LATER=KNOWN+dt.timedelta(minutes=63)
FROZEN={
 "schema":"LUCA_V03_PROSPECTIVE_FREEZE_V1",
 "selected_at_utc":T0.isoformat(),
 "session_day_ny":"2026-10-27",
 "candidates":["GPUS"],
 "candidate_count":1,
 "selection_cap":12,
 "sec_status":"SEC_UNVERIFIED",
 "validation_status":"NOT_VALIDATED",
 "real_trades_allowed":False,
}
FROZEN["sha256"]=digest_frozen(FROZEN)
REVIEW={
 "schema":"LUCA_V03_PROSPECTIVE_IEX_REVIEW_V1",
 "selected_at_utc":T0.isoformat(),
 "first_allowed_bar_start_utc":BASE.isoformat(),
 "last_allowed_bar_start_utc":(REVIEWED-dt.timedelta(minutes=2)).replace(second=0,microsecond=0).isoformat(),
 "reviewed_at_utc":REVIEWED.isoformat(),
 "feed":"IEX_SINGLE_EXCHANGE_NOT_SIP",
 "candidate_selection_before_bars":True,
 "results":[{"symbol":"GPUS","grade":"D","pattern_count":1,
             "buy_allowed":False,
             "first_pattern":{
               "signal_bar_start_utc":(KNOWN-dt.timedelta(minutes=1)).isoformat(),
               "bar_knowable_after_utc":KNOWN.isoformat(),
               "research_pattern_only":True,"buy_allowed":False}}],
 "prediction_accuracy_verified":False,"validation_status":"NOT_VALIDATED",
 "real_trades_allowed":False,
}
def bars(n=60):
    return [{"t":(KNOWN+dt.timedelta(minutes=i)).isoformat(),
             "o":1.0,"h":1.5,"l":0.9,"c":1.0+0.005*i,"v":100+i}
            for i in range(n)]


class FakeResponse:
    def __init__(self,value):self.value=value
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.value[:n]


class Tests(unittest.TestCase):
    def test_linked_freeze_and_review(self):
        t0,reviewed,signals=validate_origins(FROZEN,REVIEW)
        self.assertEqual(t0,T0)
        self.assertEqual(signals,{"GPUS":KNOWN})
        self.assertEqual(evaluation_window(signals),(KNOWN,KNOWN+dt.timedelta(minutes=59)))

    def test_all_horizons_exact(self):
        r=build_report(FROZEN,REVIEW,{"GPUS":bars()},LATER)
        self.assertEqual(r["evaluated_signals"],1)
        self.assertEqual(r["complete_horizons"],4)
        self.assertEqual([x["horizon_minutes"] for x in r["signals"][0]["horizons"]],[5,15,30,60])
        self.assertEqual(r["signals"][0]["horizons"][0]["theoretical_iex_open_to_close_pct"],2.0)
        self.assertEqual(r["signals"][0]["horizons"][3]["theoretical_iex_open_to_close_pct"],29.5)
        self.assertFalse(r["real_trades_allowed"])
        self.assertFalse(r["fees_slippage_or_spread_included"])
        self.assertFalse(r["historical_accuracy_verified"])

    def test_no_claims_of_fill_or_return(self):
        r=build_report(FROZEN,REVIEW,{"GPUS":bars()},LATER)
        x=r["signals"][0]["horizons"][0]
        self.assertFalse(x["real_fill_verified"])
        self.assertFalse(x["slippage_and_spread_included"])
        self.assertEqual(r["measurement"],"HYPOTHETICAL_IEX_NEXT_MINUTE_OPEN_TO_HORIZON_CLOSE")

    def test_missing_minute_blocks_only_affected_horizons(self):
        data=[x for i,x in enumerate(bars()) if i!=7]
        r=build_report(FROZEN,REVIEW,{"GPUS":data},LATER)
        v=r["signals"][0]["horizons"]
        self.assertEqual(v[0]["status"],"COMPLETE_IEX_PRICES_ONLY")
        self.assertEqual(v[1]["status"],"MISSING_IEX_MINUTES")
        self.assertIsNone(v[3]["theoretical_iex_open_to_close_pct"])
        self.assertEqual(r["complete_horizons"],1)

    def test_first_eligible_bar_missing_blocks_all(self):
        r=build_report(FROZEN,REVIEW,{"GPUS":bars()[1:]},LATER)
        self.assertEqual(r["complete_horizons"],0)

    def test_future_not_yet_known_cannot_be_evaluated(self):
        with self.assertRaisesRegex(ValueError,"FUTURE_OUTCOMES_NOT_READY"):
            build_report(FROZEN,REVIEW,{"GPUS":bars()},KNOWN+dt.timedelta(minutes=30))

    def test_fetch_not_yet_completed_never_calls_api(self):
        def forbidden(*a,**kw):
            raise AssertionError("API request before outcome maturity")
        with self.assertRaisesRegex(ValueError,"OUTCOMES_NOT_YET_COMPLETED"):
            fetch_forward_bars({"GPUS":KNOWN},KNOWN+dt.timedelta(minutes=59),"k","s",forbidden)

    def test_get_only_iex_and_forward_times(self):
        def opener(req,timeout):
            self.assertEqual(req.get_method(),"GET")
            self.assertIn("feed=iex",req.full_url)
            self.assertIn("timeframe=1Min",req.full_url)
            self.assertNotIn("/orders",req.full_url)
            self.assertIn("symbols=GPUS",req.full_url)
            self.assertIn("13%3A52%3A00Z",req.full_url)
            self.assertIn("14%3A51%3A00Z",req.full_url)
            return FakeResponse(json.dumps({"bars":{"GPUS":bars()},"next_page_token":None}).encode())
        out=fetch_forward_bars({"GPUS":KNOWN},LATER,"k","s",opener)
        self.assertEqual(len(out["GPUS"]),60)

    def test_duplicate_bar_refused(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_IEX_MINUTE"):
            build_report(FROZEN,REVIEW,{"GPUS":bars(5)+[bars(5)[1]]},LATER)

    def test_future_bar_ignored_not_entered_as_price(self):
        extra=dict(bars()[0])
        extra["t"]=(KNOWN+dt.timedelta(minutes=80)).isoformat()
        r=build_report(FROZEN,REVIEW,{"GPUS":bars()+[extra]},LATER)
        self.assertEqual(r["complete_horizons"],4)

    def test_tampered_freeze_hash_refused(self):
        f=json.loads(json.dumps(FROZEN))
        f["selected_at_utc"]=(T0+dt.timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError,"T0_HASH_MISMATCH"):
            validate_origins(f,REVIEW)

    def test_unsafe_tampered_review_rejected(self):
        r=json.loads(json.dumps(REVIEW));r["real_trades_allowed"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_REVIEW"):
            validate_origins(FROZEN,r)

    def test_retro_report_rejected(self):
        r=json.loads(json.dumps(REVIEW));r["candidate_selection_before_bars"]=False
        with self.assertRaisesRegex(ValueError,"RETROSPECTIVE_OR_MIXED_FEED"):
            validate_origins(FROZEN,r)

    def test_future_signal_known_after_review_rejected(self):
        r=json.loads(json.dumps(REVIEW))
        r["results"][0]["first_pattern"]["bar_knowable_after_utc"]=(REVIEWED+dt.timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError,"FUTURE_OR_PRE_T0_SIGNAL"):
            validate_origins(FROZEN,r)

    def test_signal_pre_t0_rejected(self):
        r=json.loads(json.dumps(REVIEW))
        r["results"][0]["first_pattern"]["signal_bar_start_utc"]=T0.replace(second=0,microsecond=0).isoformat()
        r["results"][0]["first_pattern"]["bar_knowable_after_utc"]=(T0.replace(second=0,microsecond=0)+dt.timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError,"FUTURE_OR_PRE_T0_SIGNAL"):
            validate_origins(FROZEN,r)

    def test_grade_upgrade_rejected(self):
        r=json.loads(json.dumps(REVIEW));r["results"][0]["grade"]="A"
        with self.assertRaisesRegex(ValueError,"UNSAFE_RESEARCH_GRADE"):
            validate_origins(FROZEN,r)

    def test_signal_universe_swap_rejected(self):
        r=json.loads(json.dumps(REVIEW));r["results"][0]["symbol"]="AAPL"
        with self.assertRaisesRegex(ValueError,"REVIEW_SYMBOLS_DRIFT"):
            validate_origins(FROZEN,r)

    def test_invalid_time_rejected(self):
        with self.assertRaisesRegex(ValueError,"AWARE_DATETIME_REQUIRED"):
            parse_utc("2026-10-27T14:00:00")

    def test_no_horizon_when_data_sparse(self):
        self.assertEqual(horizon_result([],KNOWN,5)["status"],"MISSING_IEX_MINUTES")
        self.assertIsNone(horizon_result([],KNOWN,60)["theoretical_iex_open_to_close_pct"])

    def test_no_signal_cannot_claim_success(self):
        r=json.loads(json.dumps(REVIEW))
        r["results"][0]["pattern_count"]=0
        r["results"][0]["first_pattern"]=None
        _t0,_r,known=validate_origins(FROZEN,r)
        self.assertEqual(known,{})
        with self.assertRaisesRegex(ValueError,"NO_FROZEN_SIGNALS"):
            build_report(FROZEN,r,{},LATER)


if __name__=="__main__":
    unittest.main()
