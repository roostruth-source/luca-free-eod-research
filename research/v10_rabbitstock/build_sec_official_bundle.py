"""Build a bounded SEC-official bundle from already downloaded raw JSON.

This command performs no network requests.  The raw files must have been
downloaded from the declared SEC URLs by an environment that is permitted to
access them.  The resulting bundle is validated again before it is written.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

from sec_official_bundle import (SCHEMA, SOURCE, TICKERS_URL, canonical_sha256,
                                 validate_official_bundle)

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


def build(ticker_payload: dict, submission_payloads: dict[str, dict],
          symbols: list[str], collected_at: datetime) -> dict:
    if collected_at.tzinfo is None:
        raise ValueError("sec_bundle_collected_timezone_required")
    full_map = ticker_cik_map(ticker_payload)
    selected_map = {symbol: full_map[symbol] for symbol in symbols
                    if symbol in full_map}
    collected_text = collected_at.isoformat()
    submissions = {}
    for symbol, payload in submission_payloads.items():
        if symbol not in selected_map:
            raise ValueError("sec_submission_symbol_not_mapped")
        cik = selected_map[symbol]
        if payload.get("cik") != cik:
            raise ValueError("sec_submission_cik_mismatch")
        submissions[symbol] = {
            "source_url": f"https://data.sec.gov/submissions/CIK{cik:010d}.json",
            "retrieved_at_utc": collected_text,
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
    validate_official_bundle(bundle, collected_at, symbols)
    return bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker-map", type=Path, required=True)
    parser.add_argument("--submissions-dir", type=Path, required=True)
    parser.add_argument("--symbols", type=Path, required=True,
                        help="JSON array of uppercase ticker symbols")
    parser.add_argument("--collected-at", required=True,
                        help="timezone-aware ISO timestamp")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("sec_bundle_no_overwrite")
    collected_at = datetime.fromisoformat(args.collected_at.replace("Z", "+00:00"))
    symbols = _read_symbols(args.symbols)
    submissions = {}
    for path in sorted(args.submissions_dir.glob("*.json")):
        submissions[path.stem.upper()] = _read_object(path)
    bundle = build(_read_object(args.ticker_map), submissions, symbols, collected_at)
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
