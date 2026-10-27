"""Synthetic second Korean report regression tests; no market data calls."""
import copy
import unittest
from second_korean_research_report import report_korean_second
from two_session_iex_comparison import compare
from first_iex_baseline_integrity import load_verified
from test_second_trial_artifact_bridge import META,SECOND_ID
from test_two_session_iex_comparison import fixture


class SecondKoreanReportTests(unittest.TestCase):
    def setUp(self):
        self.meta=copy.deepcopy(META)
        self.f,self.r,self.p=fixture()
        self.coverage=compare(load_verified(),self.f,self.r,self.p,SECOND_ID)

    def report(self,**changes):
        data=dict(meta=self.meta,frozen=self.f,review=self.r,
                  provenance=self.p,coverage=self.coverage)
        data.update(changes)
        return report_korean_second(**data)

    def test_korean_real_coverage_and_no_trading(self):
        s=self.report()
        self.assertIn("1차 IEX 수집: 94/168개 (55.95%)",s)
        self.assertIn("2차 IEX 수집: 9/15개 (60.00%)",s)
        self.assertIn("수집률 차이: +4.05%p",s)
        self.assertIn("D등급(매수 불가)",s)
        self.assertIn("NOT_VALIDATED",s)
        self.assertIn("실제 주문 금지",s)

    def test_no_signal_no_fake_wins(self):
        s=self.report()
        self.assertIn("전조 패턴 관측: 0종목",s)
        self.assertIn("후속 관찰 자료 없음",s)
        self.assertNotIn("승률 100%",s)

    def test_changed_coverage_rejected(self):
        self.coverage["second"]["observed"]=10
        with self.assertRaisesRegex(ValueError,"SECOND_COMPARISON_REPORT_DRIFT"):
            self.report()

    def test_changed_source_rejected(self):
        self.meta["conclusion"]="failure"
        with self.assertRaisesRegex(ValueError,"SECOND_RUN_NOT_SUCCESSFUL"):
            self.report()

    def test_changed_provenance_rejected(self):
        self.p["rows"][0]["missing_iex_bar_start_utc"]=[]
        with self.assertRaisesRegex(ValueError,"INCONSISTENT_TIMESTAMP_GRID"):
            self.report()

    def test_changed_t0_rejected(self):
        self.f["selected_at_utc"]="2026-10-28T14:40:00+00:00"
        with self.assertRaisesRegex(ValueError,"T0_HASH_MISMATCH"):
            self.report()

    def test_unsafe_grade_rejected(self):
        self.r["results"][0]["grade"]="A"
        with self.assertRaisesRegex(ValueError,"UNSAFE_RESEARCH_GRADE"):
            self.report()

    def test_missing_bar_is_not_declared_failure(self):
        s=self.report()
        self.assertIn("분봉 누락·패턴 미관측(판정 불가)",s)
        self.assertIn("누락 분봉 원인은 확인되지 않았습니다",s)

if __name__=="__main__":
    unittest.main()
