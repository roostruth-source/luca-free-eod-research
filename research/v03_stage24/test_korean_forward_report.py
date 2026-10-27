"""Korean prospective evidence reporting, offline fixtures only."""
import copy
import unittest

from korean_forward_report import korean_report
from test_fixed_clock_reference import pair,prices,READY
from test_forward_outcomes_iex import bars,LATER
from forward_outcomes_iex import build_report
from fixed_clock_reference import prepare_result
from followup_bridge import RUN_WORKFLOW,RESEARCH_BRANCH

META={"databaseId":40490000001,"name":RUN_WORKFLOW,"headBranch":RESEARCH_BRANCH,
      "event":"push","status":"completed","conclusion":"success"}


class KoreanReportTests(unittest.TestCase):
    def test_verified_source_korean_summary(self):
        f,r=pair()
        s=korean_report(META,f,r)
        self.assertIn("40490000001",s)
        self.assertIn("초기 연구 패턴 기록: 1종목",s)
        self.assertIn("첫 관찰 분봉 누락: 2종목",s)
        self.assertIn("후속 실측 미확인",s)
        self.assertIn("NOT_VALIDATED",s)
        self.assertIn("실제 주문 금지",s)

    def test_valid_full_forward_and_reference(self):
        f,r=pair()
        o=build_report(f,r,{"GPUS":bars()},LATER)
        b=prepare_result(f,r,{"GPUS":prices(),"LAES":prices()},READY)
        s=korean_report(META,f,r,o,b)
        self.assertIn("후속 IEX 분봉 확인(실제 체결 아님)",s)
        self.assertIn("같은 T0 전체 후보",s)

    def test_no_pattern_not_declared_market_failure(self):
        f,r=pair()
        r["results"][0]["pattern_count"]=0
        r["results"][0]["first_pattern"]=None
        s=korean_report(META,f,r)
        self.assertIn("초기 연구 패턴 기록: 0종목",s)
        self.assertIn("급등 실패 판정 아님",s)
        self.assertNotIn("0% 수익",s)

    def test_no_bars_is_unavailable_not_zero_return(self):
        f,r=pair()
        r["results"][1]["observed_iex_bars"]=0
        s=korean_report(META,f,r)
        self.assertIn("IEX 분봉 0개(판정 불가)",s)

    def test_no_frozen_candidates(self):
        f,r=pair()
        f["candidates"]=[]
        f["candidate_count"]=0
        from prospective_iex_research import digest_frozen
        f["sha256"]=digest_frozen(f)
        r["symbols"]=0
        r["results"]=[]
        r["observed_iex_bars"]=0
        r["forward_pattern_symbols"]=0
        s=korean_report(META,f,r)
        self.assertIn("후보 없음",s)

    def test_forged_source_run_id_rejected(self):
        m=copy.deepcopy(META);m["databaseId"]="40490000001"
        f,r=pair()
        with self.assertRaisesRegex(ValueError,"INVALID_SOURCE_RUN_ID"):
            korean_report(m,f,r)

    def test_failed_source_run_rejected(self):
        m=copy.deepcopy(META);m["conclusion"]="failure"
        f,r=pair()
        with self.assertRaisesRegex(ValueError,"PROSPECTIVE_RUN_NOT_SUCCESSFUL"):
            korean_report(m,f,r)

    def test_wrong_workflow_rejected(self):
        m=copy.deepcopy(META);m["name"]="Production"
        f,r=pair()
        with self.assertRaisesRegex(ValueError,"WRONG_WORKFLOW"):
            korean_report(m,f,r)

    def test_wrong_branch_rejected(self):
        m=copy.deepcopy(META);m["headBranch"]="main"
        f,r=pair()
        with self.assertRaisesRegex(ValueError,"WRONG_BRANCH_OR_EVENT"):
            korean_report(m,f,r)

    def test_tampered_t0_rejected(self):
        f,r=pair()
        f["selected_at_utc"]="2026-10-27T13:50:00+00:00"
        with self.assertRaisesRegex(ValueError,"FROZEN_HASH_MISMATCH"):
            korean_report(META,f,r)

    def test_unrelated_outcome_rejected(self):
        f,r=pair()
        o=build_report(f,r,{"GPUS":bars()},LATER)
        o["frozen_t0_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"OUTCOMES_FROM_ANOTHER_T0"):
            korean_report(META,f,r,o)

    def test_unrelated_reference_rejected(self):
        f,r=pair()
        b=prepare_result(f,r,{"GPUS":prices(),"LAES":prices()},READY)
        b["freeze_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"REFERENCE_FROM_ANOTHER_T0"):
            korean_report(META,f,r,reference=b)

    def test_forged_buy_grade_rejected(self):
        f,r=pair()
        r["results"][0]["grade"]="A"
        with self.assertRaisesRegex(ValueError,"UNSAFE_REVIEW_ROW"):
            korean_report(META,f,r)

    def test_report_never_promises_success_rate(self):
        f,r=pair()
        s=korean_report(META,f,r)
        self.assertNotIn("승률 100%",s)
        self.assertNotIn("실전 매수 가능",s)
        self.assertIn("매수 금지",s)

if __name__=="__main__":
    unittest.main()
