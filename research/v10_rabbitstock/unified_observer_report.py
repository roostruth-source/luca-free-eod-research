"""Build one self-contained Korean LUCA V10 observation report.

This joins already-produced research artifacts.  It never calls a market API,
changes the detector, or creates an order path.
"""

from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
import math
from pathlib import Path

from prospective_outcomes import BLOCKER_KO


EXPECTED_SCHEMAS = {
    "live": "LUCA_V10_LIVE_WATCHLIST_1",
    "outcomes": "LUCA_V10_PROSPECTIVE_OUTCOMES_1",
    "validation": "LUCA_V10_REFERENCE_VALIDATION_1",
}

RISK_KO = {
    "SEC_UNVERIFIED": "SEC 공시 원문을 확인하지 못함",
    "FLOAT_UNVERIFIED": "Float(유통주식 수)를 공식 자료로 확인하지 못함",
    "PRICE_STALE_OR_MISSING": "가격이 오래됐거나 없음",
    "IEX_SPREAD_UNKNOWN": "매수·매도 호가 차이를 확인하지 못함",
    "WIDE_IEX_SPREAD": "Spread(매수·매도 호가 차이)가 큼",
    "WIDE_IEX_SPREAD_PRIORITY_CAPPED": "호가 차이가 커 관찰 우선순위를 낮춤",
    "EXTREME_IEX_SPREAD_PRIORITY_CAPPED": "호가 차이가 매우 커 관찰 우선순위를 제한함",
    "VOLUME_FIRST_NOT_CONFIRMED": "거래량 선행 증가를 확인하지 못함",
    "PREMARKET_VOLUME_FIRST_UNVERIFIED": "장전 거래량 선행 증가를 검증하지 못함",
    "PREMARKET_SCREENER_RANK_SESSION_UNVERIFIED": "검색 순위가 장전 자료인지 확인하지 못함",
    "PREMARKET_SINGLE_EXCHANGE_CONTEXT": "장전 IEX 한 거래소 자료만 사용함",
}


def _safe_input(name: str, report: dict) -> None:
    if not isinstance(report, dict) or report.get("schema_version") != EXPECTED_SCHEMAS[name]:
        raise ValueError(f"invalid_{name}_schema")
    if (report.get("WATCH_ONLY") is not True
            or report.get("NO_ORDERS") is not True
            or report.get("validation_status") != "NOT_VALIDATED"):
        raise ValueError(f"unsafe_{name}_report")


def validate_inputs(live: dict, outcomes: dict, validation: dict) -> None:
    _safe_input("live", live)
    _safe_input("outcomes", outcomes)
    _safe_input("validation", validation)
    rows = live.get("rows")
    if not isinstance(rows, list) or live.get("candidate_count") != len(rows):
        raise ValueError("candidate_count_mismatch")
    for row in rows:
        if not isinstance(row, dict) or row.get("NO_ORDERS") is not True:
            raise ValueError("unsafe_candidate_row")
        if row.get("buy_allowed") is not False:
            raise ValueError("candidate_buy_flag_not_forced_false")
        if row.get("priority_is_buy_signal") is not False:
            raise ValueError("candidate_priority_misrepresented")
        if not isinstance(row.get("risk_flags"), list):
            raise ValueError("candidate_risks_missing")
    if (outcomes.get("prediction_accuracy_verified") is not False
            or outcomes.get("performance_validation_ready") is not False):
        raise ValueError("unvalidated_performance_claim")
    if validation.get("trade_accuracy_validated") is not False:
        raise ValueError("unvalidated_trade_accuracy_claim")


def _pct(value) -> str:
    if type(value) not in (int, float) or not math.isfinite(value):
        return "표본 없음"
    return f"{value:.1f}%"


def _number(value) -> str:
    if type(value) is int:
        return f"{value:,}"
    return "0"


def _risk_text(code: str) -> str:
    return RISK_KO.get(code, "추가 확인 필요")


