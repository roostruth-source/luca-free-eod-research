"""Offline receipts linking claimed collection times to each NY session archive.

This is a *self-reported* chain-of-custody consistency check. Even matching
hashes and plausible times do NOT prove when/where data were collected.
No network, secrets, orders, third-trial execution, or protected-branch writes.
"""
from __future__ import annotations

import datetime as dt

from mobile_outcomes import _time
from offline_multisession_audit import audit_session_bundle

UTC = dt.timezone.utc
ALLOWED_SOURCE_KINDS = frozenset({"SYNTHETIC", "UNVERIFIED_ARCHIVE"})


def _claimed_utc(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("MISSING_" + field)
    try:
        original = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("INVALID_" + field) from exc
    if original.tzinfo is None or original.utcoffset() is None:
        raise ValueError("NOT_UTC_" + field)
    if original.utcoffset() != dt.timedelta(0):
        raise ValueError("NOT_UTC_" + field)
    return original.astimezone(UTC)


def _identifier(value, field):
    if (not isinstance(value, str) or not value.strip()
            or len(value) > 120 or any(ord(char) < 32 for char in value)):
        raise ValueError("INVALID_" + field)
    return value


def audit_claimed_receipts(sessions, receipts):
    """Check one unverified receipt per session; preserve all safety disclaimers.

    Receipt keys: session_day_ny, observation_id, capture_id, source_label,
    source_kind, raw_content_sha256, commitment_sha256,
    claimed_commitment_recorded_at_utc, claimed_raw_captured_at_utc,
    validation_status, sec_status, all_grades, orders_allowed,
    real_trades_allowed, source_externally_verified,
    timestamps_externally_verified.
    """
    base = audit_session_bundle(sessions)
    if not isinstance(receipts, list) or len(receipts) != len(sessions):
        raise ValueError("RECEIPT_COVERAGE_MISMATCH")
    session_map = {s["session_day_ny"]: s for s in base["sessions"]}
    raw_map = {s["session_day_ny"]: s["raw"] for s in sessions}
    seen_days, seen_captures = set(), set()
    details = []
    warnings = list(base["warnings"])
    for receipt in receipts:
        if not isinstance(receipt, dict):
            raise ValueError("INVALID_RECEIPT")
        day = receipt.get("session_day_ny")
        if not isinstance(day, str) or day not in session_map or day in seen_days:
            raise ValueError("RECEIPT_DAY_MISSING_OR_DUPLICATED")
        seen_days.add(day)
        expected = session_map[day]
        if receipt.get("observation_id") != expected["observation_id"]:
            raise ValueError("RECEIPT_OBSERVATION_ID_MISMATCH")
        if receipt.get("raw_content_sha256") != expected["raw_content_sha256"]:
            raise ValueError("RECEIPT_RAW_HASH_MISMATCH")
        if receipt.get("commitment_sha256") != expected["commitment_sha256"]:
            raise ValueError("RECEIPT_COMMITMENT_HASH_MISMATCH")
        capture_id = _identifier(receipt.get("capture_id"), "CAPTURE_ID")
        if capture_id in seen_captures:
            raise ValueError("REUSED_CAPTURE_ID")
        seen_captures.add(capture_id)
        source_label = _identifier(receipt.get("source_label"), "SOURCE_LABEL")
        source_kind = receipt.get("source_kind")
        if not isinstance(source_kind, str) or source_kind not in ALLOWED_SOURCE_KINDS:
            raise ValueError("UNVERIFIED_SOURCE_KIND_REQUIRED")
        if (receipt.get("validation_status") != "NOT_VALIDATED"
                or receipt.get("sec_status") != "SEC_UNVERIFIED"
                or receipt.get("all_grades") != "D"
                or receipt.get("orders_allowed") is not False
                or receipt.get("real_trades_allowed") is not False
                or receipt.get("source_externally_verified") is not False
                or receipt.get("timestamps_externally_verified") is not False):
            raise ValueError("UNSAFE_OR_UNSUPPORTED_RECEIPT_CLAIM")
        anchor = _time(expected["reference_time_utc"]).astimezone(UTC)
        claimed_lock = _claimed_utc(
            receipt.get("claimed_commitment_recorded_at_utc"),
            "COMMITMENT_RECORDED_AT")
        claimed_capture = _claimed_utc(
            receipt.get("claimed_raw_captured_at_utc"), "RAW_CAPTURED_AT")
        if claimed_lock > anchor:
            raise ValueError("CLAIMED_COMMITMENT_AFTER_REFERENCE")
        if claimed_capture < anchor:
            raise ValueError("CLAIMED_CAPTURE_BEFORE_REFERENCE")
        stamps = [_time(bar["t"]).astimezone(UTC)
                  for row in raw_map[day]["rows"] for bar in row["ohlcv"]]
        # One-minute bar timestamp is its START; a full close is not knowable
        # until the following minute. This is a conservative minimum.
        if stamps and claimed_capture < max(stamps) + dt.timedelta(minutes=1):
            raise ValueError("CLAIMED_CAPTURE_BEFORE_LAST_BAR_CLOSE")
        if not stamps:
            warnings.append("ZERO_BAR_RECEIPT_CANNOT_ESTABLISH_PRICE_COLLECTION")
        if source_kind == "SYNTHETIC":
            warnings.append("SYNTHETIC_RECEIPT_NOT_MARKET_EVIDENCE")
        if any(stamp >= anchor for stamp in stamps):
            warnings.append("POST_REFERENCE_BARS_ARE_OUTCOMES_NOT_ASOF_SIGNAL_EVIDENCE")
        details.append({
            "session_day_ny": day,
            "observation_id": expected["observation_id"],
            "capture_id": capture_id,
            "source_label_claimed": source_label,
            "source_kind": source_kind,
            "claimed_commitment_recorded_at_utc": claimed_lock.isoformat(),
            "claimed_raw_captured_at_utc": claimed_capture.isoformat(),
            "raw_content_sha256": expected["raw_content_sha256"],
            "commitment_sha256": expected["commitment_sha256"],
            "raw_bar_count": len(stamps),
            "post_reference_raw_bar_count": sum(stamp >= anchor for stamp in stamps),
            "source_externally_verified": False,
            "timestamps_externally_verified": False,
        })
    return {
        "schema": "LUCA_V03_OFFLINE_CLAIMED_PROVENANCE_AUDIT_V1",
        "session_count_with_consistent_claimed_receipts": len(details),
        "receipts": sorted(details, key=lambda row: row["session_day_ny"]),
        "source_provenance_verified": False,
        "commitment_timestamp_externally_verified": False,
        "capture_timestamp_externally_verified": False,
        "actual_market_sessions_verified": False,
        "independent_sample_count_verified": 0,
        "prediction_accuracy_verified": False,
        "statistical_significance_verified": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "orders_allowed": False,
        "real_trades_allowed": False,
        "warnings": sorted(set(warnings + [
            "SELF_REPORTED_TIMES_AND_SOURCE_NOT_EXTERNALLY_VERIFIED",
            "MATCHING_HASHES_DO_NOT_PROVE_PRE_REGISTRATION_OR_SOURCE",
            "RECEIPTS_ARE_NOT_INDEPENDENT_TRADING_SAMPLES",
        ])),
        "note_ko": "제출한 출처·수집 시각·원본 해시가 서로 모순되는지만 검사합니다. 출처나 사전 등록 시각이 실제라는 증거는 아닙니다. 1분봉은 시작 시각이므로 수집 시각이 마지막 봉 시작보다 최소 1분 뒤인지 확인합니다.",
    }
