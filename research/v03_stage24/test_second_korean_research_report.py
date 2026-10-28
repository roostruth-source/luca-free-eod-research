"""Synthetic second Korean report regression tests; no market data calls."""
import copy
import unittest
from second_korean_research_report import report_korean_second
from second_trial_artifact_bridge import build_verified_comparison
from test_second_trial_artifact_bridge import ART
from first_iex_baseline_integrity import load_verified
from test_second_trial_artifact_bridge import META,SECOND_ID
from test_two_session_iex_comparison import fixture


class SecondKoreanReportTests(unittest.TestCase):
    def setUp(self):
        self.meta=copy.deepcopy(META)
        self.f,self.r,self.p=fixture()
        self.coverage=build_verified_comparison(load_verified(),self.meta,self.f,self.r,self.p,ART)

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
        self.assertIn("실제 전조 검사 가능: 1/1종목",s)
        self.assertIn("검사 가능한 6분 구간: 1/10개",s)
        self.assertIn("D등급(매수 불가)",s)
        self.assertIn("NOT_VALIDATED",s)
        self.assertIn("실제 주문 금지",s)

    def test_signal_report_discloses_timestamp_only_not_recomputed_price(self):
        s=self.report()
        self.assertIn("해당 시각의 6분 연속 자료 확인",s)
        self.assertIn("가격·거래량 원본은 재계산 못함",s)
        self.assertIn("전조 계산식 자체는 재검산할 수 없습니다",s)

    def test_no_signal_no_fake_wins(self):
        self.f,self.r,self.p=fixture(())
        self.coverage=build_verified_comparison(load_verified(),self.meta,self.f,self.r,self.p,ART)
        s=self.report()
        self.assertIn("전조 패턴 관측: 0종목",s)
        self.assertIn("실제 전조 검사 불가: 1종목",s)
        self.assertIn("후속 관찰 자료 없음",s)
        self.assertNotIn("승률 100%",s)

    def test_six_disconnected_bars_are_not_six_minute_window(self):
        self.f,self.r,self.p=fixture((0,2,4,6,8,10))
        self.coverage=build_verified_comparison(load_verified(),self.meta,self.f,self.r,self.p,ART)
        s=self.report()
        self.assertIn("IEX 분봉 6/15",s)
        self.assertIn("전조 검사 불가(6분 연속 분봉 없음)",s)
        self.assertIn("실제 전조 검사 불가: 1종목",s)
        self.assertNotIn("급등 성공",s)

    def test_six_contiguous_without_pattern_is_evaluable_not_failure(self):
        self.f,self.r,self.p=fixture((6,7,8,9,10,11))
        self.coverage=build_verified_comparison(load_verified(),self.meta,self.f,self.r,self.p,ART)
        s=self.report()
        self.assertIn("실제 전조 검사 가능: 1/1종목",s)
        self.assertIn("검사 가능·해당 패턴 미관측",s)
        self.assertIn("급등이 없었다는 뜻 아님",s)

    def test_valid_bridge_metadata_is_not_false_rejected(self):
        s=self.report()
        self.assertIn("2차 IEX 수집:",s)
        self.assertIn("실제 주문 금지",s)

    def test_unverified_artifact_flag_rejected(self):
        self.coverage["second_artifact_metadata_verified"]=False
        with self.assertRaisesRegex(ValueError,"SECOND_COMPARISON_SOURCE_UNVERIFIED"):
            self.report()

    def test_unverified_source_workflow_flag_rejected(self):
        self.coverage["second_source_workflow_verified"]=False
        with self.assertRaisesRegex(ValueError,"SECOND_COMPARISON_SOURCE_UNVERIFIED"):
            self.report()

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
        self.f,self.r,self.p=fixture((0,1,2))
        self.coverage=build_verified_comparison(load_verified(),self.meta,self.f,self.r,self.p,ART)
        s=self.report()
        self.assertIn("전조 검사 불가(6분 연속 분봉 없음)",s)
        self.assertIn("누락 분봉 원인은 확인되지 않았습니다",s)

if __name__=="__main__":
    unittest.main()