def _candidate_cards(live: dict) -> str:
    collected_at = live.get("collected_at", "미확인")
    cards = []
    for row in live["rows"]:
        ticker = escape(str(row.get("ticker", "UNKNOWN")))
        label = str(row.get("research_priority_label", "HOLD_UNVERIFIED"))
        css = "watch" if not label.startswith("HOLD_") else "hold"
        reasons = row.get("priority_reasons") or []
        reason_text = "".join(
            f"<li>{escape(str(item.get('ko', item.get('code', '근거 미확인'))))}</li>"
            for item in reasons if isinstance(item, dict)
        ) or "<li>확정된 관찰 근거 없음</li>"
        risk_text = "".join(
            f"<li><code>{escape(str(code))}</code> — {escape(_risk_text(str(code)))}</li>"
            for code in row["risk_flags"]
        ) or "<li>표시된 위험 없음 — SEC·Float 미확인 상태는 별도 확인</li>"
        price = row.get("iex_price")
        price_text = f"${price:,.4f}" if type(price) in (int, float) and math.isfinite(price) else "미확인"
        spread = row.get("iex_quote_spread_pct")
        spread_text = _pct(spread)
        cards.append(f"""
<article class="candidate {css}">
  <div class="candidate-head"><div><span class="rank">#{escape(str(row.get('research_priority_rank', '?')))}</span>
  <h3>{ticker}</h3></div><div class="score">{escape(str(row.get('research_priority_score', 0)))}점</div></div>
  <p><b>{escape(str(row.get('research_priority_ko', label)))}</b> · 관찰 시각 {escape(str(collected_at))}</p>
  <div class="two"><div><b>관찰 이유</b><ul>{reason_text}</ul></div>
  <div><b>위험·자료 부족</b><ul>{risk_text}</ul></div></div>
  <p class="muted">IEX 참고가격 {escape(price_text)} · Spread(매수·매도 호가 차이) {escape(spread_text)} · {escape(str(row.get('detector_profile', 'NASDAQ_7_0')))}</p>
  <p class="warning">이 점수는 먼저 볼 순서이며 매수 점수나 주문 신호가 아닙니다.</p>
</article>""")
    return "".join(cards) or "<article><p>이번 실행에는 관찰 후보가 없습니다. 신호 없음도 정상 기록입니다.</p></article>"


def _performance_rows(outcomes: dict) -> str:
    scorecard = outcomes.get("descriptive_candidate_scorecard", {})
    rows = []
    for horizon in ("1", "3", "5", "10"):
        item = scorecard.get(horizon, {})
        hits = item.get("mfe_hit_rates_pct", {})
        rows.append(
            "<tr>"
            f"<td>{horizon}거래일</td>"
            f"<td>{_number(item.get('sample_size'))}</td>"
            f"<td>{escape(_pct(hits.get('5')))}</td>"
            f"<td>{escape(_pct(hits.get('10')))}</td>"
            f"<td>{escape(_pct(item.get('average_close_return_pct')))}</td>"
            f"<td>{escape(_pct(item.get('average_mae_pct')))}</td>"
            "</tr>"
        )
    return "".join(rows)


def _stress_rows(outcomes: dict) -> str:
    stress = outcomes.get("spread_friction_stress", {})
    scenarios = stress.get("scenarios", {})
    rows = []
    for code, label in (("HALF_SPREAD_ENTRY", "호가 차이 절반 부담"),
                        ("FULL_SPREAD_ENTRY", "호가 차이 전부 부담")):
        horizons = scenarios.get(code, {}).get("horizons", {})
        for horizon in ("1", "3", "5", "10"):
            item = horizons.get(horizon, {})
            rows.append(
                f"<tr><td>{label}</td><td>{horizon}거래일</td>"
                f"<td>{_number(item.get('sample_size'))}</td>"
                f"<td>{escape(_pct(item.get('average_close_return_pct')))}</td>"
                f"<td>{escape(_pct(item.get('positive_close_rate_pct')))}</td></tr>"
            )
    return "".join(rows)


