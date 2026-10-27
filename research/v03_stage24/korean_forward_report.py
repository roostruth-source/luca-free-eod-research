"""LUCA V0.3: concise Korean evidence report from verified prospective files.

This report is not an alert, trading signal, market prediction, or live execution.
It can only be generated from a successful GitHub source run with matching T0.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from followup_bridge import validate_github_run
from evidence_quality_gate import summarize
from source_run_inventory import SOURCE_WORKFLOW

STATUS={
    "PATTERN_RECORDED":"초기 연구 패턴 기록(급등 성공 아님)",
    "NO_PATTERN_OBSERVED":"관찰봉 완전·패턴 없음(급등 실패 판정 아님)",
    "NO_PATTERN_WITH_GAPS":"분봉 누락·패턴 미관측(판정 불가)",
    "NO_IEX_BARS":"IEX 분봉 0개(판정 불가)",
}
OUTCOMES={
    "AWAITING_OR_UNAVAILABLE":"후속 실측 미확인",
    "OBSERVED_PARTIAL_IEX":"후속 분봉 일부만 확인",
    "OBSERVED_COMPLETE_IEX_ONLY":"후속 IEX 분봉 확인(실제 체결 아님)",
}


def korean_report(source_metadata, frozen, review, outcomes=None, reference=None):
    if type(source_metadata) is not dict:
        raise ValueError("INVALID_SOURCE_METADATA")
    rid=source_metadata.get("databaseId")
    if type(rid) is not int or rid<=0:
        raise ValueError("INVALID_SOURCE_RUN_ID")
    approved=validate_github_run(source_metadata,rid)
    quality=summarize(frozen,review,outcomes,reference)
    if approved["real_trades_allowed"] is not False or quality["real_trades_allowed"] is not False:
        raise ValueError("UNSAFE_TRADE_CLAIM")
    if quality["validation_status"]!="NOT_VALIDATED" or quality["sec_status"]!="SEC_UNVERIFIED":
        raise ValueError("UNSAFE_RESEARCH_CLAIM")
    if quality["prediction_accuracy_verified"] is not False:
        raise ValueError("FALSE_PREDICTION_CLAIM")
    lines=[
        "# 루카 V0.3 첫 전향 실측 결과 (연구 전용)",
        "",
        f"- 원본 GitHub 실행: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/{rid}",
        f"- T0 후보 확정 시각(UTC): {quality['frozen_at_utc']}",
        f"- T0 원본 해시: \`{quality['frozen_t0_sha256']}\`",
        f"- T0 고정 후보: {quality['candidates_frozen']}종목",
        f"- 실제 확인한 IEX 1분봉: {quality['forward_iex_bars_observed']}개",
        f"- 초기 연구 패턴 기록: {quality['pattern_observed_symbols']}종목",
        f"- 첫 관찰 분봉 누락: {quality['first_window_sparse_symbols']}종목",
        f"- 신호 이후 5·15·30·60분: {OUTCOMES[quality['signal_outcome_evidence']]}",
        f"- 같은 T0 전체 후보 고정시각 비교: {OUTCOMES[quality['fixed_clock_reference_evidence']]}",
        "",
        "## 후보별 자료 상태",
    ]
    if not quality["rows"]:
        lines.append("- 후보 없음. 시장 전체에 기회가 없었다는 뜻은 아닙니다.")
    for row in quality["rows"]:
        status=STATUS[row["initial_pattern_status"]]
        lines.append(f"- {row['symbol']}: {status}; 분봉 {row['first_window_bars_observed']}/{row['first_window_minutes_expected']}; 등급 D(매수 금지)")
    lines+=["","## 해석할 때 반드시 지킬 점",
        "- 이 연구의 패턴은 급등 예측 확률, 매수 신호, 실제 수익을 뜻하지 않습니다.",
        "- IEX는 미국 전체 거래소 가격이 아닙니다. 누락된 분봉을 수익률 0%로 처리하지 않습니다.",
        "- SEC 증자·전환사채, Float, 시총, 전체 호가·체결 비용을 검증하지 못했습니다.",
        "- 연구 판정: NOT_VALIDATED / SEC_UNVERIFIED / A·B·C 0개 / 실제 주문 금지.",
        "- 이 파일은 검증된 원본의 읽기 전용 보고서이며 알림을 보내지 않습니다.",
        ""]
    return "\n".join(lines)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--metadata",required=True)
    p.add_argument("--source-dir",required=True)
    p.add_argument("--outcomes")
    p.add_argument("--reference")
    p.add_argument("--output",required=True)
    args=p.parse_args()
    def read(path):
        path=Path(path)
        if path.stat().st_size>2_000_000:
            raise ValueError("INPUT_TOO_LARGE")
        return json.loads(path.read_text(encoding="utf8"))
    def optional(path):
        return read(path) if path and Path(path).is_file() else None
    root=Path(args.source_dir)
    report=korean_report(read(args.metadata),read(root/"frozen_t0.json"),
                         read(root/"forward_review.json"),
                         optional(args.outcomes),optional(args.reference))
    out=Path(args.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf8") as f:
        f.write(report)
    print("KOREAN_EVIDENCE_REPORT_WRITTEN; NOT_VALIDATED; NO_ORDERS")


if __name__=="__main__":
    main()
