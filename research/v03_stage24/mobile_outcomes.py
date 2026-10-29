"""Research-only, offline price changes from archived IEX bars. No orders or network."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

HORIZONS = (5, 15, 30, 60)
SCHEMA = "LUCA_V03_MOBILE_OUTCOMES_V1"
RAW_SCHEMA = "LUCA_V03_IEX_RAW_OHLCV_EVIDENCE_V1"


def _time(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_TIMESTAMP")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(dt.timezone.utc)


def _price(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value < 1e12:
        raise ValueError("INVALID_CLOSE_PRICE")
    return value


def build_report(raw):
    if not isinstance(raw, dict) or raw.get("schema") != RAW_SCHEMA:
        raise ValueError("WRONG_RAW_EVIDENCE_SCHEMA")
    if (raw.get("validation_status") != "NOT_VALIDATED" or
            raw.get("sec_status") != "SEC_UNVERIFIED" or
            raw.get("orders_allowed") is not False or
            raw.get("real_trades_allowed") is not False or
            raw.get("all_grades") != "D"):
        raise ValueError("UNSAFE_EVIDENCE")
    supplied_hash = raw.get("sha256")
    if supplied_hash is not None:
        canonical = json.dumps({k: v for k, v in raw.items() if k != "sha256"},
                               sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if supplied_hash != hashlib.sha256(canonical.encode("utf8")).hexdigest():
            raise ValueError("RAW_EVIDENCE_HASH_MISMATCH")
    rows = raw.get("rows")
    if not isinstance(rows, list):
        raise ValueError("MISSING_ROWS")
    output = []
    seen_symbols = set()
    for row in rows:
        if not isinstance(row, dict) or row.get("grade", "D") != "D" or row.get("buy_allowed", False) is not False:
            raise ValueError("UNSAFE_ROW")
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or not symbol or symbol in seen_symbols:
            raise ValueError("INVALID_OR_DUPLICATE_SYMBOL")
        seen_symbols.add(symbol)
        by_time = {}
        bars = row.get("ohlcv", [])
        if not isinstance(bars, list):
            raise ValueError("INVALID_BARS")
        for bar in bars:
            if not isinstance(bar, dict):
                raise ValueError("INVALID_BAR")
            stamp = _time(bar["t"])
            if stamp in by_time:
                raise ValueError("DUPLICATE_BAR_TIMESTAMP")
            by_time[stamp] = _price(bar["c"])
        signals = row.get("signals", [])
        if not isinstance(signals, list):
            raise ValueError("INVALID_SIGNALS")
        for index, entry in enumerate(signals):
            if not isinstance(entry, dict) or not isinstance(entry.get("signal"), dict):
                raise ValueError("INVALID_SIGNAL")
            start = _time(entry["signal"].get("signal_bar_start_utc"))
            baseline = by_time.get(start)
            changes = {}
            for minutes in HORIZONS:
                later = by_time.get(start + dt.timedelta(minutes=minutes))
                changes[str(minutes)] = (round((later / baseline - 1) * 100, 4)
                                         if baseline is not None and later is not None else None)
            output.append({"symbol": symbol, "signal_index": index + 1,
                           "signal_bar_start_utc": start.isoformat(),
                           "signal_bar_close": baseline, "changes_pct": changes,
                           "grade": "D", "buy_allowed": False})
    return {"schema": SCHEMA, "feed": "IEX_SINGLE_EXCHANGE_NOT_SIP",
            "price_basis": "signal_bar_close_vs_N_minutes_later_bar_close",
            "horizons_minutes": list(HORIZONS), "signals": output,
            "validation_status": "NOT_VALIDATED", "sec_status": "SEC_UNVERIFIED",
            "prediction_accuracy_verified": False, "orders_allowed": False,
            "real_trades_allowed": False,
            "warning_ko": "관찰 가격 변화이며 매수 추천·실제 체결 수익·예측 정확도가 아닙니다. 자료 누락은 확인 불가로 표시합니다."}


def markdown(report):
    lines = ["# 루카 V0.3 신호별 후속 가격 변화 (연구 전용)", "",
             "**NOT_VALIDATED · SEC_UNVERIFIED · 실제 주문 금지**", "",
             "신호가 발생한 1분봉의 종가와 N분 뒤 1분봉 종가를 비교했습니다. IEX 단일 거래소 자료입니다.", "",
             "| 종목 | 신호 시각(UTC) | 5분 | 15분 | 30분 | 60분 |",
             "|---|---|---:|---:|---:|---:|"]
    for item in report["signals"]:
        changes = item["changes_pct"]
        values = ["확인 불가" if changes[str(n)] is None else f'{changes[str(n)]:+.2f}%'
                  for n in HORIZONS]
        lines.append("| " + " | ".join([item["symbol"], item["signal_bar_start_utc"]] + values) + " |")
    if not report["signals"]:
        lines.append("| 신호 없음 | - | 확인 불가 | 확인 불가 | 확인 불가 | 확인 불가 |")
    lines.extend(["", report["warning_ko"], ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--json-output")
    args = parser.parse_args()
    source = Path(args.raw)
    if source.stat().st_size > 1_000_000:
        raise ValueError("RAW_FILE_TOO_LARGE")
    result = build_report(json.loads(source.read_text(encoding="utf8")))
    output = Path(args.output)
    if args.json_output:
        json_dest = Path(args.json_output)
        if json_dest.resolve() == output.resolve():
            raise ValueError("OUTPUT_PATH_COLLISION")
        if json_dest.exists():
            raise FileExistsError("JSON_OUTPUT_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf8") as handle:
        handle.write(markdown(result))
    if args.json_output:
        json_dest = Path(args.json_output)
        json_dest.parent.mkdir(parents=True, exist_ok=True)
        with json_dest.open("x", encoding="utf8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
    print("MOBILE_RESEARCH_REPORT_WRITTEN; NOT_VALIDATED; NO_ORDERS")


if __name__ == "__main__":
    main()
