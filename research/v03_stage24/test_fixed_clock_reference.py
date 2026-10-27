"""Offline tests for frozen all-ticker reference, NOT a backtest success rate."""
import copy
import datetime as dt
import json
import unittest
from unittest.mock import patch

from fixed_clock_reference import fixed_reference_entries, prepare_result
from forward_outcomes_iex import fetch_forward_bars
from prospective_iex_research import digest_frozen
from test_forward_outcomes_iex import T0,REVIEWED,REVIEW,FROZEN,KNOWN,LATER

UTC=dt.timezone.utc
REF=dt.datetime(2026,10,27,13,52,tzinfo=UTC)
READY=dt.datetime(2026,10,27,14,55,tzinfo=UTC)


def prices(n=60,missing=None):
    missing=missing or set()
    return [{"t":(REF+dt.timedelta(minutes=i)).isoformat(),
             "o":2.00,"h":2.50,"l":1.90,"c":2+0.002*i,"v":200}
            for i in range(n) if i not in missing]


def pair():
    freeze=copy.deepcopy(FROZEN)
    freeze["candidates"]=["GPUS","LAES"]
    freeze["candidate_count"]=2
    freeze["sha256"]=digest_frozen(freeze)
    review=copy.deepcopy(REVIEW)
    review["results"][0]["observed_iex_bars"]=14
    review["results"].append({
        "symbol":"LAES","grade":"D","pattern_count":0,"first_pattern":None,
        "buy_allowed":False,"observed_iex_bars":12,
    })
    return freeze,review


