"""Offline cohort inventory: count signal and no-signal candidates without claiming predictive performance.

No market requests, orders, or statistical success-rate claims.
"""
from __future__ import annotations
import json
from pathlib import Path

SCHEMA = "LUCA_V03_COHORT_INVENTORY_V1"
RAW_SCHEMA = "LUCA_V03_IEX_RAW_OHLCV_EVIDENCE_V1"


def inventory(raw):
    if not isinstance(raw, dict) or raw.get("schema") != RAW_SCHEMA:
        raise ValueError("BAD_RAW_SCHEMA")
    if (raw.get("validation_status") != "NOT_VALIDATED" or
            raw.get("sec_status") != "SEC_UNVERIFIED" or
            raw.get("all_grades") != "D" or
            raw.get("orders_allowed") is not False or
            raw.get("real_trades_allowed") is not False):
        raise ValueError("UNSAFE_RAW_EVIDENCE")
    rows = raw.get("rows")
    if not isinstance(rows, list):
        raise ValueError("INVALID_ROWS")
    seen = set()
    signal = []
    no_signal = []
    missing = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("INVALID_ROW")
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or not symbol or symbol in seen:
            raise ValueError("INVALID_OR_DUPLICATE_SYMBOL")
        seen.add(symbol)
        if row.get("grade") != "D" or row.get("buy_allowed") is not False:
            raise ValueError("UNSAFE_ROW")
        signals = row.get("signals")
        bars = row.get("ohlcv")
        if not isinstance(signals, list) or not isinstance(bars, list):
            raise ValueError("INVALID_SIGNALS_OR_BARS")
        if signals:
            signal.append(symbol)
        else:
            no_signal.append(symbol)
        if row.get("missing_minutes", 0) or not bars:
            missing.append(symbol)
    if raw.get("symbols", len(rows)) != len(rows):
        raise ValueError("SYMBOL_COUNT_MISMATCH")
    return {
        "schema": SCHEMA,
        "candidate_count": len(rows),
        "signal_candidate_count": len(signal),
        "no_signal_candidate_count": len(no_signal),
        "missing_or_empty_candidate_count": len(missing),
        "signal_symbols": signal,
        "no_signal_symbols": no_signal,
        "missing_or_empty_symbols": missing,
        "comparison_outcomes_calculated": False,
        "comparison_reference_time_defined": False,
        "prediction_accuracy_verified": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "orders_allowed": False,
        "real_trades_allowed": False,
        "warning_ko": "후보 명단과 신호 유무만 집계했습니다. 무신호 종목의 기준 시각을 정하지 않았으므로 성과·승률을 비교하지 않습니다.",
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = Path(args.raw)
    if source.stat().st_size > 1_000_000:
        raise ValueError("RAW_FILE_TOO_LARGE")
    result = inventory(json.loads(source.read_text(encoding="utf8")))
    dest = Path(args.output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("x", encoding="utf8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("OFFLINE_COHORT_INVENTORY_ONLY; NOT_VALIDATED; NO_ORDERS")


if __name__ == "__main__":
    main()
