"""Offline fixed-time commitment manifest: integrity check, not proof of pre-registration."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from mobile_outcomes import _time

SCHEMA = "LUCA_V03_REFERENCE_TIME_COMMITMENT_V1"

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def create_commitment(reference_time_utc, symbols, observation_id):
    instant = _time(reference_time_utc)
    if not isinstance(observation_id, str) or not observation_id.strip():
        raise ValueError("INVALID_OBSERVATION_ID")
    if not isinstance(symbols, list) or not symbols or any(
            not isinstance(s, str) or not s.strip() for s in symbols):
        raise ValueError("INVALID_SYMBOLS")
    if len(set(symbols)) != len(symbols):
        raise ValueError("DUPLICATE_SYMBOL")
    payload = {"schema": SCHEMA, "observation_id": observation_id,
               "reference_time_utc": instant.isoformat(),
               "symbols": sorted(symbols),
               "validation_status": "NOT_VALIDATED",
               "orders_allowed": False}
    return {"payload": payload, "sha256": hashlib.sha256(canonical(payload).encode("utf8")).hexdigest()}

def verify_commitment(manifest, raw, requested_reference_time_utc):
    if not isinstance(manifest, dict) or not isinstance(manifest.get("payload"), dict):
        raise ValueError("INVALID_MANIFEST")
    payload = manifest["payload"]
    if payload.get("schema") != SCHEMA or payload.get("validation_status") != "NOT_VALIDATED" or payload.get("orders_allowed") is not False:
        raise ValueError("UNSAFE_MANIFEST")
    digest = hashlib.sha256(canonical(payload).encode("utf8")).hexdigest()
    if manifest.get("sha256") != digest:
        raise ValueError("COMMITMENT_HASH_MISMATCH")
    if payload.get("reference_time_utc") != _time(requested_reference_time_utc).isoformat():
        raise ValueError("REFERENCE_TIME_CHANGED")
    if not isinstance(raw, dict) or not isinstance(raw.get("rows"), list):
        raise ValueError("INVALID_RAW_ROWS")
    symbols = [r.get("symbol") for r in raw["rows"] if isinstance(r, dict)]
    if len(symbols) != len(raw["rows"]) or sorted(symbols) != payload.get("symbols"):
        raise ValueError("CANDIDATE_UNIVERSE_CHANGED")
    return True

def compare_committed(raw, manifest):
    from offline_fixed_time_comparison import compare
    if not isinstance(manifest, dict) or not isinstance(manifest.get("payload"), dict):
        raise ValueError("INVALID_MANIFEST")
    stamp = manifest["payload"].get("reference_time_utc")
    verify_commitment(manifest, raw, stamp)
    result = compare(raw, stamp)
    result["commitment_sha256"] = manifest["sha256"]
    result["commitment_timestamp_externally_verified"] = False
    result["warning_ko"] += " 해시값은 파일 변조 탐지용이며 실제 사전 등록 시각을 증명하지 않습니다."
    return result
