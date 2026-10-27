"""Offline rehearsal of the EXACT T0 -> IEX review -> outcomes -> Korean report chain.

No market API, GitHub write, orders, alerts, or real performance. All prices
and source metadata below are SYNTHETIC and must never be published as results.
"""
import copy
import datetime as dt
import unittest
from pathlib import Path

from prospective_iex_research import freeze,review,next_bar_start
from forward_outcomes_iex import build_report
from fixed_clock_reference import prepare_result
from korean_forward_report import korean_report
from evidence_quality_gate import summarize
from test_prospective_iex_research import ENRICH,T0,T1,make_bar
from followup_bridge import RUN_WORKFLOW,RESEARCH_BRANCH

SOURCE={"databaseId":40499999999,"name":RUN_WORKFLOW,
        "headBranch":RESEARCH_BRANCH,"event":"push",
        "status":"completed","conclusion":"success"}
UTC=dt.timezone.utc


def make_synthetic():
    frozen=freeze(ENRICH,T0)
    initial=[make_bar(i,low=1.0+i*0.01,
                      volume=300 if i==5 else 20) for i in range(12)]
    observed=review(frozen,{"GPUS":initial},T1)
    return frozen,observed


def mature_synthetic(frozen,observed):
    signal=observed["results"][0]["first_pattern"]
    entry=dt.datetime.fromisoformat(signal["bar_knowable_after_utc"])
    later=entry+dt.timedelta(minutes=65)
    prices=[{"t":(entry+dt.timedelta(minutes=i)).isoformat(),
             "o":1.5,"h":1.8,"l":1.4,"c":1.5+0.001*i,"v":100}
            for i in range(60)]
    outcomes=build_report(frozen,observed,{"GPUS":prices},later)
    fixed=next_bar_start(T0)+dt.timedelta(minutes=6)
    fixed_prices=[{"t":(fixed+dt.timedelta(minutes=i)).isoformat(),
                   "o":1.5,"h":1.8,"l":1.4,"c":1.5+0.001*i,"v":100}
                  for i in range(60)]
    reference=prepare_result(frozen,observed,{"GPUS":fixed_prices},later)
    return outcomes,reference


class LiveTrialContractTests(unittest.TestCase):
    def test_full_synthetic_chain_keeps_research_grade_d(self):
        frozen,observed=make_synthetic()
        outcomes,reference=mature_synthetic(frozen,observed)
        quality=summarize(frozen,observed,outcomes,reference)
        report=korean_report(SOURCE,frozen,observed,outcomes,reference)
        self.assertEqual(quality["pattern_observed_symbols"],1)
        self.assertEqual(quality["signal_outcome_evidence"],"OBSERVED_COMPLETE_IEX_ONLY")
        self.assertEqual(quality["fixed_clock_reference_evidence"],"OBSERVED_COMPLETE_IEX_ONLY")
        self.assertIn("40499999999",report)
        self.assertIn("초기 연구 패턴 기록: 1종목",report)
        self.assertIn("실제 주문 금지",report)
        self.assertFalse(quality["real_trades_allowed"])

    def test_synthetic_no_signal_still_reports_not_validated(self):
        frozen,observed=make_synthetic()
        observed["results"][0]["pattern_count"]=0
        observed["results"][0]["first_pattern"]=None
        observed["forward_pattern_symbols"]=0
        report=korean_report(SOURCE,frozen,observed)
        self.assertIn("초기 연구 패턴 기록: 0종목",report)
        self.assertIn("후속 실측 미확인",report)
        self.assertIn("매수 금지",report)

    def test_missing_initial_iex_bars_not_a_failed_prediction(self):
        frozen,observed=make_synthetic()
        observed["results"][0]["pattern_count"]=0
        observed["results"][0]["first_pattern"]=None
        observed["results"][0]["observed_iex_bars"]=0
        observed["observed_iex_bars"]=0
        observed["forward_pattern_symbols"]=0
        report=korean_report(SOURCE,frozen,observed)
        self.assertIn("IEX 분봉 0개(판정 불가)",report)

    def test_tampered_candidate_universe_blocks_all_reporting(self):
        frozen,observed=make_synthetic()
        frozen["candidates"]=["AAPL"]
        with self.assertRaises(ValueError):
            korean_report(SOURCE,frozen,observed)

    def test_failed_github_run_blocks_reporting(self):
        frozen,observed=make_synthetic()
        bad=copy.deepcopy(SOURCE);bad["conclusion"]="failure"
        with self.assertRaisesRegex(ValueError,"PROSPECTIVE_RUN_NOT_SUCCESSFUL"):
            korean_report(bad,frozen,observed)

    def test_wrong_branch_blocks_reporting(self):
        frozen,observed=make_synthetic()
        bad=copy.deepcopy(SOURCE);bad["headBranch"]="main"
        with self.assertRaisesRegex(ValueError,"WRONG_BRANCH_OR_EVENT"):
            korean_report(bad,frozen,observed)

    def test_future_outcome_not_ready_is_rejected(self):
        frozen,observed=make_synthetic()
        signal=observed["results"][0]["first_pattern"]
        entry=dt.datetime.fromisoformat(signal["bar_knowable_after_utc"])
        with self.assertRaisesRegex(ValueError,"FUTURE_OUTCOMES_NOT_READY"):
            build_report(frozen,observed,{"GPUS":[]},entry+dt.timedelta(minutes=30))

    def test_source_workflow_is_one_shot_not_scheduled(self):
        root=Path(__file__).resolve().parents[2]
        content=(root/".github/workflows/luca-v03-prospective-live-once.yml").read_text()
        self.assertIn("research/v03_stage24/prospective_live_request.txt",content)
        self.assertIn("sleep 960",content)
        self.assertIn("research/v03-stage24-evidence",content)
        self.assertNotIn("schedule:",content)
        self.assertNotIn("workflow_dispatch:",content)
        self.assertNotIn("cancel-in-progress: true",content)

    def test_followup_is_one_shot_not_scheduled(self):
        root=Path(__file__).resolve().parents[2]
        content=(root/".github/workflows/luca-v03-followup-once.yml").read_text()
        self.assertIn("research/v03_stage24/followup_live_request.txt",content)
        self.assertIn("korean_forward_report.py",content)
        self.assertNotIn("schedule:",content)
        self.assertNotIn("workflow_dispatch:",content)
        self.assertIn("NO", "NO")

    def test_synthetic_source_metadata_cannot_claim_real_trading(self):
        frozen,observed=make_synthetic()
        report=korean_report(SOURCE,frozen,observed)
        self.assertIn("NOT_VALIDATED",report)
        self.assertIn("SEC_UNVERIFIED",report)
        self.assertNotIn("실전 매수 가능",report)


if __name__=="__main__":
    unittest.main()
