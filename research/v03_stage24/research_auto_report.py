"""Research-only automatic A/B/C/D report from a FROZEN Stage24 replay.

Consumes existing historical replay + partial SEC evidence; no market API calls,
new signal rules, orders, site changes or user-submitted ticker lists.
A is never issued before independent validation and complete SEC verification.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
from sec_asof_guard import STUDY_SYMBOLS, annotate_replay

EXPECTED_RULE_SHA = "b8e0dd350daba7c9b1e6fa41fd3886ca32ea1395a785478257132310d08d8d1b"
EXPECTED_HYP_SHA = "a30de65d7f5e561178ebe888c45d3f4fd6f51209dd5ab03ff1551bd7a9a7a5eb"
REPLAY_SCHEMA = "LUCA_STAGE24_FUTURE_DATED_HISTORICAL_REPLAY_V1"


def build_report(replay: dict, snapshot: dict) -> dict:
    if not isinstance(replay, dict) or replay.get("schema") != REPLAY_SCHEMA:
        raise ValueError("WRONG_FROZEN_REPLAY_SCHEMA")
    if replay.get("frozen_protocol_sha256") != EXPECTED_RULE_SHA:
        raise ValueError("RULE_HASH_MISMATCH")
    if replay.get("frozen_hypotheses_sha256") != EXPECTED_HYP_SHA:
        raise ValueError("HYPOTHESIS_HASH_MISMATCH")
    if replay.get("prediction_accuracy_verified") is not False:
        raise ValueError("UNSAFE_PREDICTION_CLAIM")
    if replay.get("real_trades_allowed") is not False or replay.get("validation_status") != "NOT_VALIDATED":
        raise ValueError("UNSAFE_REPLAY_FLAGS")
    if replay.get("source") != "user supplied Alpaca SIP labelled file not provider reverified":
        raise ValueError("SOURCE_MISMATCH")
    if not isinstance(replay.get("days_downloaded"), list) or len(replay["days_downloaded"]) != 1:
        raise ValueError("ONE_DAY_AT_A_TIME")
    day = replay["days_downloaded"][0]
    if not isinstance(day, str) or dt.date.fromisoformat(day).isoformat() != day:
        raise ValueError("INVALID_DAY")
    coverage = replay.get("coverage")
    if not isinstance(coverage, list) or len(coverage) != 6:
        raise ValueError("INVALID_COVERAGE")
    seen = set()
    for c in coverage:
        if not isinstance(c, dict) or c.get("day") != day:
            raise ValueError("COVERAGE_DAY_MISMATCH")
        symbol = c.get("symbol")
        if symbol not in set(STUDY_SYMBOLS) | {"AAPL"} or symbol in seen:
            raise ValueError("COVERAGE_SYMBOL_MISMATCH")
        seen.add(symbol)
        bars = c.get("bars")
        if type(bars) is not int or not 0 <= bars <= 180 or c.get("missing_minutes") != 180-bars:
            raise ValueError("INVALID_BAR_COVERAGE")
    if seen != set(STUDY_SYMBOLS) | {"AAPL"}:
        raise ValueError("INCOMPLETE_COVERAGE")
    cases = replay.get("cases")
    if not isinstance(cases, list):
        raise ValueError("INVALID_CASES")
    if replay.get("summary", {}).get("total_first_signals") != len(cases):
        raise ValueError("SIGNAL_COUNT_MISMATCH")
    if len({x.get("symbol") for x in cases if isinstance(x, dict)}) != len(cases):
        raise ValueError("DUPLICATE_FIRST_SIGNAL")
    risk = annotate_replay(replay, snapshot)
    risks = {x["symbol"]: x for x in risk["cases"]}
    by_symbol = {x["symbol"]: x for x in cases}
    rows = []
    for c in coverage:
        symbol = c["symbol"]
        if symbol == "AAPL":
            continue  # market reference, not a microcap candidate
        bars = c["bars"]
        case = by_symbol.get(symbol)
        if case:
            if case.get("day") != day or case.get("real_trades_allowed") is not False:
                raise ValueError("UNSAFE_CASE")
            t = dt.datetime.fromisoformat(case["signal_bar_start_utc"])
            known = dt.datetime.fromisoformat(case["known_at_utc"])
            if t.tzinfo is None or known.tzinfo is None or known-t != dt.timedelta(minutes=1):
                raise ValueError("LOOKAHEAD_OR_TIME_ERROR")
            if t.astimezone(dt.timezone.utc).date().isoformat() != day:
                raise ValueError("SIGNAL_DAY_MISMATCH")
            status15 = case.get("15m")
            if not isinstance(status15, dict):
                raise ValueError("MISSING_OUTCOME")
            outcome = status15.get("change_pct") if status15.get("complete") is True else None
            if outcome is not None and (type(outcome) not in (int, float) or not -100 <= outcome <= 100000):
                raise ValueError("BAD_OUTCOME")
            # Grade C: research signal exists, but SEC dilution risk or verification gap blocks approval.
            grade = "C"
            explanation = ("희석 위험 확인" if risks[symbol]["sec_risk"] != "UNKNOWN"
                           else "SEC 위험 확인 부족")
            rows.append({"symbol":symbol,"grade":grade,"observed_bars":bars,
                         "signal_known_at_utc":case["known_at_utc"],
                         "15m_historical_change_pct":outcome,
                         "sec_risk":risks[symbol]["sec_risk"],"reason":explanation,
                         "buy_allowed":False})
        else:
            # Grade D: no confirmed first signal, including sparse sessions.
            rows.append({"symbol":symbol,"grade":"D","observed_bars":bars,
                         "signal_known_at_utc":None,"15m_historical_change_pct":None,
                         "sec_risk":"NOT_ASSESSED_NO_SIGNAL",
                         "reason":"자료 부족" if bars < 180 else "관측 구간 신호 없음",
                         "buy_allowed":False})
    return {
        "schema":"LUCA_V03_RESEARCH_AUTOREPORT_V1","day":day,
        "source":"FROZEN_STAGE24_SIP_HISTORICAL_REPLAY_NOT_LIVE_IEX",
        "grades":{"A":0,"B":0,"C":sum(x["grade"]=="C" for x in rows),
                  "D":sum(x["grade"]=="D" for x in rows)},
        "observed_bars":sum(c["bars"] for c in coverage),
        "signals":len(cases),"rows":rows,
        "asof_sec_acceptance_times_verified":False,
        "prediction_accuracy_verified":False,
        "new_signal_rules_enabled":False,"real_trades_allowed":False,
        "validation_status":"NOT_VALIDATED",
        "warning":"사후 검증 보고서이며 실시간 탐색 성공·체결·수익 보장이 아닙니다."
    }


def to_markdown(r: dict) -> str:
    lines = [
        "# 루카 V0.3 연구판 자동 보고 — "+r["day"],
        "",
        "**NOT_VALIDATED · 실제 매수 금지 · 과거 자료 재생 (실시간 알림 아님)**",
        "",
        "원본 고정 규칙으로 탐색한 결과입니다. A/B는 검증 전이므로 발급하지 않습니다.",
        "",
        "| 종목 | 등급 | 확보 분봉 | 15분 뒤 변화 | SEC/사유 |",
        "|---|---|---:|---:|---|",
    ]
    for x in r["rows"]:
        pct = ("확인 불가" if x["15m_historical_change_pct"] is None
               else f'{x["15m_historical_change_pct"]:+.3f}%')
        lines.append(f'| {x["symbol"]} | {x["grade"]} | {x["observed_bars"]}/180 | {pct} | {x["reason"]} |')
    lines += [
        "",
        f'총 신호 **{r["signals"]}건** / 연구 위험 신호 C **{r["grades"]["C"]}건** / '
        f'자료 부족 또는 무신호 D **{r["grades"]["D"]}건**',
        "",
        "**주의:** SEC 자료는 날짜 단위의 부분 검수이며, 신호 발생 시각 이전에 공개됐는지 "
        "모든 공시의 정확한 접수시각을 검증한 것은 아닙니다.",
        "",
        "실시간 전 종목 자동감시·호가 검증·실제 체결은 아직 구현/검증 완료되지 않았습니다.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("frozen_replay_json")
    p.add_argument("sec_snapshot_json")
    p.add_argument("--out-dir",required=True)
    args = p.parse_args()
    replay = json.loads(Path(args.frozen_replay_json).read_text(encoding="utf8"))
    sec = json.loads(Path(args.sec_snapshot_json).read_text(encoding="utf8"))
    report = build_report(replay,sec)
    folder = Path(args.out_dir)
    folder.mkdir(parents=True,exist_ok=True)
    for filename in ("report.json","report.md"):
        if (folder/filename).exists():
            raise FileExistsError("NO_OVERWRITE")
    (folder/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    (folder/"report.md").write_text(to_markdown(report),encoding="utf8")
    print("RESEARCH_AUTOREPORT; SIGNALS="+str(report["signals"])+
          "; A=0; B=0; C="+str(report["grades"]["C"])+
          "; D="+str(report["grades"]["D"])+
          "; NOT_VALIDATED; NO_ORDERS")


if __name__=="__main__":
    main()
