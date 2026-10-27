"""Manual-only IEX WebSocket evidence capture for LUCA V0.2.

No order/trading endpoints. No automatic schedule. No production dependencies.
Saves allowlisted trade and completed-bar messages, not credentials.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import time

from quality import QualityBook, finite_number, parse_completed_bar, parse_utc

UTC = timezone.utc
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,12}$")
MAX_RAW_ROWS = 100000


def parse_symbols(raw):
    symbols = list(dict.fromkeys(x.strip().upper() for x in raw.replace(";", ",").split(",") if x.strip()))
    if not 1 <= len(symbols) <= 20 or any(not SYMBOL_RE.fullmatch(s) for s in symbols):
        raise ValueError("INVALID_SYMBOLS")
    return symbols


def safe_events(raw):
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [x for x in value if isinstance(x, dict)] if isinstance(value, list) else []


def write_json_line(handle, value):
    handle.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")


def run(symbols, minutes, outdir):
    # Import only inside the live collector; offline quality tests need no dependencies.
    from websockets.sync.client import connect

    if minutes not in (3, 6, 9):
        raise ValueError("INVALID_DURATION")
    key = os.environ.get("ALPACA_KEY")
    secret = os.environ.get("ALPACA_SECRET")
    if not key or not secret:
        raise ValueError("MISSING_GITHUB_SECRETS")

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    book = QualityBook(symbols)
    start = datetime.now(UTC)
    deadline = time.monotonic() + minutes * 60
    authenticated = False
    subscribed = False
    raw_rows = 0
    raw_truncated = False
    emitted = set()
    signal_count = 0
    summary = None

    with (outdir / "raw_events.jsonl").open("w", encoding="utf-8") as rawfile, \
         (outdir / "signals.jsonl").open("w", encoding="utf-8") as signalfile:
        with connect(
            "wss://stream.data.alpaca.markets/v2/iex",
            open_timeout=15, close_timeout=4, max_size=2_000_000,
        ) as ws:
            ws.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
            while time.monotonic() < deadline:
                try:
                    frame = ws.recv(timeout=min(8, max(0.1, deadline - time.monotonic())))
                except TimeoutError:
                    continue
                except Exception:
                    raise RuntimeError("WEBSOCKET_DISCONNECTED") from None
                received_at = datetime.now(UTC)
                for event in safe_events(frame):
                    kind = event.get("T")
                    if kind == "error":
                        code = event.get("code")
                        code = code if type(code) is int and 100 <= code <= 999 else "UNKNOWN"
                        raise RuntimeError("ALPACA_WS_ERROR_" + str(code))
                    if kind == "success" and event.get("msg") == "authenticated":
                        if not authenticated:
                            authenticated = True
                            ws.send(json.dumps({
                                "action": "subscribe",
                                "trades": symbols, "bars": symbols, "updatedBars": symbols,
                            }))
                        continue
                    if kind == "subscription":
                        if authenticated and all(
                            set(symbols).issubset(set(event.get(field, [])))
                            for field in ("trades", "bars", "updatedBars")
                        ):
                            subscribed = True
                        else:
                            raise RuntimeError("SUBSCRIPTION_INCOMPLETE")
                        continue
                    symbol = event.get("S")
                    if not subscribed or not isinstance(symbol, str) or symbol not in book.symbols:
                        continue

                    record = None
                    if kind == "t":
                        price = finite_number(event.get("p"), positive=True)
                        size = finite_number(event.get("s"))
                        exchange_time = parse_utc(event.get("t"))
                        if price is None or size is None or exchange_time is None:
                            continue
                        if exchange_time > received_at.replace(microsecond=0) + __import__("datetime").timedelta(minutes=1):
                            continue
                        book.record_trade(symbol)
                        record = {
                            "received_at_utc": received_at.isoformat(), "type": "trade",
                            "symbol": symbol, "exchange_at_utc": exchange_time.isoformat(),
                            "price": price, "size": size,
                        }
                    elif kind in ("b", "u"):
                        bar = parse_completed_bar(event, received_at)
                        outcome = book.ingest(event, received_at)
                        if bar is None:
                            continue
                        record = {
                            "received_at_utc": received_at.isoformat(),
                            "type": "minute_bar" if kind == "b" else "updated_minute_bar",
                            "symbol": symbol, "minute_utc": bar.minute.isoformat(),
                            "open": bar.open, "high": bar.high, "low": bar.low,
                            "close": bar.close, "iex_volume": bar.volume,
                            "quality_ingest": outcome,
                        }
                        if outcome in ("NEW", "REVISION"):
                            assessment = book.evaluate(symbol, received_at)
                            key_for_signal = (symbol, assessment["last_minute_utc"])
                            if assessment["research_pattern"] and key_for_signal not in emitted:
                                emitted.add(key_for_signal)
                                signal_count += 1
                                write_json_line(signalfile, {
                                    "symbol": symbol,
                                    "known_at_utc": received_at.isoformat(),
                                    "status": "UNVALIDATED_RESEARCH_PATTERN",
                                    "evidence": assessment,
                                    "data_source": "ALPACA_IEX_ONLY",
                                    "sec_checked": False,
                                    "buy_signal": False,
                                })
                    if record is not None:
                        if raw_rows < MAX_RAW_ROWS:
                            write_json_line(rawfile, record)
                            raw_rows += 1
                        else:
                            raw_truncated = True

            if not authenticated:
                raise RuntimeError("AUTH_NOT_CONFIRMED")
            if not subscribed:
                raise RuntimeError("SUBSCRIPTION_NOT_CONFIRMED")

    end = datetime.now(UTC)
    summary = {
        "version": "0.2-quality",
        "research_only": True,
        "validated": False,
        "orders_enabled": False,
        "source": "Alpaca IEX only, NOT consolidated market",
        "started_utc": start.isoformat(),
        "finished_utc": end.isoformat(),
        "duration_minutes": minutes,
        "raw_event_rows": raw_rows,
        "raw_truncated": raw_truncated,
        "unvalidated_pattern_events": signal_count,
        "symbols": [book.summary(symbol, end) for symbol in symbols],
        "limitations": [
            "IEX-only: zero messages does not imply zero US-market trades",
            "No SEC/float/dilution, order book, spread, short interest or trading checks",
            "No true consolidated RVOL or calibrated probability",
            "No 5/15/30/60-minute future outcome validation yet",
        ],
    }
    (outdir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# 루카 IEX V0.2 원본 관찰 · 독립 연구판", "",
        "**실거래 주문 없음 / 매수 추천 아님 / NOT_VALIDATED**", "",
        f"- IEX 원본 기록: {raw_rows:,}건" + (" (상한 도달: 일부 누락)" if raw_truncated else ""),
        f"- 검증 전 연구 패턴: {signal_count}건", "",
        "| 종목 | IEX 체결 | 완성된 서로 다른 1분봉 | 누락 분 | 상태 |",
        "|---|---:|---:|---:|---|",
    ]
    for item in summary["symbols"]:
        lines.append(
            f"| {item['symbol']} | {item['iex_trade_messages']} | "
            f"{item['unique_completed_minutes']} | "
            f"{item['missing_minutes_between_first_and_last']} | {item['quality_state']} |"
        )
    lines.extend([
        "", "IEX는 미국 전체 거래소가 아닙니다. 자료 부족은 거래가 없었다는 뜻이 아닙니다.",
        "연구 패턴은 검증 전 가설이며, SEC·희석·호가를 확인하지 않아 매수 등급을 부여하지 않습니다.",
        "원본은 raw_events.jsonl, 신호 최초 관측 시점은 signals.jsonl, 요약은 summary.json에 저장됩니다.",
    ])
    markdown = "\n".join(lines) + "\n"
    (outdir / "summary.md").write_text(markdown, encoding="utf-8")
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        Path(step_summary).write_text(markdown, encoding="utf-8")
    print(
        "RESULT: SUCCESS_IEX_QUALITY_V02; RAW_ROWS=", raw_rows,
        "; PATTERNS=", signal_count, "; NO_ORDERS; NOT_VALIDATED",
        flush=True,
    )
    return summary


def main():
    try:
        symbols = parse_symbols(os.environ.get("LUCA_SYMBOLS", "AAPL,NIKI,GPUS,PFSA,LAES,VCIG"))
        minutes = int(os.environ.get("LUCA_MINUTES", "9"))
        run(symbols, minutes, os.environ.get("LUCA_OUTPUT_DIR", "luca_iex_quality_v02"))
    except Exception as error:
        # Deliberately avoid printing credentials, server payloads or traceback.
        reason = str(error)
        allowed = {
            "INVALID_SYMBOLS", "INVALID_DURATION", "MISSING_GITHUB_SECRETS",
            "WEBSOCKET_DISCONNECTED", "SUBSCRIPTION_INCOMPLETE",
            "AUTH_NOT_CONFIRMED", "SUBSCRIPTION_NOT_CONFIRMED",
        }
        label = reason if reason in allowed or reason.startswith("ALPACA_WS_ERROR_") else "RUNTIME_" + type(error).__name__
        print("RESULT: SAFE_FAILURE; REASON=" + label + "; NO_ORDERS", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
