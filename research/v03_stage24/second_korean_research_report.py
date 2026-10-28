"""Second prospective session: Korean research-only report from verified evidence.

Not an alert, trading advice, success-rate estimate, or actual trade outcome.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from second_trial_artifact_bridge import verify_second_run
from evidence_quality_gate import summarize
from first_iex_baseline_integrity import load_verified
from two_session_iex_comparison import compare
from second_six_minute_evaluability import assess_six_minute_evaluability

STATUS={
    "PATTERN_RECORDED":"초기 연구 패턴 기록(급등 성공 아님)",
    "NO_PATTERN_OBSERVED":"IEX 분봉 완전·패턴 없음",
    "NO_PATTERN_WITH_GAPS":"IEX 분봉 누락·패턴 미관측(판정 불가)",
    "NO_IEX_BARS":"IEX 분봉 없음(판정 불가)",
}
EVIDENCE={
    "AWAITING_OR_UNAVAILABLE":"후속 관찰 자료 없음",
    "OBSERVED_PARTIAL_IEX":"후속 IEX 자료 일부만 확인",
    "OBSERVED_COMPLETE_IEX_ONLY":"후속 IEX 분봉 확인(실제 체결 아님)",
}


def report_korean_second(meta,frozen,review,provenance,coverage,outcomes=None,reference=None):
    rid=verify_second_run(meta)
    checked=compare(load_verified(),frozen,review,provenance,rid)
    # The authenticated GitHub bridge adds source/artifact identity flags to
    # the strict numerical comparison. Compare ALL strict fields while requiring
    # the additional source checks, rather than rejecting valid bridge output.
    if type(coverage) is not dict or any(coverage.get(k)!=v for k,v in checked.items()):
        raise ValueError("SECOND_COMPARISON_REPORT_DRIFT")
    if (coverage.get("second_source_workflow_verified") is not True or
        coverage.get("second_artifact_metadata_verified") is not True or
        coverage.get("first_audit_source_run_id")!=40532482508 or
        coverage.get("not_a_prediction_win_rate") is not True):
        raise ValueError("SECOND_COMPARISON_SOURCE_UNVERIFIED")
    quality=summarize(frozen,review,outcomes,reference)
    if quality["validation_status"]!="NOT_VALIDATED" or quality["real_trades_allowed"] is not False:
        raise ValueError("UNSAFE_SECOND_QUALITY")
    observability=assess_six_minute_evaluability(frozen,review,provenance,rid)
    first,second=checked["first"],checked["second"]
    lines=[
        "# 루카 V0.3 두 번째 실제 장중 실측 — 연구 결과",
        "",
        f"- 원본 2차 실행: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/{rid}",
        f"- 2차 T0(UTC): {quality['frozen_at_utc']}",
        f"- 2차 T0 해시: `{quality['frozen_t0_sha256']}`",
        f"- 1차 IEX 수집: {first['observed']}/{first['expected']}개 ({first['presence_pct']:.2f}%)",
        f"- 2차 IEX 수집: {second['observed']}/{second['expected']}개 ({second['presence_pct']:.2f}%)",
        f"- 수집률 차이: {checked['presence_change_percentage_points']:+.2f}%p (종목과 관찰 구간이 달라 직접적인 개선 증거 아님)",
        f"- 2차 후보: {second['symbols']}종목, 전조 패턴 관측: {quality['pattern_observed_symbols']}종목",
        f"- 2차 초기 관찰 분봉 누락: {quality['first_window_sparse_symbols']}종목",
        f"- 실제 전조 검사 가능: {observability['evaluable_symbols']}/{observability['candidate_count']}종목 (6분 연속 자료가 1구간 이상 있는 종목)",
        f"- 실제 전조 검사 불가: {observability['not_evaluable_symbols']}종목 (6분 연속 자료 부족)",
        f"- 검사 가능한 6분 구간: {observability['evaluable_windows']}/{observability['possible_windows']}개 (같은 종목의 겹치는 구간 포함)",
        f"- 신호 이후 5·15·30·60분: {EVIDENCE[quality['signal_outcome_evidence']]}",
        f"- 같은 T0 전체 후보 고정시각 비교: {EVIDENCE[quality['fixed_clock_reference_evidence']]}",
        "",
        "## 2차 후보별 실제 데이터 상태",
    ]
    for row,availability in zip(quality["rows"],observability["rows"]):
        if row["symbol"]!=availability["symbol"]:
            raise ValueError("EVALUABILITY_UNIVERSE_DRIFT")
        windows=availability["evaluable_six_minute_windows"]
        if row["pattern_count"]>0:
            description="전조 기록(해당 시각의 6분 연속 자료 확인, 가격·거래량 원본은 재계산 못함)"
        elif windows==0:
            description="전조 검사 불가(6분 연속 분봉 없음)"
        else:
            description="검사 가능·해당 패턴 미관측(급등이 없었다는 뜻 아님)"
        lines.append(f"- {row['symbol']}: {description}; IEX 분봉 {row['first_window_bars_observed']}/{row['first_window_minutes_expected']}; "
                     f"가장 긴 연속 기록 {availability['longest_contiguous_minutes']}분; 검사 가능 6분 구간 {windows}개; D등급(매수 불가)")
    lines += [
        "",
        "## 전조 발견 뒤 5·15·30·60분 관찰 (실제 체결 수익 아님)",
    ]
    if quality["pattern_observed_symbols"]==0:
        lines.append("- 전조 기록 0종목: 전조 이후 결과를 계산할 대상이 없습니다. 급등 기회가 없었다는 뜻은 아닙니다.")
    elif outcomes is None:
        lines.append("- 전조 기록은 있지만 후속 관찰 자료가 없습니다. 주가 변화는 미확인입니다(0%로 계산하지 않음).")
    else:
        # summarize() above has already enforced same T0, exact signal symbols,
        # 60m maturity, all horizons, safe grades and non-executable returns.
        records={record["symbol"]:record for record in outcomes["signals"]}
        for row in quality["rows"]:
            sym=row["symbol"]
            if row["pattern_count"]==0:
                continue
            record=records[sym]
            formatted=[]
            for h in record["horizons"]:
                n=h["horizon_minutes"]
                if h["status"]=="COMPLETE_IEX_PRICES_ONLY":
                    pct=h["theoretical_iex_open_to_close_pct"]
                    formatted.append(f"{n}분: IEX 가정상 가격 변화 {pct:+.2f}% (자료 완전, 실제 매매 아님)")
                else:
                    formatted.append(f"{n}분: 관찰 불완전 {h['observed_bars']}/{h['expected_bars']}개 (가격 변화 판정 불가)")
            lines.append(f"- {sym}: "+"; ".join(formatted))
    lines += [
        "",
        "## 전체 후보의 고정시각 참고 관찰 (급등 전조의 효과를 증명하지 않음)",
    ]
    if reference is None:
        lines.append("- 공통 시각부터 관찰한 참고 자료가 없습니다. 비교 결과는 미확인입니다.")
    else:
        for minutes in (5,15,30,60):
            complete=sum(
                any(h["horizon_minutes"]==minutes and h["status"]=="COMPLETE_IEX_PRICES_ONLY"
                    for h in record["horizons"])
                for record in reference["rows"]
            )
            lines.append(f"- {minutes}분 자료 완전: {complete}/{len(reference['rows'])}종목 (단일 IEX 거래소 자료, 매매 성과 아님)")
    lines += [
        "",
        "## 반드시 지킬 해석",
        "- 두 번의 관찰만으로 급등 예측 정확도, 승률, 실제 수익률을 계산할 수 없습니다.",
        "- IEX는 미국 전체 거래소 통합 시세가 아닙니다. 누락 분봉 원인은 확인되지 않았습니다.",
        "- 자료가 6개 이상이어도 분 단위로 연속하지 않으면 전조를 검사할 수 없습니다.",
        "- 전조 기록은 해당 시각의 6분 연속 자료 존재만 대조했습니다. 보관된 자료에는 원본 가격·거래량이 없어 전조 계산식 자체는 재검산할 수 없습니다.",
        "- 검사가 가능했는데 패턴이 없었던 종목도 미래에 급등하지 않는다는 뜻이 아닙니다.",
        "- 관찰된 패턴은 실제 체결 가능한 매수 신호가 아닙니다. 호가 차이·수수료·미끄러짐을 검증하지 않았습니다.",
        "- 가정상 가격 변화는 특정 IEX 1분봉의 시가·종가를 단순 비교한 숫자입니다. 실제 호가에서 사거나 팔 수 있었다는 증거가 아닙니다.",
        "- SEC 증자·전환사채·워런트, Float, 시총과 실제 매도 가능 물량은 확인되지 않았습니다.",
        "- 연구 상태: NOT_VALIDATED / SEC_UNVERIFIED / 모든 후보 D등급 / 실제 주문 금지.",
        "- 이 파일은 검증된 연구 기록을 요약한 것이며 자동 알림을 보내지 않습니다.",
        "",
    ]
    return "\n".join(lines)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--metadata",required=True)
    p.add_argument("--source-dir",required=True)
    p.add_argument("--comparison",required=True)
    p.add_argument("--outcomes")
    p.add_argument("--reference")
    p.add_argument("--output",required=True)
    args=p.parse_args()
    def load(path):
        f=Path(path)
        if not f.is_file() or f.stat().st_size>2_000_000:
            raise ValueError("MISSING_OR_OVERSIZE_EVIDENCE")
        return json.loads(f.read_text(encoding="utf8"))
    def optional(path):
        return load(path) if path and Path(path).is_file() else None
    root=Path(args.source_dir)
    report=report_korean_second(
        load(args.metadata),load(root/"frozen_t0.json"),load(root/"forward_review.json"),
        load(root/"iex_timestamp_provenance.json"),load(args.comparison),
        optional(args.outcomes),optional(args.reference))
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf8") as f:
        f.write(report)
    print("SECOND_KOREAN_RESEARCH_REPORT_WRITTEN; NOT_VALIDATED; NO_ORDERS")


if __name__=="__main__":
    main()
