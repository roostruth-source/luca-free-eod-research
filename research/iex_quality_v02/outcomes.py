"""Offline 5/15/30/60-minute outcomes from IEX evidence. Never infer fills.

Reference = last completed IEX minute close known when the research pattern fired.
Outcome = first *observed IEX trade* in the 60-second window beginning at
signal-known-time + horizon. Missing IEX prints MISSING, never zero or success.
No trade is assumed executable. Not consolidated market data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from quality import finite_number, parse_utc

UTC = timezone.utc
HORIZONS = (5, 15, 30, 60)
MAX_JSONL_BYTES = 40_000_000


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    if path.stat().st_size > MAX_JSONL_BYTES:
        raise ValueError("INPUT_TOO_LARGE")
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            item = json.loads(line)
            if not isinstance(item, dict):
                raise ValueError("INVALID_JSONL_ROW")
            rows.append(item)
    return rows


def reference_price(signal, raw_rows):
    """Pick the latest bar version actually received by signal time."""
    known = parse_utc(signal.get("known_at_utc"))
    evidence = signal.get("evidence")
    minute = parse_utc(evidence.get("last_minute_utc")) if isinstance(evidence, dict) else None
    symbol = signal.get("symbol")
    if known is None or minute is None or not isinstance(symbol, str):
        return None
    candidates = []
    for row in raw_rows:
        if row.get("symbol") != symbol or row.get("type") not in ("minute_bar", "updated_minute_bar"):
            continue
        received = parse_utc(row.get("received_at_utc"))
        bar_minute = parse_utc(row.get("minute_utc"))
        price = finite_number(row.get("close"), positive=True)
        if received is None or bar_minute != minute or price is None or received > known:
            continue
        if minute + timedelta(minutes=1) > received:
            continue
        candidates.append((received, price))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def evaluate_signal(signal, raw_rows, *, evaluated_at, truncated=False):
    """Historical as-of evaluation; never use events received after evaluated_at."""
    known = parse_utc(signal.get("known_at_utc"))
    symbol = signal.get("symbol")
    if known is None or not isinstance(symbol, str) or evaluated_at.tzinfo is None:
        raise ValueError("INVALID_SIGNAL_OR_EVALUATION_TIME")
    evaluated_at = evaluated_at.astimezone(UTC)
    if evaluated_at < known:
        raise ValueError("EVALUATION_BEFORE_SIGNAL")
    baseline = reference_price(signal, raw_rows)
    result = {
        "symbol": symbol,
        "signal_known_at_utc": known.isoformat(),
        "evaluated_at_utc": evaluated_at.isoformat(),
        "reference_type": "LAST_COMPLETED_IEX_BAR_CLOSE_NOT_EXECUTABLE_FILL",
        "reference_price": baseline,
        "market_coverage": "ALPACA_IEX_ONLY",
        "validated": False,
        "horizons": {},
    }
    for minutes in HORIZONS:
        target = known + timedelta(minutes=minutes)
        deadline = target + timedelta(seconds=60)
        row = {
            "target_utc": target.isoformat(),
            "observation_window_seconds": 60,
            "status": None,
            "first_iex_trade_at_utc": None,
            "first_iex_trade_price": None,
            "change_pct_vs_reference": None,
        }
        if truncated:
            row["status"] = "INCOMPLETE_CAPTURE"
        elif baseline is None:
            row["status"] = "NO_ASOF_REFERENCE_BAR"
        elif evaluated_at < deadline:
            row["status"] = "PENDING"
        else:
            trades = []
            for event in raw_rows:
                if event.get("type") != "trade" or event.get("symbol") != symbol:
                    continue
                trade_at = parse_utc(event.get("exchange_at_utc"))
                received = parse_utc(event.get("received_at_utc"))
                price = finite_number(event.get("price"), positive=True)
                if trade_at is None or received is None or price is None:
                    continue
                # The trade must be within the future target window and
                # actually observed by evaluated_at, not backfilled later.
                if target <= trade_at < deadline and known <= received <= evaluated_at:
                    trades.append((trade_at, received, price))
            if trades:
                trade_at, _, price = min(trades, key=lambda item: (item[0], item[1]))
                row["status"] = "IEX_OBSERVED_NOT_EXECUTABLE_FILL"
                row["first_iex_trade_at_utc"] = trade_at.isoformat()
                row["first_iex_trade_price"] = price
                row["change_pct_vs_reference"] = round((price / baseline - 1) * 100, 3)
            else:
                row["status"] = "NO_IEX_TRADE_IN_WINDOW"
        result["horizons"][str(minutes)] = row
    return result


def build_report(signals, raw_rows, *, evaluated_at, truncated=False):
    return {
        "version": "0.2-outcomes",
        "research_only": True,
        "validated": False,
        "orders_enabled": False,
        "warning": "IEX-only observations, not consolidated market or executable prices",
        "evaluated_at_utc": evaluated_at.astimezone(UTC).isoformat(),
        "signals": [
            evaluate_signal(signal, raw_rows, evaluated_at=evaluated_at, truncated=truncated)
            for signal in signals
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="LUCA IEX offline future outcome check")
    parser.add_argument("--dir", default="luca_iex_quality_v02")
    parser.add_argument("--evaluated-at", default=None, help="UTC ISO timestamp, defaults to now")
    args = parser.parse_args()
    folder = Path(args.dir)
    summary = folder / "summary.json"
    if not summary.exists():
        raise SystemExit("MISSING_CAPTURE_SUMMARY")
    meta = json.loads(summary.read_text(encoding="utf-8"))
    if meta.get("source") != "Alpaca IEX only, NOT consolidated market":
        raise SystemExit("WRONG_CAPTURE_SOURCE")
    evaluated_at = parse_utc(args.evaluated_at) if args.evaluated_at else datetime.now(UTC)
    if evaluated_at is None:
        raise SystemExit("INVALID_EVALUATION_TIME")
    report = build_report(
        read_jsonl(folder / "signals.jsonl"),
        read_jsonl(folder / "raw_events.jsonl"),
        evaluated_at=evaluated_at,
        truncated=bool(meta.get("raw_truncated", False)),
    )
    (folder / "outcomes.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("RESULT: OFFLINE_OUTCOMES_WRITTEN; SIGNALS=" + str(len(report["signals"])) +
          "; NO_ORDERS; NOT_VALIDATED", flush=True)


if __name__ == "__main__":
    main()
