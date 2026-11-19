"""Validate bounded SEC-official input captured outside GitHub Actions.

GitHub-hosted runners can receive HTTP 403 from SEC-owned endpoints.  This
module does not bypass that denial.  It accepts a small, provenance-bearing
bundle produced by another authorized environment, validates it, and returns
only the current watchlist intersection.  A valid bundle is still research
input, never SEC clearance or permission to trade.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re


SCHEMA = "LUCA_V10_SEC_OFFICIAL_BUNDLE_1"
SOURCE = "SEC_OFFICIAL"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = re.compile(r"https://data\.sec\.gov/submissions/CIK(\d{10})\.json")
SYMBOL = re.compile(r"[A-Z][A-Z0-9.\-]{0,12}")
SHA256 = re.compile(r"[0-9a-f]{64}")
MAX_FILE_BYTES = 4_000_000
MAX_EXPECTED_SYMBOLS = 50
MAX_TICKER_ENTRIES = 5_000
MAX_SUBMISSIONS = 100
MAX_AGE = timedelta(hours=72)
CAPTURE_SCHEMA = "LUCA_V10_SEC_DIRECT_CAPTURE_1"
MAX_CAPTURE_CLOCK_SKEW = timedelta(minutes=15)


def canonical_sha256(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(label + "_timestamp_required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(label + "_timestamp_invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(label + "_timezone_required")
    return parsed.astimezone(timezone.utc)


def load_bundle_file(path: Path) -> dict:
    if not path.is_file():
        raise ValueError("sec_bundle_file_required")
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("sec_bundle_too_large")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("sec_bundle_json_invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("sec_bundle_object_required")
    return value


def validate_official_bundle(bundle: dict, asof: datetime,
                             expected_symbols: list[str]) -> dict:
    if not isinstance(bundle, dict):
        raise ValueError("sec_bundle_object_required")
    if not isinstance(asof, datetime) or asof.tzinfo is None:
        raise ValueError("sec_bundle_asof_timezone_required")
    asof_utc = asof.astimezone(timezone.utc)
    if bundle.get("schema_version") != SCHEMA or bundle.get("source") != SOURCE:
        raise ValueError("sec_bundle_schema_or_source_invalid")
    collected = _timestamp(bundle.get("collected_at_utc"), "sec_bundle_collected")
    if collected > asof_utc:
        raise ValueError("sec_bundle_future_collection_not_allowed")
    if asof_utc - collected > MAX_AGE:
        raise ValueError("sec_bundle_stale")

    if (not isinstance(expected_symbols, list)
            or len(expected_symbols) > MAX_EXPECTED_SYMBOLS):
        raise ValueError("sec_bundle_expected_symbols_invalid")
    expected = set()
    for symbol in expected_symbols:
        if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol) or symbol in expected:
            raise ValueError("sec_bundle_expected_symbol_invalid_or_duplicate")
        expected.add(symbol)

    if bundle.get("ticker_map_source_url") != TICKERS_URL:
        raise ValueError("sec_bundle_ticker_source_not_official")
    ticker_map = bundle.get("ticker_map")
    if (not isinstance(ticker_map, dict)
            or len(ticker_map) > MAX_TICKER_ENTRIES):
        raise ValueError("sec_bundle_ticker_map_invalid")
    for symbol, cik in ticker_map.items():
        if (not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol)
                or type(cik) is not int or not 1 <= cik <= 9_999_999_999):
            raise ValueError("sec_bundle_ticker_entry_invalid")
    ticker_hash = bundle.get("ticker_map_sha256")
    if (not isinstance(ticker_hash, str) or not SHA256.fullmatch(ticker_hash)
            or ticker_hash != canonical_sha256(ticker_map)):
        raise ValueError("sec_bundle_ticker_hash_mismatch")

    submissions = bundle.get("submissions")
    if not isinstance(submissions, dict) or len(submissions) > MAX_SUBMISSIONS:
        raise ValueError("sec_bundle_submissions_invalid")
    selected_map = {symbol: ticker_map[symbol]
                    for symbol in expected if symbol in ticker_map}
    # Fail closed: never silently ignore unexpected submission payloads.
    if set(submissions) - expected:
        raise ValueError("sec_bundle_unexpected_submission_symbol")
    selected_submissions = {}
    selected_sources = {}
    for symbol in sorted(expected):
        if symbol not in submissions:
            continue
        entry = submissions[symbol]
        if not isinstance(entry, dict) or symbol not in selected_map:
            raise ValueError("sec_bundle_submission_without_mapping")
        url = entry.get("source_url")
        match = SUBMISSIONS_URL.fullmatch(url or "")
        if match is None or int(match.group(1)) != selected_map[symbol]:
            raise ValueError("sec_bundle_submission_source_not_official")
        retrieved = _timestamp(entry.get("retrieved_at_utc"),
                               "sec_bundle_retrieved")
        if retrieved > collected or retrieved > asof_utc:
            raise ValueError("sec_bundle_future_retrieval_not_allowed")
        if asof_utc - retrieved > MAX_AGE:
            raise ValueError("sec_bundle_submission_stale")
        payload = entry.get("payload")
        if not isinstance(payload, dict) or payload.get("cik") != selected_map[symbol]:
            raise ValueError("sec_bundle_submission_payload_invalid")
        digest = entry.get("sha256")
        if (not isinstance(digest, str) or not SHA256.fullmatch(digest)
                or digest != canonical_sha256(payload)):
            raise ValueError("sec_bundle_submission_hash_mismatch")
        selected_submissions[symbol] = payload
        selected_sources[symbol] = {
            "source_url": url,
            "retrieved_at_utc": retrieved.isoformat(),
            "sha256": digest,
        }

    capture_manifest = bundle.get("capture_manifest")
    if capture_manifest is None:
        raise ValueError("sec_bundle_capture_manifest_required")
    else:
        if (not isinstance(capture_manifest, dict)
                or capture_manifest.get("schema_version") != CAPTURE_SCHEMA
                or capture_manifest.get("source") != SOURCE
                or capture_manifest.get("NO_ORDERS") is not True
                or capture_manifest.get("timestamp_basis")
                != "SEC_HTTP_DATE_PLUS_LOCAL_UTC_CLOCK"
                or capture_manifest.get("independent_timestamp_fully_verified") is not False):
            raise ValueError("sec_bundle_capture_manifest_invalid")
        manifest_expected = capture_manifest.get("expected_symbols")
        if (not isinstance(manifest_expected, list)
                or len(manifest_expected) != len(expected)
                or set(manifest_expected) != expected):
            raise ValueError("sec_bundle_capture_expected_symbols_mismatch")
        started = _timestamp(capture_manifest.get("started_at_utc"),
                             "sec_bundle_capture_started")
        completed = _timestamp(capture_manifest.get("completed_at_utc"),
                               "sec_bundle_capture_completed")
        if (completed != collected or completed < started
                or completed - started > timedelta(minutes=20)):
            raise ValueError("sec_bundle_capture_window_invalid")
        ticker_receipt = capture_manifest.get("ticker_map")
        if (not isinstance(ticker_receipt, dict)
                or ticker_receipt.get("source_url") != TICKERS_URL
                or not isinstance(ticker_receipt.get("canonical_sha256"), str)
                or not SHA256.fullmatch(ticker_receipt["canonical_sha256"])):
            raise ValueError("sec_bundle_capture_ticker_receipt_invalid")
        ticker_retrieved = _timestamp(ticker_receipt.get("retrieved_at_utc"),
                                      "sec_bundle_capture_ticker_retrieved")
        ticker_server = _timestamp(ticker_receipt.get("http_date_utc"),
                                   "sec_bundle_capture_ticker_http_date")
        if (not started <= ticker_retrieved <= completed
                or abs(ticker_retrieved - ticker_server) > MAX_CAPTURE_CLOCK_SKEW):
            raise ValueError("sec_bundle_capture_ticker_time_invalid")
        receipts = capture_manifest.get("submissions")
        if not isinstance(receipts, dict) or set(receipts) != set(submissions):
            raise ValueError("sec_bundle_capture_receipts_mismatch")
        for symbol, source in selected_sources.items():
            receipt = receipts.get(symbol)
            if (not isinstance(receipt, dict)
                    or receipt.get("source_url") != source["source_url"]
                    or receipt.get("retrieved_at_utc") != source["retrieved_at_utc"]
                    or receipt.get("canonical_sha256") != source["sha256"]):
                raise ValueError("sec_bundle_capture_receipt_invalid")
            server = _timestamp(receipt.get("http_date_utc"),
                                "sec_bundle_capture_http_date")
            retrieved = _timestamp(receipt.get("retrieved_at_utc"),
                                   "sec_bundle_capture_retrieved")
            if not started <= retrieved <= completed:
                raise ValueError("sec_bundle_capture_submission_outside_window")
            if abs(retrieved - server) > MAX_CAPTURE_CLOCK_SKEW:
                raise ValueError("sec_bundle_capture_clock_skew_excessive")
        timestamp_provenance = "SEC_HTTP_DATE_PLUS_LOCAL_UTC_CLOCK"
        capture_revalidated = True

    mapped = len(selected_map)
    available = len(selected_submissions)
    return {
        "ticker_map": selected_map,
        "submissions": selected_submissions,
        "provenance": {
            "status": ("FULL_CURRENT_WATCHLIST_INPUT_NOT_CLEARED"
                       if mapped == len(expected) and available == mapped
                       else "PARTIAL_CURRENT_WATCHLIST_INPUT_NOT_CLEARED"),
            "source": SOURCE,
            "collected_at_utc": collected.isoformat(),
            "ticker_map_source_url": TICKERS_URL,
            "ticker_map_sha256": ticker_hash,
            "expected_symbols": len(expected),
            "mapped_symbols": mapped,
            "submissions_available": available,
            "submission_sources": selected_sources,
            "retrieval_time_provenance": timestamp_provenance,
            "capture_manifest_revalidated": capture_revalidated,
            "independent_timestamp_fully_verified": False,
            "independently_refetched_in_this_run": False,
            "sec_clearance": False,
            "validation_status": "NOT_VALIDATED",
            "NO_ORDERS": True,
        },
    }
