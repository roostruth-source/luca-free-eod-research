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
    # Do not trust an independently supplied coverage report if it was changed.
    if coverage!=checked:
        raise ValueError("SECOND_COMPARISON_REPORT_DRIFT")
    quality=summarize(frozen,review,outcomes,reference)
    if quality["validation_status"]!="NOT_VALIDATED" or quality["real_trades_allowed"] is not False:
        raise ValueError("UNSAFE_SECOND_QUALITY")
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
        f"- 신호 이후 5·15·30·60분: {EVIDENCE[quality['signal_outcome_evidence']]}",
        f"- 같은 T0 전체 후보 고정시각 비교: {EVIDENCE[quality['fixed_clock_reference_evidence']]}",
        "",
        "## 2차 후보별 실제 데이터 상태",
    ]
    for row in quality["rows"]:
        lines.append(f"- {row['symbol']}: {STATUS[row['initial_pattern_status']]}; IEX 분봉 {row['first_window_bars_observed']}/{row['first_window_minutes_expected']}; D등급(매수 불가)")
    lines += [
        "",
        "## 반드시 지킬 해석",
        "- 두 번의 관찰만으로 급등 예측 정확도, 승률, 실제 수익률을 계산할 수 없습니다.",
        "- IEX는 미국 전체 거래소 통합 시세가 아닙니다. 누락 분봉 원인은 확인되지 않았습니다.",
        "- 관찰된 패턴은 실제 체결 가능한 매수 신호가 아닙니다. 호가 차이·수수료·미끄러짐을 검증하지 않았습니다.",
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