def render_html(live: dict, outcomes: dict, validation: dict,
                provenance: dict[str, dict] | None = None) -> str:
    validate_inputs(live, outcomes, validation)
    horizons = outcomes.get("independent_mature_fresh_horizons", {})
    integrity = outcomes.get("daily_bar_integrity_guard", {})
    blockers = outcomes.get("readiness_blockers", [])
    blocker_rows = "".join(
        f"<li><code>{escape(str(code))}</code><br>{escape(BLOCKER_KO.get(str(code), '추가 확인이 필요한 제한'))}</li>"
        for code in blockers
    ) or "<li>표시된 차단 사유 없음</li>"
    label_counts = live.get("priority_summary", {})
    held = sum(count for label, count in label_counts.items()
               if str(label).startswith("HOLD_") and type(count) is int)
    prov_rows = "".join(
        f"<tr><td>{escape(name)}</td><td>{escape(str(item.get('file', '')))}</td>"
        f"<td><code>{escape(str(item.get('sha256', '')))}</code></td></tr>"
        for name, item in sorted((provenance or {}).items())
    ) or "<tr><td colspan='3'>파일 해시는 CLI 실행에서 기록됩니다.</td></tr>"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LUCA V10 통합 관찰 보고서</title>
<style>
:root{{--bg:#f4f6fa;--card:#fff;--ink:#172033;--muted:#637083;--line:#dce2ec;--red:#a12b2b;--blue:#165dbe}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 system-ui,-apple-system,sans-serif}}
main{{max-width:920px;margin:auto;padding:18px}}h1,h2,h3{{line-height:1.2}}h3{{font-size:25px;margin:3px 0}}section,article{{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:16px;margin:14px 0;overflow-wrap:anywhere}}
.safety{{background:#2c1720;color:#fff;border:0}}.safety strong{{color:#ffd2d2}}.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.metric{{background:#eef3fb;border-radius:12px;padding:12px}}.metric b{{display:block;color:var(--muted);font-size:13px}}.metric span{{font-size:24px;font-weight:800}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{border-bottom:1px solid var(--line);padding:9px;text-align:left;vertical-align:top}}th{{background:#f2f5fa}}code{{font-size:12px}}.candidate.watch{{border-left:6px solid var(--blue)}}.candidate.hold{{border-left:6px solid #8a94a5}}.candidate-head{{display:flex;justify-content:space-between;align-items:center}}.rank,.muted{{color:var(--muted)}}.score{{font-size:27px;font-weight:850}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.warning{{color:var(--red);font-weight:700}}details{{margin:12px 0}}.scroll{{overflow-x:auto}}ul{{padding-left:21px}}
@media(max-width:680px){{.grid{{grid-template-columns:1fr 1fr}}.two{{grid-template-columns:1fr}}th,td{{padding:7px 5px}}}}
</style></head><body><main>
<section class="safety"><h1>LUCA V10 통합 관찰 보고서</h1>
<p><strong>WATCH_ONLY · NOT_VALIDATED · SEC_UNVERIFIED · D · NO_ORDERS</strong></p>
<p>후보를 먼저 살펴보기 위한 연구 화면입니다. 매수 추천, 주문 승인, 수익 보장이 아닙니다.</p></section>

<section><h2>오늘 한눈에 보기</h2><div class="grid">
<div class="metric"><b>관찰 후보</b><span>{_number(live.get('candidate_count'))}</span></div>
<div class="metric"><b>자료 부족·보류</b><span>{held:,}</span></div>
<div class="metric"><b>독립 종목</b><span>{_number(outcomes.get('independent_fresh_ticker_count'))}</span></div>
<div class="metric"><b>5거래일 성숙</b><span>{_number(horizons.get('5'))}</span></div>
</div><p>수집 상태: <code>{escape(str(live.get('source_status', 'UNKNOWN')))}</code> · 자료 범위: {escape(str(live.get('coverage', '미확인')))}</p></section>

<section><h2>성과표 — 아직 예측 적중률이 아님</h2>
<p>MFE는 신호 뒤 한때 얼마나 올랐는지, MAE는 한때 얼마나 떨어졌는지를 뜻합니다. 5%·10%는 그 가격에 닿은 비율이며 실제 매도 수익률이 아닙니다.</p>
<div class="scroll"><table><thead><tr><th>기간</th><th>표본</th><th>한때 +5%</th><th>한때 +10%</th><th>평균 종가 변화</th><th>평균 최대 하락</th></tr></thead><tbody>{_performance_rows(outcomes)}</tbody></table></div>
<p class="warning">5거래일 독립 표본 30개와 공식 기업행사 가격 검증 전에는 성능을 검증했다고 말할 수 없습니다.</p></section>

<section><h2>거래비용 보수 가정</h2>
<p>저장 당시 IEX Spread(매수·매도 호가 차이)의 절반 또는 전부만큼 비싸게 들어갔다고 가정한 계산입니다. 실제 Fill(체결), Slippage(주문 미끄러짐), 수수료, 시장충격을 측정한 값은 아닙니다.</p>
<div class="scroll"><table><thead><tr><th>가정</th><th>기간</th><th>표본</th><th>평균 종가 변화</th><th>양수 비율</th></tr></thead><tbody>{_stress_rows(outcomes)}</tbody></table></div></section>

<section><h2>자료 누락과 검증 차단</h2><div class="grid">
<div class="metric"><b>원장 기록</b><span>{_number(outcomes.get('ledger_event_count'))}</span></div>
<div class="metric"><b>누락 기록</b><span>{_number(integrity.get('missing_trading_session_record_count'))}</span></div>
<div class="metric"><b>누락 고유 종목</b><span>{_number(integrity.get('missing_trading_session_unique_ticker_count'))}</span></div>
<div class="metric"><b>모델 대상 누락</b><span>{_number(integrity.get('model_eligible_missing_trading_session_unique_ticker_count'))}</span></div>
</div><ul>{blocker_rows}</ul>
<p>독립 두 출처로 재검증된 과거 사례: {_number(validation.get('verified_signals'))}개 · 상태: <code>{escape(str(validation.get('coverage_status', 'UNKNOWN')))}</code></p></section>

<section><h2>관찰 후보 전체</h2><p>신호가 약하거나 자료가 없는 종목도 숨기지 않고 함께 표시합니다.</p>{_candidate_cards(live)}</section>

<section><h2>입력 파일 무결성</h2><p>아래 SHA-256은 이 화면을 만든 원본 파일의 지문입니다. 파일이 바뀌면 지문도 달라집니다.</p>
<div class="scroll"><table><thead><tr><th>자료</th><th>파일</th><th>SHA-256</th></tr></thead><tbody>{prov_rows}</tbody></table></div></section>
</main></body></html>"""


def _load(path: Path) -> tuple[dict, dict]:
    raw = path.read_bytes()
    return json.loads(raw), {
        "file": path.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", type=Path, required=True)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    live, live_prov = _load(args.live)
    outcomes, outcomes_prov = _load(args.outcomes)
    validation, validation_prov = _load(args.validation)
    page = render_html(live, outcomes, validation, {
        "후보 원본": live_prov,
        "성과 원본": outcomes_prov,
        "독립 검증 원본": validation_prov,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(page, encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "candidates": live["candidate_count"],
        "independent_tickers": outcomes.get("independent_fresh_ticker_count", 0),
        "mature_5_sessions": outcomes.get("independent_mature_fresh_horizons", {}).get("5", 0),
        "WATCH_ONLY": True, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
