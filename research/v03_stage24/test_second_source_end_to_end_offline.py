"""Offline E2E rehearsal for the exact SECOND SOURCE GitHub workflow.

Calls real freeze-phase entrypoint and real future review entrypoint, with only
synthetic enrichment and GET responses. No market network, orders or schedules.
"""
import copy
import datetime as real_dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import prospective_iex_research as source
from future_iex_review import review_future_session
from second_trial_gate import validate,BRANCH
from second_trial_artifact_bridge import build_verified_comparison
from first_iex_baseline_integrity import load_verified
from test_second_trial_artifact_bridge import META,ART
from test_prospective_iex_research import ENRICH
from prospective_iex_research import next_bar_start
from test_two_session_iex_comparison import SECOND_ID

UTC=real_dt.timezone.utc
T0=real_dt.datetime(2026,10,28,14,0,5,tzinfo=UTC)
T1=T0+real_dt.timedelta(minutes=17)

class FrozenClock(real_dt.datetime):
    @classmethod
    def now(cls,tz=None):
        if tz!=UTC:
            raise ValueError("TEST_REQUIRES_UTC")
        return cls(2026,10,28,14,0,5,tzinfo=UTC)

class Response:
    def __init__(self,bars,status=200):
        self.status=status
        self.data=json.dumps({"bars":bars,"next_page_token":None}).encode()
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,n=-1):return self.data[:n]

def synthetic_enrichment():
    x=copy.deepcopy(ENRICH)
    x["collected_at_utc"]=(T0-real_dt.timedelta(seconds=12)).isoformat()
    return x

def synthetic_bars():
    return [
        {"t":(next_bar_start(T0)+real_dt.timedelta(minutes=i)).isoformat(),
         "o":1.5,"h":1.7,"l":1.0+i*0.01,"c":1.5,"v":300 if i==5 else 20}
        for i in range(12)
    ]


class SecondSourceWorkflowE2ETests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.enrich=synthetic_enrichment()
        self.clock=SimpleNamespace(datetime=FrozenClock,
              timedelta=real_dt.timedelta,timezone=real_dt.timezone)
        self.env=patch.dict(os.environ,{"LUCA_FREEZE_DIR":str(self.folder),
              "ALPACA_KEY":"offline-key","ALPACA_SECRET":"offline-secret"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.calls=0

    def freeze(self):
        with patch.object(source,"dt",self.clock),patch.object(source,"enrich_run",return_value=self.enrich):
            source.run_freeze_phase()
        return json.loads((self.folder/"frozen_t0.json").read_text(encoding="utf8"))

    def get(self,req,timeout,bars=None,status=200):
        self.assertEqual(req.get_method(),"GET")
        self.assertIn("feed=iex",req.full_url)
        self.assertNotIn("/orders",req.full_url)
        self.assertIn("14%3A01%3A00Z",req.full_url)
        self.calls+=1
        return Response({"GPUS":synthetic_bars()} if bars is None else bars,status)

    def review(self,opener):
        clock=SimpleNamespace(datetime=SimpleNamespace(
              now=lambda tz:T1+real_dt.timedelta(seconds=1)))
        with patch("iex_provenance_adapter.dt",clock):
            return review_future_session(self.folder,now=T1,opener=opener)

    def test_real_second_source_entrypoints_through_verified_comparison(self):
        request="LUCA_V03_SECOND_PROSPECTIVE_ONCE\\nsession_day_ny=2026-10-28\\nresearch_only=true\\n".replace("\\n","\n")
        self.assertTrue(validate(request,T0,"push",BRANCH,"1",1)["allowed"])
        frozen=self.freeze()
        digest=frozen["sha256"]
        observed,provenance=self.review(lambda req,timeout:self.get(req,timeout))
        self.assertEqual(self.calls,1)
        self.assertEqual(frozen["candidates"],["GPUS"])
        self.assertEqual(observed["observed_iex_bars"],12)
        self.assertEqual(observed["forward_pattern_symbols"],1)
        self.assertEqual(provenance["api_fetch"]["page_count"],1)
        self.assertEqual(provenance["rows"][0]["observed_minutes"],12)
        self.assertEqual(provenance["expected_minutes_per_symbol"],15)
        self.assertEqual(json.loads((self.folder/"frozen_t0.json").read_text())["sha256"],digest)
        compared=build_verified_comparison(load_verified(),META,frozen,observed,provenance,ART)
        self.assertEqual(compared["second"]["observed"],12)
        self.assertFalse(compared["real_trades_allowed"])
        self.assertTrue(compared["second_source_workflow_verified"])

    def test_empty_single_exchange_feed_kept_as_unknown_not_failed_trade(self):
        self.freeze()
        observed,provenance=self.review(lambda req,timeout:self.get(req,timeout,bars={}))
        self.assertEqual(observed["forward_pattern_symbols"],0)
        self.assertEqual(provenance["rows"][0]["observed_minutes"],0)
        self.assertEqual(len(provenance["rows"][0]["missing_iex_bar_start_utc"]),15)
        self.assertTrue(provenance["missing_iex_bar_cause_unknown"])
        self.assertFalse(observed["real_trades_allowed"])

    def test_pre_t0_bar_cannot_be_smuggled_into_review(self):
        self.freeze()
        corrupted=synthetic_bars()
        corrupted[0]["t"]=T0.replace(second=0).isoformat()
        with self.assertRaisesRegex(ValueError,"BAR_OUTSIDE_WINDOW"):
            self.review(lambda req,timeout:self.get(req,timeout,bars={"GPUS":corrupted}))
        self.assertFalse((self.folder/"forward_review.json").exists())
        self.assertFalse((self.folder/"iex_timestamp_provenance.json").exists())

    def test_unverified_http_status_blocks_archival(self):
        self.freeze()
        with self.assertRaisesRegex(ValueError,"UNVERIFIED_HTTP_STATUS"):
            self.review(lambda req,timeout:self.get(req,timeout,status=503))
        self.assertFalse((self.folder/"forward_review.json").exists())
        self.assertFalse((self.folder/"iex_timestamp_provenance.json").exists())

    def test_duplicate_freeze_file_is_not_overwritten(self):
        f=self.freeze()
        with self.assertRaises(FileExistsError):
            self.freeze()
        self.assertEqual(json.loads((self.folder/"frozen_t0.json").read_text()),f)


if __name__=="__main__":
    unittest.main()