class FixedClockReferenceTests(unittest.TestCase):
    def test_same_reference_for_both_cohorts(self):
        f,r=pair()
        refs=fixed_reference_entries(f,r)
        self.assertEqual(refs,{"GPUS":REF,"LAES":REF})
        self.assertLess(REF,REVIEWED)
        self.assertLess(T0,REF)

    def test_all_frozen_symbols_not_just_winners(self):
        f,r=pair()
        out=prepare_result(f,r,{"GPUS":prices(),"LAES":prices()},READY)
        self.assertEqual(out["frozen_symbols"],2)
        self.assertEqual(out["initial_pattern_observed"],1)
        self.assertEqual(out["initial_no_pattern_observed"],1)
        self.assertEqual(out["observed_iex_prices_complete"],8)
        self.assertTrue(out["not_randomized_control"])
        self.assertTrue(out["not_proof_of_no_signal"])
        self.assertTrue(out["not_a_causal_effect_estimate"])
        self.assertFalse(out["real_trades_allowed"])
        self.assertTrue(all(not x["buy_allowed"] and x["grade"]=="D" for x in out["rows"]))

    def test_no_signal_still_has_preset_reference(self):
        f,r=pair()
        r["results"][0]["pattern_count"]=0
        r["results"][0]["first_pattern"]=None
        out=prepare_result(f,r,{"GPUS":prices(),"LAES":prices()},READY)
        self.assertEqual(out["initial_pattern_observed"],0)
        self.assertEqual(out["frozen_symbols"],2)
        self.assertEqual(out["observed_iex_prices_complete"],8)
        self.assertTrue(out["not_proof_of_no_signal"])

    def test_missing_minutes_unknown_not_zero_returns(self):
        f,r=pair()
        out=prepare_result(f,r,{"GPUS":prices(missing={3}),"LAES":[]},READY)
        self.assertEqual(out["observed_iex_prices_complete"],0)
        self.assertIsNone(out["rows"][0]["horizons"][0]["theoretical_iex_open_to_close_pct"])
        self.assertTrue(all(x["status"]=="MISSING_IEX_MINUTES" for x in out["rows"][1]["horizons"]))

    def test_future_not_mature(self):
        f,r=pair()
        with self.assertRaisesRegex(ValueError,"FIXED_REFERENCE_FUTURE_NOT_MATURE"):
            prepare_result(f,r,{"GPUS":[],"LAES":[]},REF+dt.timedelta(minutes=59))

    def test_missing_stock_is_not_silent(self):
        f,r=pair()
        with self.assertRaisesRegex(ValueError,"FROZEN_REFERENCE_UNIVERSE_MISMATCH"):
            prepare_result(f,r,{"GPUS":prices()},READY)

    def test_added_stock_is_not_silent(self):
        f,r=pair()
        with self.assertRaisesRegex(ValueError,"FROZEN_REFERENCE_UNIVERSE_MISMATCH"):
            prepare_result(f,r,{"GPUS":prices(),"LAES":[],"AAPL":[]},READY)

    def test_pre_reference_prices_rejected(self):
        f,r=pair()
        bad=prices()
        bad[0]["t"]=(REF-dt.timedelta(minutes=1)).isoformat()
        with self.assertRaisesRegex(ValueError,"BAR_OUTSIDE_WINDOW"):
            prepare_result(f,r,{"GPUS":bad,"LAES":[]},READY)

    def test_future_prices_rejected(self):
        f,r=pair()
        bad=prices()
        bad[-1]["t"]=(REF+dt.timedelta(minutes=63)).isoformat()
        with self.assertRaisesRegex(ValueError,"BAR_OUTSIDE_WINDOW"):
            prepare_result(f,r,{"GPUS":bad,"LAES":[]},READY)

    def test_duplicate_bar_rejected(self):
        f,r=pair()
        bad=prices()+[prices()[0]]
        with self.assertRaisesRegex(ValueError,"DUPLICATE_IEX_BAR"):
            prepare_result(f,r,{"GPUS":bad,"LAES":[]},READY)

    def test_tampered_t0_rejected(self):
        f,r=pair()
        f["selected_at_utc"]=(T0-dt.timedelta(hours=1)).isoformat()
        with self.assertRaisesRegex(ValueError,"T0_HASH_MISMATCH"):
            fixed_reference_entries(f,r)

    def test_fake_retro_study_rejected(self):
        f,r=pair()
        r["candidate_selection_before_bars"]=False
        with self.assertRaisesRegex(ValueError,"RETROSPECTIVE_OR_MIXED_FEED"):
            fixed_reference_entries(f,r)

    def test_grade_upgrade_rejected(self):
        f,r=pair()
        r["results"][1]["grade"]="A"
        with self.assertRaisesRegex(ValueError,"UNSAFE_RESEARCH_GRADE"):
            fixed_reference_entries(f,r)

    def test_outcome_fetch_before_maturity_blocked(self):
        f,r=pair()
        entries=fixed_reference_entries(f,r)
        def forb(*args,**kwargs):
            raise AssertionError("MUST NOT ACCESS MARKETS BEFORE 60M")
        with self.assertRaisesRegex(ValueError,"OUTCOMES_NOT_YET_COMPLETED"):
            fetch_forward_bars(entries,REF+dt.timedelta(minutes=60),"k","s",opener=forb)

    def test_successful_iex_get_request_is_get_only(self):
        f,r=pair()
        entries=fixed_reference_entries(f,r)
        class FakeResponse:
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def read(self,n=-1):return json.dumps({
                "bars":{"GPUS":prices(),"LAES":prices()},"next_page_token":None
            }).encode()
        def opener(req,timeout):
            self.assertEqual(req.get_method(),"GET")
            self.assertIn("feed=iex",req.full_url)
            self.assertIn("symbols=GPUS%2CLAES",req.full_url)
            self.assertNotIn("/orders",req.full_url)
            self.assertIn("13%3A52%3A00Z",req.full_url)
            return FakeResponse()
        output=fetch_forward_bars(entries,READY,"k","s",opener=opener)
        self.assertEqual(list(output),["GPUS","LAES"])
        self.assertEqual(len(output["LAES"]),60)

    def test_ref_does_not_change_with_pattern_status(self):
        f,r=pair()
        first=fixed_reference_entries(f,r)
        r["results"][0]["pattern_count"]=0
        r["results"][0]["first_pattern"]=None
        self.assertEqual(first,fixed_reference_entries(f,r))

    def test_reference_contains_no_live_accuracy_claim(self):
        f,r=pair()
        out=prepare_result(f,r,{"GPUS":[],"LAES":[]},READY)
        self.assertFalse(out["not_prospective_accuracy_verified"] is False)
        self.assertFalse(out["fees_spread_slippage_or_fills_verified"])
        self.assertEqual(out["validation_status"],"NOT_VALIDATED")


if __name__=="__main__":
    unittest.main()
