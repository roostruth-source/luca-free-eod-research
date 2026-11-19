"""Directly capture bounded SEC JSON with HTTP-Date timestamp receipts.

No proxy, mirror, retry loop, or access-denial bypass is used.  A missing or
implausible server Date header fails closed so the later bundle builder does
not rely only on a manually supplied timestamp.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
from pathlib import Path
import sys
import time
import urllib.request

from sec_access import MAX_JSON_BYTES, validate_user_agent
from sec_official_bundle import (MAX_EXPECTED_SYMBOLS, SOURCE, SUBMISSIONS_URL,
                                 SYMBOL, TICKERS_URL, canonical_sha256)

V03_DIR = Path(__file__).resolve().parents[1] / "v03_stage24"
sys.path.insert(0, str(V03_DIR))
from sec_auto_triage import ticker_cik_map  # noqa: E402

CAPTURE_SCHEMA = "LUCA_V10_SEC_DIRECT_CAPTURE_1"
MAX_CLOCK_SKEW = timedelta(minutes=15)
REQUEST_DELAY_SECONDS = 0.22


def _utc(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(label + "_timezone_required")
    return value.astimezone(timezone.utc)


def _symbols(value: list[str]) -> list[str]:
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_EXPECTED_SYMBOLS:
        raise ValueError("sec_capture_symbols_invalid")
    seen = set()
    output = []
    for symbol in value:
        if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol) or symbol in seen:
            raise ValueError("sec_capture_symbol_invalid_or_duplicate")
        seen.add(symbol)
        output.append(symbol)
    return output


def _fetch(url: str, user_agent: str, opener, clock) -> tuple[dict, dict]:
    if url != TICKERS_URL and SUBMISSIONS_URL.fullmatch(url) is None:
        raise ValueError("sec_capture_url_not_allowed")
    request = urllib.request.Request(url, headers={
        "User-Agent": validate_user_agent(user_agent),
        "Accept": "application/json", "Accept-Encoding": "identity",
    }, method="GET")
    with opener(request, timeout=20) as response:
        raw = response.read(MAX_JSON_BYTES + 1)
        date_header = response.headers.get("Date")
    retrieved = _utc(clock(), "sec_capture_clock")
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("sec_capture_response_too_large")
    if not isinstance(date_header, str):
        raise ValueError("sec_capture_http_date_required")
    try:
        server_time = parsedate_to_datetime(date_header)
    except (TypeError, ValueError) as exc:
        raise ValueError("sec_capture_http_date_invalid") from exc
    server_time = _utc(server_time, "sec_capture_http_date")
    if abs(retrieved - server_time) > MAX_CLOCK_SKEW:
        raise ValueError("sec_capture_clock_skew_excessive")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("sec_capture_json_object_required")
    return payload, {
        "source_url": url,
        "retrieved_at_utc": retrieved.isoformat(),
        "http_date_utc": server_time.isoformat(),
        "canonical_sha256": canonical_sha256(payload),
    }


def capture(symbols: list[str], user_agent: str, *, opener=None, clock=None,
            sleeper=None) -> dict:
    symbols = _symbols(symbols)
    validate_user_agent(user_agent)
    opener = opener or urllib.request.urlopen
    clock = clock or (lambda: datetime.now(timezone.utc))
    sleeper = sleeper or time.sleep
    started = _utc(clock(), "sec_capture_started")
    ticker_payload, ticker_receipt = _fetch(TICKERS_URL, user_agent, opener, clock)
    mapping = ticker_cik_map(ticker_payload)
    submissions = {}
    receipts = {}
    for symbol in symbols:
        cik = mapping.get(symbol)
        if cik is None:
            continue
        sleeper(REQUEST_DELAY_SECONDS)
        url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
        payload, receipt = _fetch(url, user_agent, opener, clock)
        if payload.get("cik") != cik:
            raise ValueError("sec_capture_submission_cik_mismatch")
        submissions[symbol] = payload
        receipts[symbol] = receipt
    completed = _utc(clock(), "sec_capture_completed")
    if completed < started or completed - started > timedelta(minutes=20):
        raise ValueError("sec_capture_duration_invalid")
    manifest = {
        "schema_version": CAPTURE_SCHEMA,
        "source": SOURCE,
        "started_at_utc": started.isoformat(),
        "completed_at_utc": completed.isoformat(),
        "expected_symbols": symbols,
        "ticker_map": ticker_receipt,
        "submissions": receipts,
        "declared_user_agent_present": True,
        "request_delay_seconds": REQUEST_DELAY_SECONDS,
        "timestamp_basis": "SEC_HTTP_DATE_PLUS_LOCAL_UTC_CLOCK",
        "independent_timestamp_fully_verified": False,
        "NO_ORDERS": True,
    }
    return {"ticker_payload": ticker_payload,
            "submission_payloads": submissions, "manifest": manifest}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", type=Path, required=True)
    parser.add_argument("--user-agent", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise FileExistsError("sec_capture_output_no_overwrite")
    symbols = json.loads(args.symbols.read_text(encoding="utf-8"))
    result = capture(symbols, args.user_agent)
    submissions_dir = args.output_dir / "submissions"
    submissions_dir.mkdir(parents=True)
    (args.output_dir / "company_tickers.json").write_text(
        json.dumps(result["ticker_payload"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    for symbol, payload in result["submission_payloads"].items():
        (submissions_dir / f"{symbol}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "capture_manifest.json").write_text(
        json.dumps(result["manifest"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({"status": "SEC_DIRECT_CAPTURE_NOT_CLEARED",
                      "expected": len(symbols),
                      "submissions": len(result["submission_payloads"]),
                      "NO_ORDERS": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
