"""Offline-only Korean 5/15/30/60m evidence display, never actual fills."""
import copy
import datetime as dt
import unittest

from test_second_trial_artifact_bridge import META,ART
from test_two_session_iex_comparison import fixture
from second_trial_artifact_bridge import build_verified_comparison
from first_iex_baseline_integrity import load_verified
from second_korean_research_report import report_korean_second
from forward_outcomes_iex import validate_origins,build_report
from fixed_clock_reference import fixed_reference_entries,prepare_result
from test_second_followup_full_cli_integration import fake_bars

UTC=dt.timezone.utc

class HorizonDetailsTests(unittest.TestCase):
    def setUp(self):
        self.meta=copy.deepcopy(META)
        self.art=copy.deepcopy(ART)
        self.f,self.r,self.p=fixture()
        self.comparison=build_verified_comparison(load_verified(),self.meta,self.f,self.r,self.p,self.art)
        self.t0,self.reviewed,self.entries=validate_origins(self.f,self.r)
        self.later=self.t0+dt.timedelta(minutes=100)

    def report(self,outcomes=None,reference=None):
        return report_korean_second(self.meta,self.f,self.r,self.p,self.comparison,outcomes,reference)

    def outcomes(self,missing=()):
        return build_report(self.f,self.r,{
            sym:[row for i,row in enumerate(fake_bars(when)) if i not in missing]
            for sym,when in self.entries.items()
        },self.later)

    def reference(self,missing=()):
        return prepare_result(self.f,self.r,{
            sym:[row for i,row in enumerate(fake_bars(when)) if i not in missing]
            for sym,when in fixed_reference_entries(self.f,self.r).items()
        },self.later)

    def test_all_complete_shows_each_horizon_as_hypothetical_only(self):
        s=self.report(self.outcomes(),self.reference())
        for n in (5,15,30,60):
            self.assertIn(f"{n}분: IEX 가정상 가격 변화 +5.00%",s)
            self.assertIn(f"{n}분 자료 완전: 1/1종목",s)
        self.assertIn("실제 매매 아님",s)
        self.assertIn("호가",s)
        self.assertIn("실제 주문 금지",s)
        self.assertNotIn("실현 수익",s)

    def test_one_missing_bar_keeps_5m_but_withholds_15_30_60(self):
        s=self.report(self.outcomes(missing=(7,)),self.reference())
        self.assertIn("5분: IEX 가정상 가격 변화 +5.00%",s)
        for n in (15,30,60):
            self.assertIn(f"{n}분: 관찰 불완전 {n-1}/{n}개 (가격 변화 판정 불가)",s)
        self.assertNotIn("15분: IEX 가정상 가격 변화",s)
        self.assertNotIn("30분: IEX 가정상 가격 변화",s)
        self.assertNotIn("60분: IEX 가정상 가격 변화",s)

    def test_no_followup_is_unknown_not_zero_return(self):
        s=self.report()
        self.assertIn("주가 변화는 미확인입니다(0%로 계산하지 않음)",s)
        self.assertIn("공통 시각부터 관찰한 참고 자료가 없습니다",s)
        self.assertNotIn("IEX 가정상 가격 변화",s)

    def test_no_signals_has_no_fake_outcomes(self):
        self.f,self.r,self.p=fixture(())
        self.comparison=build_verified_comparison(load_verified(),self.meta,self.f,self.r,self.p,self.art)
        s=self.report(reference=self.reference())
        self.assertIn("전조 기록 0종목: 전조 이후 결과를 계산할 대상이 없습니다",s)
        self.assertNotIn("IEX 가정상 가격 변화",s)

    def test_sparse_reference_counts_only_complete_per_horizon(self):
        s=self.report(self.outcomes(),self.reference(missing=(7,)))
        self.assertIn("5분 자료 완전: 1/1종목",s)
        for n in (15,30,60):
            self.assertIn(f"{n}분 자료 완전: 0/1종목",s)

    def test_forged_complete_horizon_rejected_by_quality(self):
        wrong=self.outcomes(missing=(7,))
        wrong["signals"][0]["horizons"][1]["status"]="COMPLETE_IEX_PRICES_ONLY"
        wrong["signals"][0]["horizons"][1]["theoretical_iex_open_to_close_pct"]=9.5
        with self.assertRaises(ValueError):
            self.report(wrong)

if __name__=="__main__":
    unittest.main()
