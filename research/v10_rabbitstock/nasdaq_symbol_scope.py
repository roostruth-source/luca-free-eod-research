"""Classify candidate security scope from official Nasdaq Trader directories."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import io
import re
import urllib.request

NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
MAX_BYTES = 5_000_000
SYMBOL = re.compile(r"[A-Z][A-Z0-9.\-]{0,13}")
NON_COMMON_NAME = re.compile(
    r"\b(WARRANTS?|UNITS?|RIGHTS?|PREFERRED|NOTES?|BONDS?)\b", re.IGNORECASE)


def _fetch(url: str, opener=None) -> tuple[str, dict]:
    if url not in (NASDAQ_URL, OTHER_URL):
        raise ValueError("symbol_directory_url_not_allowed")
    request = urllib.request.Request(url, headers={
        "Accept": "text/plain", "Accept-Encoding": "identity",
        "User-Agent": "LUCA-V10-RESEARCH-READONLY/1.0",
    }, method="GET")
    with (opener or urllib.request.urlopen)(request, timeout=20) as response:
        raw = response.read(MAX_BYTES + 1)
        date_header = response.headers.get("Date")
    if len(raw) > MAX_BYTES:
        raise ValueError("symbol_directory_too_large")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("symbol_directory_encoding_invalid") from exc
    receipt = {"source_url": url, "http_date_utc": None}
    if date_header:
        try:
            server_time = parsedate_to_datetime(date_header)
        except (TypeError, ValueError) as exc:
            raise ValueError("symbol_directory_http_date_invalid") from exc
        if server_time.tzinfo is None:
            raise ValueError("symbol_directory_http_date_timezone_required")
        receipt["http_date_utc"] = server_time.astimezone(timezone.utc).isoformat()
    return text, receipt


def parse_directory(text: str, source_url: str) -> tuple[dict[str, dict], str]:
    if not isinstance(text, str) or source_url not in (NASDAQ_URL, OTHER_URL):
        raise ValueError("symbol_directory_input_invalid")
    lines = [line for line in text.splitlines() if line]
    if len(lines) < 2:
        raise ValueError("symbol_directory_empty")
    creation = next((line.split("|", 1)[0] for line in reversed(lines)
                     if line.startswith("File Creation Time:")), None)
    if creation is None:
        raise ValueError("symbol_directory_creation_time_missing")
    data_lines = [line for line in lines if not line.startswith("File Creation Time:")]
    reader = csv.DictReader(io.StringIO("\n".join(data_lines)), delimiter="|")
    symbol_field = "Symbol" if source_url == NASDAQ_URL else "ACT Symbol"
    required = {symbol_field, "Security Name", "Test Issue"}
    if reader.fieldnames is None or not required.issubset(reader.fieldnames):
        raise ValueError("symbol_directory_columns_missing")
    records = {}
    for row in reader:
        symbol = row.get(symbol_field, "").strip().upper()
        if not SYMBOL.fullmatch(symbol) or symbol in records:
            raise ValueError("symbol_directory_symbol_invalid_or_duplicate")
        name = row.get("Security Name", "").strip()
        etf = row.get("ETF", "").strip().upper()
        test_issue = row.get("Test Issue", "").strip().upper()
        if etf not in ("", "Y", "N") or test_issue not in ("Y", "N"):
            raise ValueError("symbol_directory_flags_invalid")
        if test_issue == "Y":
            status = "EXCLUDED_TEST_ISSUE"
        elif etf == "Y":
            status = "EXCLUDED_ETF_OR_ETP"
        elif NON_COMMON_NAME.search(name):
            status = "EXCLUDED_NON_COMMON_NAME"
        else:
            status = "COMMON_EQUITY_CANDIDATE_SCOPE"
        records[symbol] = {
            "status": status, "security_name": name,
            "etf_flag": etf or "UNKNOWN", "test_issue": test_issue,
            "exchange_code": row.get("Exchange") or "NASDAQ",
            "financial_status": row.get("Financial Status") or "UNKNOWN",
            "source_url": source_url,
        }
    return records, creation


def collect(symbols: list[str], asof: datetime, opener=None) -> dict:
    if not isinstance(asof, datetime) or asof.tzinfo is None:
        raise ValueError("symbol_scope_asof_timezone_required")
    if (not isinstance(symbols, list) or len(symbols) > 50
            or len(symbols) != len(set(symbols))
            or any(not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol)
                   for symbol in symbols)):
        raise ValueError("symbol_scope_symbols_invalid")
    merged = {}
    receipts = []
    creation_times = []
    try:
        for url in (NASDAQ_URL, OTHER_URL):
            text, receipt = _fetch(url, opener)
            records, creation = parse_directory(text, url)
            overlap = set(merged).intersection(records)
            if overlap:
                raise ValueError("symbol_directory_cross_file_duplicate")
            merged.update(records)
            receipts.append(receipt)
            creation_times.append(creation)
    except (OSError, ValueError, UnicodeError) as exc:
        return {
            "schema_version": "LUCA_V10_SYMBOL_SCOPE_1",
            "status": "SYMBOL_DIRECTORY_" + type(exc).__name__.upper(),
            "rows": [], "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
        }
    rows = []
    for symbol in symbols:
        record = merged.get(symbol)
        rows.append({"symbol": symbol, **(record or {
            "status": "SYMBOL_DIRECTORY_NOT_MAPPED",
            "security_name": None, "etf_flag": "UNKNOWN", "test_issue": "UNKNOWN",
            "exchange_code": "UNKNOWN", "financial_status": "UNKNOWN",
            "source_url": None,
        })})
    return {
        "schema_version": "LUCA_V10_SYMBOL_SCOPE_1",
        "status": "OFFICIAL_NASDAQ_DIRECTORY_COLLECTED",
        "collected_at": asof.astimezone(timezone.utc).isoformat(),
        "file_creation_rows": creation_times, "source_receipts": receipts,
        "rows": rows, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
    }
