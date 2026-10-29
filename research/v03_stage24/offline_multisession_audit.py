"""Offline multi-session evidence audit: one raw archive and one commitment per NY day.

This checks structural consistency only. It cannot establish archival provenance,
pre-registration, actual exchange opening, or statistical independence.
No network access, orders, or changes to live workflows.
"""
from __future__ import annotations

from collections import Counter
import datetime as dt
import hashlib
from zoneinfo import ZoneInfo

from mobile_outcomes import _time
from nyse_session_gate import EARLY_CLOSES_2026
from offline_cohort_scorecard import scorecard
from offline_reference_commitment import canonical
from offline_session_integrity import _calendar_label

NY = ZoneInfo("America/New_York")
OPEN = dt.time(9, 30)
CLOSE = dt.time(16, 0)
EARLY_CLOSE = dt.time(13, 0)
ALLOWED_DAYS = {"SCHEDULED_WEEKDAY_NOT_LIVE_VERIFIED", "SCHEDULED_EARLY_CLOSE"}


def _date(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_NY_SESSION_DATE")
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_NY_SESSION_DATE") from exc
    if parsed.isoformat() != value:
        raise ValueError("INVALID_NY_SESSION_DATE")
    return parsed


def _in_regular_session(instant, day):
    local = _time(instant).astimezone(NY)
    close = EARLY_CLOSE if day in EARLY_CLOSES_2026 else CLOSE
    return local.date() == day and OPEN <= local.time().replace(tzinfo=None) < close


def _price_sequence_fingerprint(raw):
    # Time-independent warning only: matching prices may be legitimate.
    sequence = [{"symbol": row["symbol"],
                 "bars": [{key: bar.get(key) for key in ("o", "h", "l", "c", "v")}
                          for bar in row["ohlcv"]]}
                for row in sorted(raw["rows"], key=lambda r: r["symbol"])]
    return hashlib.sha256(canonical(sequence).encode("utf8")).hexdigest()


def audit_session_bundle(sessions):
    """Require distinct NY session dates, commitment IDs and raw contents.

    Input: [{session_day_ny: YYYY-MM-DD, manifest: {...}, raw: {...}}, ...].
    Scores remain per-session only; do NOT aggregate candidate rows into an
    independent-sample win rate.
    """
    if not isinstance(sessions, list) or not sessions:
        raise ValueError("MISSING_SESSION_BUNDLE")
    days, ids, raw_hashes = set(), set(), set()
    price_fingerprints = {}
    repeated_price_sequences = []
    counts = Counter()
    summaries = []
    for item in sessions:
        if not isinstance(item, dict):
            raise ValueError("INVALID_SESSION_ENTRY")
        day = _date(item.get("session_day_ny"))
        if day in days:
            raise ValueError("DUPLICATE_NY_SESSION_DAY")
        label = _calendar_label(day)
        if label not in ALLOWED_DAYS:
            raise ValueError("CLOSED_OR_UNSUPPORTED_NY_SESSION_DATE")
        manifest, raw = item.get("manifest"), item.get("raw")
        if not isinstance(manifest, dict) or not isinstance(manifest.get("payload"), dict):
            raise ValueError("INVALID_SESSION_MANIFEST")
        payload = manifest["payload"]
        observation_id = payload.get("observation_id")
        if not isinstance(observation_id, str) or not observation_id.strip():
            raise ValueError("INVALID_OBSERVATION_ID")
        if observation_id in ids:
            raise ValueError("DUPLICATE_OBSERVATION_ID")
        anchor = payload.get("reference_time_utc")
        if not _in_regular_session(anchor, day):
            raise ValueError("REFERENCE_OUTSIDE_DECLARED_NY_SESSION")
        if _time(anchor).second or _time(anchor).microsecond:
            raise ValueError("REFERENCE_NOT_MINUTE_ALIGNED")
        # Validate all raw safety fields, every six-bar signal, fixed reference
        # time, commitment hash and frozen candidate universe before counting.
        result = scorecard(raw, manifest)
        if not isinstance(raw, dict) or not isinstance(raw.get("rows"), list):
            raise ValueError("INVALID_RAW_ROWS")
        for row in raw["rows"]:
            for bar in row["ohlcv"]:
                if not _in_regular_session(bar["t"], day):
                    raise ValueError("RAW_BAR_OUTSIDE_DECLARED_NY_SESSION")
                stamp = _time(bar["t"])
                if stamp.second or stamp.microsecond:
                    raise ValueError("RAW_BAR_NOT_MINUTE_ALIGNED")
        fingerprint = hashlib.sha256(canonical(raw).encode("utf8")).hexdigest()
        if fingerprint in raw_hashes:
            raise ValueError("REUSED_RAW_ARCHIVE_CONTENT")
        raw_hashes.add(fingerprint)
        price_signature = _price_sequence_fingerprint(raw)
        if price_signature in price_fingerprints:
            repeated_price_sequences.append({
                "first_session_day_ny": price_fingerprints[price_signature],
                "repeated_session_day_ny": day.isoformat(),
            })
        else:
            price_fingerprints[price_signature] = day.isoformat()
        ids.add(observation_id)
        days.add(day)
        symbols = [row["symbol"] for row in raw["rows"]]
        counts.update(symbols)
        summaries.append({
            "session_day_ny": day.isoformat(),
            "calendar_status": label,
            "observation_id": observation_id,
            "reference_time_utc": result["reference_time_utc"],
            "commitment_sha256": result["commitment_sha256"],
            "raw_content_sha256": fingerprint,
            "candidate_count": len(symbols),
            "groups": result["groups"],
            "source_and_timestamp_externally_verified": False,
        })
    repeated = {symbol: n for symbol, n in sorted(counts.items()) if n > 1}
    warnings = ["SCHEDULED_CALENDAR_ONLY_NOT_ACTUAL_OPEN",
                "RAW_HASH_IS_NOT_ARCHIVAL_PROOF",
                "COMMITMENT_HASH_IS_NOT_PRE_REGISTRATION_PROOF",
                "SESSION_RECORDS_NOT_INDEPENDENT_SAMPLES"]
    if repeated:
        warnings.append("REPEATED_SYMBOL_ACROSS_DAYS_NOT_INDEPENDENT")
    if repeated_price_sequences:
        warnings.append("IDENTICAL_PRICE_SEQUENCE_ACROSS_DAYS_REVIEW")
    if any(s["calendar_status"] == "SCHEDULED_EARLY_CLOSE" for s in summaries):
        warnings.append("EARLY_CLOSE_REQUIRES_MISSING_HORIZON_REVIEW")
    return {
        "schema": "LUCA_V03_OFFLINE_MULTI_SESSION_AUDIT_V1",
        "claimed_session_days_with_structurally_consistent_records": len(days),
        "unique_symbols": len(counts),
        "symbol_session_pairs": sum(counts.values()),
        "repeated_symbols": repeated,
        "matching_price_sequences_ignoring_timestamps": repeated_price_sequences,
        "extra_symbol_sessions_beyond_first": sum(n - 1 for n in counts.values()),
        "sessions": sorted(summaries, key=lambda s: s["session_day_ny"]),
        "independent_session_count_verified": 0,
        "independent_sample_count_verified": 0,
        "actual_market_sessions_verified": False,
        "source_provenance_verified": False,
        "commitment_timestamp_externally_verified": False,
        "prediction_accuracy_verified": False,
        "statistical_significance_verified": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "orders_allowed": False,
        "real_trades_allowed": False,
        "warnings": warnings,
        "note_ko": "날짜마다 다른 원본·기준 시각·종목 명단이 있는지만 오프라인 검사했습니다. 날짜만 바꾼 동일 가격 배열은 검토 경고를 표시하며 실제 수집 여부는 증명하지 못합니다. 종목-날짜 기록을 독립 표본이나 검증된 승률로 계산하지 않습니다.",
    }
