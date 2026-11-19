"""Build a bounded SEC-official bundle from already downloaded raw JSON.

This command performs no network requests.  The raw files must have been
downloaded from the declared SEC URLs by an environment that is permitted to
access them.  The resulting bundle is validated again before it is written.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys

from sec_official_bundle import (SCHEMA, SOURCE, TICKERS_URL, canonical_sha256,
                                 validate_official_bundle)
from capture_sec_official_inputs import CAPTURE_SCHEMA, MAX_CLOCK_SKEW

V03_DIR = Path(__file__).resolve().parents[1] / "v03_stage24"
sys.path.insert(0, str(V03_DIR))
from sec_auto_triage import ticker_cik_map  # noqa: E402


def _read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("sec_raw_json_object_required")
    return value


def _read_symbols(path: Path) -> list[str]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError("sec_symbols_json_list_required")
    return value


def _time(raw: object, label: str) -> datetime:
    if not isinstance(raw, str):
        raise ValueError(label + "_timestamp_required")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(label + "_timestamp_invalid") from exc
    if value.tzinfo is None:
        raise ValueError(label + "_timezone_required")
    return value.astimezone(timezone.utc)


def _validate_capture_manifest(manifest: dict, ticker_payload: dict,
                               submission_payloads: dict[str, dict],
                               symbols: list[str]) -> tuple[datetime, dict[str, str]]:
    if (not isinstance(manifest, dict)
            or manifest.get("schema_version") != CAPTURE_SCHEMA
            or manifest.get("source") != SOURCE
            or manifest.get("NO_ORDERS") is not True
            or manifest.get("expected_symbols") != symbols
            or manifest.get("timestamp_basis") != "SEC_HTTP_DATE_PLUS_LOCAL_UTC_CLOCK"
            or manifest.get("independent_timestamp_fully_verified") is not False):
        raise ValueError("sec_capture_manifest_invalid")
    started = _time(manifest.get("started_at_utc"), "sec_capture_started")
    completed = _time(manifest.get("completed_at_utc"), "sec_capture_completed")
    if completed < started or completed - started > timedelta(minutes=20):
        raise ValueError("sec_capture_manifest_duration_invalid")

    def check(receipt: object, payload: dict, expected_url: str, label: str) -> str:
        if not isinstance(receipt, dict) or receipt.get("source_url") != expected_url:
            raise ValueError(label + "_receipt_invalid")
        retrieved = _time(receipt.get("retrieved_at_utc"), label + "_retrieved")
        server = _time(receipt.get("http_date_utc"), label + "_http_date")
        if not started <= retrieved <= completed or abs(retrieved - server) > MAX_CLOCK_SKEW:
            raise ValueError(label + "_receipt_time_invalid")
        if receipt.get("canonical_sha256") != canonical_sha256(payload):
            raise ValueError(label + "_receipt_hash_mismatch")
        return retrieved.isoformat()

    ticker_receipt = manifest.get("ticker_map")
    check(ticker_receipt, ticker_payload, TICKERS_URL, "sec_capture_ticker")
    receipts = manifest.get("submissions")
    if not isinstance(receipts, dict) or set(receipts) != set(submission_payloads):
        raise ValueError("sec_capture_submission_receipts_mismatch")
    retrieved_at = {}
    full_map = ticker_cik_map(ticker_payload)
    for symbol, payload in submission_payloads.items():
        cik = full_map.get(symbol)
        if cik is None:
            raise ValueError("sec_capture_submission_symbol_not_mapped")
        url = f"https://data.sec.gov/submissions/CIK{cik:010d}.json"
        retrieved_at[symbol] = check(receipts[symbol], payload, url,
                                     "sec_capture_submission")
    return completed, retrieved_at


def build(ticker_payload: dict, submission_payloads: dict[str, dict],
          symbols: list[str], collected_at: datetime,
          *, capture_manifest: dict | None = None) -> dict:
    if capture_manifest is None:
        raise ValueError("sec_capture_manifest_required")
    if collected_at.tzinfo is None:
        raise ValueError("sec_bundle_collected_timezone_required")
    full_map = ticker_cik_map(ticker_payload)
    selected_map = {symbol: full_map[symbol] for symbol in symbols
                    if symbol in full_map}
    retrieved_at = {}
    manifest_completed, retrieved_at = _validate_capture_manifest(
        capture_manifest, ticker_payload, submission_payloads, symbols)
    if manifest_completed != collected_at.astimezone(timezone.utc):
        raise ValueError("sec_capture_completed_time_mismatch")
    collected_text = collected_at.astimezone(timezone.utc).isoformat()
    submissions = {}
    for symbol, payload in submission_payloads.items():
        if symbol not in selected_map:
            raise ValueError("sec_submission_symbol_not_mapped")
        cik = selected_map[symbol]
        if payload.get("cik") != cik:
            raise ValueError("sec_submission_cik_mismatch")
        submissions[symbol] = {
            "source_url": f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
            "retrieved_at_utc": retrieved_at[symbol],
            "payload": payload,
            "sha256": canonical_sha256(payload),
        }
    bundle = {
        "schema_version": SCHEMA,
        "source": SOURCE,
        "collected_at_utc": collected_text,
        "ticker_map_source_url": TICKERS_URL,
        "ticker_map": selected_map,
        "ticker_map_sha256": canonical_sha256(selected_map),
        "submissions": submissions,
    }
    bundle["capture_manifest"] = capture_manifest
    validate_official_bundle(bundle, collected_at, symbols)
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker-map", type=Path, required=True)
    parser.add_argument("--submissions-dir", type=Path, required=True)
    parser.add_argument("--symbols", type=Path, required=True,
                        help="JSON array of uppercase ticker symbols")
    parser.add_argument("--capture-manifest", type=Path, required=True,
                        help="manifest emitted by capture_sec_official_inputs.py")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("sec_bundle_no_overwrite")
    symbols = _read_symbols(args.symbols)
    submissions = {}
    for path in sorted(args.submissions_dir.glob("*.json")):
        submissions[path.stem.upper()] = _read_object(path)
    manifest = _read_object(args.capture_manifest)
    collected_at = _time(manifest.get("completed_at_utc"), "sec_capture_completed")
    bundle = build(_read_object(args.ticker_map), submissions, symbols, collected_at,
                   capture_manifest=manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "status": "SEC_OFFICIAL_BUNDLE_BUILT_NOT_CLEARED",
        "symbols": len(symbols),
        "mapped": len(bundle["ticker_map"]),
        "submissions": len(bundle["submissions"]),
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
