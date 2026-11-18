"""Render the research JSON as a self-contained, mobile-readable HTML report."""

from __future__ import annotations

from html import escape
from typing import Any


def _s(value: Any) -> str:
    return escape(str(value), quote=True)


def render_report(report: dict[str, Any]) -> str:
    rows = []
    for item in report["candidates"]:
        reasons = ", ".join(item["block_reasons"]) or "확인된 차단 없음"
        volume = item.get("volume_evidence")
        volume_text = (
            f"{volume['volume_vs_average_multiple']:.1f}배 · "
            f"{'선행 후보' if volume['early_volume_candidate'] else '선행 신호 차단'}"
            if volume else "같은 거래일 검증 자료 없음"
        )
        rows.append(
            '<article class="card"><h2>' + _s(item["ticker"]) + '</h2>'
            '<p><strong>' + _s(item["detector_profile"]) + '</strong> · '
            + _s(item["engine_count"]) + '개 엔진 · ' + _s(item["state"]) + '</p>'
            '<p>거래량: ' + _s(volume_text) + '</p>'
            '<p>관찰 시각: ' + _s(item["snapshot_at"]) + '</p>'
            '<p>차단 이유: ' + _s(reasons) + '</p></article>'
        )
    volume_rows = []
    for item in report["volume_events"]:
        volume_rows.append(
            '<li><strong>' + _s(item["ticker"]) + '</strong> · '
            + _s(item["event_date"]) + ' · 직전 10일 평균의 '
            + _s(round(item["volume_vs_average_multiple"], 2)) + '배 · '
            + _s(item["state"]) + '</li>'
        )
    error_rows = [
        '<li>' + _s(item["ticker"]) + ': ' + _s(item["error"]) + '</li>'
        for item in report["errors"]
    ]
    return '''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LUCA 급등 판별기 연구 보고서</title>
<style>
body{font:16px/1.6 system-ui,sans-serif;max-width:720px;margin:auto;padding:16px;
background:#f6f7fb;color:#18202c}h1{font-size:1.5rem}h2{margin:0;font-size:1.25rem}
.card{background:white;border:1px solid #dfe4ed;border-radius:12px;padding:16px;
margin:12px 0;overflow-wrap:anywhere}.card p{margin:.5em 0}
.notice{background:#fff3d8;border-left:4px solid #b16b00;padding:12px}
li{margin:.5em 0;overflow-wrap:anywhere}small{color:#485365}
</style><main><h1>LUCA 급등 판별기</h1>
<p class="notice">관찰 전용 · 주문 없음 · 예측 성능 미검증. 엔진 순위는 상승 확률이 아닙니다.</p>
<p><small>생성 기준: ''' + _s(report["built_at"]) + ''' · 평가 ''' + _s(report["evaluated_count"]) + '''건 · 오류 ''' + _s(report["error_count"]) + '''건</small></p>
<h2>엔진 후보</h2>''' + ("".join(rows) or "<p>후보 없음</p>") + '''
<h2>거래량 사건</h2><ul>''' + ("".join(volume_rows) or "<li>없음</li>") + '''</ul>
<h2>입력 오류</h2><ul>''' + ("".join(error_rows) or "<li>없음</li>") + '''</ul>
<p><small>이 보고서는 입력된 동결 자료만 평가합니다. 전체 시장을 실시간 탐색한 결과가 아닙니다.</small></p>
</main></html>'''
