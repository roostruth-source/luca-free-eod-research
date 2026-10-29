"""Immutable IEX 1-minute OHLCV evidence and deterministic signal replay.

This module does not fetch market data and does not define a new signal rule.
It archives the already validated bars passed to the unchanged ``find_patterns``
function, records the exact six input bars behind every recorded pattern, and
can later replay those raw bars against the separately archived review.

Research only: D grade, SEC_UNVERIFIED, NOT_VALIDATED, NO_ORDERS.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import inspect
import json
from pathlib import Path

from forward_outcomes_iex import parse_utc, validate_origins
from iex_1min_research import MIN_CONTEXT, find_patterns, valid_bar
from prospective_iex_research import review as build_review


SCHEMA = "LUCA_V03_IEX_RAW_OHLCV_EVIDENCE_V1"
REPLAY_SCHEMA = "LUCA_V03_IEX_RAW_OHLCV_REPLAY_V1"
MAX_NAMES = 12
MAX_MINUTES = 35
MAX_OUTPUT_BYTES = 1_000_000


def canonical_sha256(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf8")).hexdigest()


def evidence_sha256(document):
    return canonical_sha256({k: v for k, v in document.items() if k != "sha256"})


def signal_formula_source_sha256():
    """Bind each archive to the exact unchanged detector source code."""
    return hashlib.sha256(inspect.getsource(find_patterns).encode("utf8")).hexdigest()


def _contiguous_windows(rows):
    windows = []
    for index in range(MIN_CONTEXT - 1, len(rows)):
        window = rows[index - MIN_CONTEXT + 1:index + 1]
        stamps = [parse_utc(item["t"]) for item in window]
        if all(b - a == dt.timedelta(minutes=1) for a, b in zip(stamps, stamps[1:])):
            windows.append(window)
    return windows


def _signal_evidence(rows):
    """Call the unchanged detector and attach its exact six-bar inputs."""
    signals = find_patterns(rows)
    by_end = {window[-1]["t"]: window for window in _contiguous_windows(rows)}
    detailed = []
    for signal in signals:
        window = by_end.get(signal["signal_bar_start_utc"])
        if window is None or len(window) != MIN_CONTEXT:
            raise ValueError("SIGNAL_INPUT_WINDOW_NOT_FOUND")
        detailed.append({
            "signal": signal,
            "calculation_input_ohlcv": window,
        })
    return detailed, len(by_end)


def _safe_status(document, label):
    if (document.get("validation_status") != "NOT_VALIDATED" or
            document.get("sec_status") != "SEC_UNVERIFIED" or
            document.get("real_trades_allowed") is not False):
        raise ValueError("UNSAFE_" + label)


def build_raw_evidence(frozen, review, bars, timestamp_provenance):
    """Build a self-hashed archive from the exact bars used by the review."""
    t0, reviewed, _ = validate_origins(frozen, review)
    _safe_status(review, "REVIEW")
    _safe_status(timestamp_provenance, "TIMESTAMP_PROVENANCE")
    if timestamp_provenance.get("schema") != "LUCA_V03_IEX_TIMESTAMP_PROVENANCE_V1":
        raise ValueError("BAD_TIMESTAMP_PROVENANCE_SCHEMA")
    if timestamp_provenance.get("frozen_t0_sha256") != frozen.get("sha256"):
        raise ValueError("FROZEN_HASH_MISMATCH")
    names = frozen.get("candidates")
    if (type(names) is not list or not 0 < len(names) <= MAX_NAMES or
            type(bars) is not dict or set(bars) != set(names)):
        raise ValueError("BAR_UNIVERSE_DRIFT")
    results = review.get("results")
    provenance_rows = timestamp_provenance.get("rows")
    if (type(results) is not list or type(provenance_rows) is not list or
            [x.get("symbol") for x in results] != names or
            [x.get("symbol") for x in provenance_rows] != names):
        raise ValueError("EVIDENCE_SYMBOL_ORDER_MISMATCH")
    start = parse_utc(review["first_allowed_bar_start_utc"])
    end = parse_utc(review["last_allowed_bar_start_utc"])
    minutes = int((end - start).total_seconds() // 60) + 1
    if not 1 <= minutes <= MAX_MINUTES:
        raise ValueError("INVALID_REVIEW_WINDOW")
    grid = [start + dt.timedelta(minutes=index) for index in range(minutes)]

    archived_rows = []
    for symbol, recorded, timestamps in zip(names, results, provenance_rows):
        source_rows = bars[symbol]
        if type(source_rows) is not list or len(source_rows) > MAX_MINUTES:
            raise ValueError("BAD_BAR_LIST")
        clean = [valid_bar(item, start, end) for item in source_rows]
        clean.sort(key=lambda item: item["t"])
        if len({item["t"] for item in clean}) != len(clean):
            raise ValueError("DUPLICATE_BAR")
        observed = [item["t"] for item in clean]
        if observed != timestamps.get("observed_bar_start_utc"):
            raise ValueError("BAR_TIMESTAMP_PROVENANCE_MISMATCH")
        missing = timestamps.get("missing_iex_bar_start_utc")
        expected_missing = [stamp.isoformat() for stamp in grid
                            if stamp.isoformat() not in observed]
        if (type(missing) is not list or missing != expected_missing or
                timestamps.get("expected_minutes") != minutes or
                timestamps.get("observed_minutes") != len(observed) or
                timestamps.get("complete") is not (not missing)):
            raise ValueError("INCOMPLETE_MINUTE_GRID")
        detailed, evaluable = _signal_evidence(clean)
        signals = [item["signal"] for item in detailed]
        if (recorded.get("observed_iex_bars") != len(clean) or
                recorded.get("pattern_count") != len(signals) or
                recorded.get("first_pattern") != (signals[0] if signals else None)):
            raise ValueError("RECORDED_SIGNAL_MISMATCH")
        if not clean:
            status = "NO_IEX_BARS_RECORDED"
        elif not evaluable:
            status = "NO_EVALUABLE_SIX_MINUTE_WINDOW"
        elif signals:
            status = "SIGNAL_RECORDED"
        else:
            status = "NO_SIGNAL_IN_EVALUABLE_WINDOWS"
        archived_rows.append({
            "symbol": symbol,
            "record_status": status,
            "observed_minutes": len(clean),
            "missing_minutes": len(missing),
            "missing_iex_bar_start_utc": missing,
            "evaluable_six_minute_windows": evaluable,
            "signal_count": len(signals),
            "signals": detailed,
            "ohlcv": clean,
            "grade": "D",
            "buy_allowed": False,
            "sec_status": "SEC_UNVERIFIED",
        })
    if sum(row["observed_minutes"] for row in archived_rows) != review.get("observed_iex_bars"):
        raise ValueError("REVIEW_TOTAL_MISMATCH")

    document = {
        "schema": SCHEMA,
        "frozen_t0_sha256": frozen["sha256"],
        "review_sha256": canonical_sha256(review),
        "timestamp_provenance_sha256": canonical_sha256(timestamp_provenance),
        "selected_at_utc": t0.isoformat(),
        "reviewed_at_utc": reviewed.isoformat(),
        "first_allowed_bar_start_utc": start.isoformat(),
        "last_allowed_bar_start_utc": end.isoformat(),
        "feed": "IEX_SINGLE_EXCHANGE_NOT_SIP",
        "adjustment": "raw",
        "timeframe": "1Min",
        "symbols": len(names),
        "expected_minutes_per_symbol": minutes,
        "observed_iex_bars": sum(row["observed_minutes"] for row in archived_rows),
        "signal_symbols": sum(row["signal_count"] > 0 for row in archived_rows),
        "rows": archived_rows,
        "canonical_ohlcv_archived": True,
        "source_http_response_bytes_archived": False,
        "missing_iex_bar_cause_unknown": True,
        "not_full_market_coverage": True,
        "signal_formula_source_sha256": signal_formula_source_sha256(),
        "signal_formula_changed": False,
        "prediction_accuracy_verified": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "real_trades_allowed": False,
        "orders_allowed": False,
    }
    document["sha256"] = evidence_sha256(document)
    return document


def replay_raw_evidence(evidence, frozen, recorded_review, timestamp_provenance):
    """Recalculate signals from archived OHLCV and compare to old records."""
    if type(evidence) is not dict or evidence.get("schema") != SCHEMA:
        raise ValueError("BAD_RAW_EVIDENCE_SCHEMA")
    _safe_status(evidence, "RAW_EVIDENCE")
    if evidence.get("orders_allowed") is not False or evidence.get("all_grades") != "D":
        raise ValueError("UNSAFE_RAW_EVIDENCE")
    if evidence.get("sha256") != evidence_sha256(evidence):
        raise ValueError("RAW_EVIDENCE_HASH_MISMATCH")
    if evidence.get("signal_formula_source_sha256") != signal_formula_source_sha256():
        raise ValueError("SIGNAL_FORMULA_SOURCE_CHANGED")
    if evidence.get("frozen_t0_sha256") != frozen.get("sha256"):
        raise ValueError("FROZEN_HASH_MISMATCH")
    if evidence.get("review_sha256") != canonical_sha256(recorded_review):
        raise ValueError("REVIEW_HASH_MISMATCH")
    if evidence.get("timestamp_provenance_sha256") != canonical_sha256(timestamp_provenance):
        raise ValueError("TIMESTAMP_PROVENANCE_HASH_MISMATCH")
    names = frozen.get("candidates")
    rows = evidence.get("rows")
    if type(rows) is not list or [row.get("symbol") for row in rows] != names:
        raise ValueError("RAW_EVIDENCE_UNIVERSE_MISMATCH")
    bars = {row["symbol"]: row.get("ohlcv") for row in rows}
    reviewed_at = parse_utc(recorded_review["reviewed_at_utc"])
    recalculated_review = build_review(frozen, bars, reviewed_at)
    if recalculated_review != recorded_review:
        raise ValueError("RECALCULATED_REVIEW_MISMATCH")
    rebuilt = build_raw_evidence(
        frozen, recalculated_review, bars, timestamp_provenance)
    if rebuilt != evidence:
        raise ValueError("RECALCULATED_RAW_EVIDENCE_MISMATCH")
    return {
        "schema": REPLAY_SCHEMA,
        "raw_evidence_sha256": evidence["sha256"],
        "review_sha256": evidence["review_sha256"],
        "symbols_replayed": len(rows),
        "bars_replayed": evidence["observed_iex_bars"],
        "signal_symbols_replayed": evidence["signal_symbols"],
        "recorded_review_exact_match": True,
        "recorded_signal_inputs_exact_match": True,
        "signal_formula_changed": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "real_trades_allowed": False,
        "orders_allowed": False,
    }


def write_new(path, document):
    dest = Path(path)
    if dest.exists():
        raise FileExistsError("IMMUTABLE_RAW_EVIDENCE_EXISTS")
    encoded = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf8")
    if len(encoded) > MAX_OUTPUT_BYTES:
        raise ValueError("RAW_EVIDENCE_TOO_LARGE")
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("xb") as output:
        output.write(encoded)


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--frozen", required=True)
    parser.add_argument("--review", required=True)
    parser.add_argument("--timestamps", required=True)
    parser.add_argument("--raw-evidence", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = replay_raw_evidence(
        _load(args.raw_evidence), _load(args.frozen), _load(args.review),
        _load(args.timestamps))
    if args.output:
        write_new(args.output, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
