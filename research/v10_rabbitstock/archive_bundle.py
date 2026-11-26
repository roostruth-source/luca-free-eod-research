"""Build, verify, and safely recover an immutable LUCA V10 evidence bundle.

This module performs no network requests and has no order functionality.  The
bundle is deliberately self-contained so a downloaded Actions artifact can be
checked and recovered after the original runner has disappeared.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import tempfile
from zipfile import BadZipFile, ZIP_STORED, ZipFile, ZipInfo


SCHEMA = "LUCA_V10_ARCHIVE_BUNDLE_1"
ARCHIVE_KIND = "WATCH_ONLY_RESEARCH_EVIDENCE"
REPOSITORY = "roostruth-source/luca-free-eod-research"
BRANCH = "research/v10-rabbitstock-eval"
ZERO = "0" * 64
MAX_ARCHIVE_BYTES = 150_000_000
MAX_MEMBER_BYTES = 80_000_000
MAX_TOTAL_BYTES = 200_000_000
REQUIRED_FILES = (
    "daily_guard.json",
    "live_watchlist.html",
    "live_watchlist.json",
    "luca_v10_observer_report.html",
    "prospective_ledger.json",
    "prospective_outcomes.html",
    "prospective_outcomes.json",
    "restore_status.json",
    "validation_readiness.json",
)
SAFETY_JSON_FILES = (
    "daily_guard.json",
    "live_watchlist.json",
    "prospective_ledger.json",
    "prospective_outcomes.json",
    "validation_readiness.json",
)
HTML_FILES = tuple(name for name in REQUIRED_FILES if name.endswith(".html"))
ALLOWED_RESTORE_STATUS = {"RESTORED", "NO_PREVIOUS_SUCCESSFUL_RUN"}
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)


def _canonical_hash(value: dict) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _parse_time(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("timestamp_required")
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return value.astimezone(timezone.utc)


def _validate_source(source: object) -> None:
    if not isinstance(source, dict):
        raise ValueError("archive_source_required")
    if source.get("repository") != REPOSITORY or source.get("branch") != BRANCH:
        raise ValueError("archive_source_scope_invalid")
    if not re.fullmatch(r"[0-9a-f]{40}", str(source.get("commit", ""))):
        raise ValueError("archive_source_commit_invalid")
    if not re.fullmatch(r"[1-9][0-9]*", str(source.get("run_id", ""))):
        raise ValueError("archive_source_run_id_invalid")


def _walk_safety(value: object, location: str = "root") -> None:
    """Reject explicit order or validation claims anywhere in JSON evidence."""
    if isinstance(value, dict):
        for key, item in value.items():
            here = f"{location}.{key}"
            if key in {"NO_ORDERS", "WATCH_ONLY"} and item is not True:
                raise ValueError(f"unsafe_flag:{here}")
            if key in {"buy_allowed", "order_allowed", "orders_enabled",
                       "auto_trade_enabled", "prediction_accuracy_verified",
                       "performance_validation_ready"} and item is True:
                raise ValueError(f"unsafe_claim:{here}")
            _walk_safety(item, here)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_safety(item, f"{location}[{index}]")


def _load_json(payload: bytes, name: str) -> dict:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid_json:{name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{name}")
    return value


def _verify_ledger(ledger: dict) -> dict:
    if ledger.get("schema_version") != "LUCA_V10_PROSPECTIVE_LEDGER_1":
        raise ValueError("ledger_schema_invalid")
    events = ledger.get("events")
    if not isinstance(events, list) or type(ledger.get("event_count")) is not int:
        raise ValueError("ledger_events_invalid")
    if ledger["event_count"] != len(events) or len(events) > 10_000:
        raise ValueError("ledger_event_count_mismatch")
    expected = ZERO
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("ledger_event_invalid")
        actual = event.get("chain_hash")
        item = {key: value for key, value in event.items() if key != "chain_hash"}
        expected = hashlib.sha256((expected + _canonical_hash(item)).encode()).hexdigest()
        if actual != expected:
            raise ValueError("ledger_chain_invalid")
    if ledger.get("last_chain_hash") != expected:
        raise ValueError("ledger_head_invalid")
    return {
        "event_count": len(events),
        "last_chain_hash": expected,
        "source_collected_at": ledger.get("source_collected_at"),
    }


def _verify_evidence(payloads: dict[str, bytes]) -> dict:
    if set(payloads) != set(REQUIRED_FILES):
        missing = sorted(set(REQUIRED_FILES) - set(payloads))
        extra = sorted(set(payloads) - set(REQUIRED_FILES))
        raise ValueError(f"evidence_file_set_invalid:missing={missing}:extra={extra}")
    parsed = {name: _load_json(payloads[name], name)
              for name in REQUIRED_FILES if name.endswith(".json")}
    for name in SAFETY_JSON_FILES:
        value = parsed[name]
        if (value.get("WATCH_ONLY") is not True
                or value.get("NO_ORDERS") is not True
                or value.get("validation_status") != "NOT_VALIDATED"):
            raise ValueError(f"unsafe_top_level_state:{name}")
        _walk_safety(value, name)
    if parsed["daily_guard.json"].get("allowed") is not True:
        raise ValueError("daily_guard_not_allowed")
    restore = parsed["restore_status.json"].get("restore_status")
    if restore not in ALLOWED_RESTORE_STATUS:
        raise ValueError("restore_status_not_safe")
    _walk_safety(parsed["restore_status.json"], "restore_status.json")
    for name in HTML_FILES:
        try:
            text = payloads[name].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"html_utf8_required:{name}") from exc
        if not all(marker in text for marker in ("WATCH_ONLY", "NOT_VALIDATED", "NO_ORDERS")):
            raise ValueError(f"html_safety_markers_missing:{name}")
    ledger_summary = _verify_ledger(parsed["prospective_ledger.json"])
    new_york_time = parsed["daily_guard.json"].get("new_york_time")
    _parse_time(new_york_time)
    return {
        "ledger": ledger_summary,
        "observation_new_york_date": new_york_time[:10],
        "restore_status": restore,
    }


def _safe_input_payloads(input_dir: Path) -> dict[str, bytes]:
    if not input_dir.is_dir() or input_dir.is_symlink():
        raise ValueError("input_directory_invalid")
    payloads: dict[str, bytes] = {}
    total = 0
    for name in REQUIRED_FILES:
        path = input_dir / name
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"required_regular_file_missing:{name}")
        size = path.stat().st_size
        if size > MAX_MEMBER_BYTES:
            raise ValueError(f"evidence_file_too_large:{name}")
        total += size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("evidence_total_too_large")
        payload = path.read_bytes()
        if len(payload) != size or len(payload) > MAX_MEMBER_BYTES:
            raise ValueError(f"evidence_file_changed_while_reading:{name}")
        payloads[name] = payload
    return payloads


def _manifest(payloads: dict[str, bytes], source_commit: str, source_run_id: str,
              created_at: str) -> dict:
    created = _parse_time(created_at).isoformat()
    source = {
        "repository": REPOSITORY,
        "branch": BRANCH,
        "commit": source_commit,
        "run_id": str(source_run_id),
    }
    _validate_source(source)
    evidence = _verify_evidence(payloads)
    files = [
        {"name": name, "bytes": len(payloads[name]), "sha256": _sha256(payloads[name])}
        for name in sorted(payloads)
    ]
    return {
        "schema_version": SCHEMA,
        "archive_kind": ARCHIVE_KIND,
        "created_at_utc": created,
        "observation_new_york_date": evidence["observation_new_york_date"],
        "source": source,
        "safety_state": {
            "WATCH_ONLY": True,
            "validation_status": "NOT_VALIDATED",
            "sec_status": "SEC_UNVERIFIED",
            "research_grade": "D",
            "NO_ORDERS": True,
        },
        "restore_status": evidence["restore_status"],
        "ledger": evidence["ledger"],
        "content_total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }


def _zip_info(name: str) -> ZipInfo:
    info = ZipInfo(name, FIXED_ZIP_TIME)
    info.compress_type = ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o444) << 16
    return info


def build_bundle(input_dir: Path, output: Path, source_commit: str,
                 source_run_id: str, created_at: str) -> dict:
    payloads = _safe_input_payloads(input_dir)
    manifest = _manifest(payloads, source_commit, source_run_id, created_at)
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")) + "\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError("archive_output_already_exists")
    try:
        with ZipFile(output, "x", compression=ZIP_STORED) as archive:
            archive.writestr(_zip_info("manifest.json"), manifest_bytes)
            for name in sorted(payloads):
                archive.writestr(_zip_info(name), payloads[name])
    except Exception:
        output.unlink(missing_ok=True)
        raise
    if output.stat().st_size > MAX_ARCHIVE_BYTES:
        output.unlink()
        raise ValueError("archive_too_large")
    try:
        result = verify_bundle(output)
    except Exception:
        output.unlink(missing_ok=True)
        raise
    return {**result, "archive": str(output)}


def _read_archive(path: Path) -> tuple[dict, dict[str, bytes]]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("archive_regular_file_required")
    if path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("archive_too_large")
    with ZipFile(path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("duplicate_archive_member")
        expected = {"manifest.json", *REQUIRED_FILES}
        if set(names) != expected:
            raise ValueError("archive_member_set_invalid")
        total = 0
        payloads: dict[str, bytes] = {}
        for info in infos:
            name = info.filename
            mode = info.external_attr >> 16
            if (name.startswith("/") or "/" in name or "\\" in name
                    or name in {".", ".."} or stat.S_ISLNK(mode)
                    or info.is_dir() or info.compress_type != ZIP_STORED):
                raise ValueError("unsafe_archive_member")
            if info.file_size > MAX_MEMBER_BYTES:
                raise ValueError("archive_member_too_large")
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise ValueError("archive_uncompressed_total_too_large")
            payloads[name] = archive.read(info)
    manifest = _load_json(payloads.pop("manifest.json"), "manifest.json")
    return manifest, payloads


def verify_bundle(path: Path) -> dict:
    try:
        manifest, payloads = _read_archive(path)
    except BadZipFile as exc:
        raise ValueError("invalid_zip_archive") from exc
    if manifest.get("schema_version") != SCHEMA or manifest.get("archive_kind") != ARCHIVE_KIND:
        raise ValueError("archive_manifest_schema_invalid")
    _parse_time(manifest.get("created_at_utc"))
    _validate_source(manifest.get("source"))
    expected_safety = {
        "WATCH_ONLY": True,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "research_grade": "D",
        "NO_ORDERS": True,
    }
    if manifest.get("safety_state") != expected_safety:
        raise ValueError("archive_manifest_safety_invalid")
    listed = manifest.get("files")
    if (not isinstance(listed, list)
            or any(not isinstance(item, dict) for item in listed)
            or [item.get("name") for item in listed] != sorted(payloads)):
        raise ValueError("archive_manifest_file_list_invalid")
    expected_total = 0
    for item in listed:
        if not isinstance(item, dict) or set(item) != {"name", "bytes", "sha256"}:
            raise ValueError("archive_manifest_file_entry_invalid")
        name = item["name"]
        payload = payloads[name]
        if item["bytes"] != len(payload) or item["sha256"] != _sha256(payload):
            raise ValueError(f"archive_payload_digest_mismatch:{name}")
        expected_total += len(payload)
    if manifest.get("content_total_bytes") != expected_total:
        raise ValueError("archive_manifest_total_mismatch")
    evidence = _verify_evidence(payloads)
    if (manifest.get("ledger") != evidence["ledger"]
            or manifest.get("observation_new_york_date") != evidence["observation_new_york_date"]
            or manifest.get("restore_status") != evidence["restore_status"]):
        raise ValueError("archive_manifest_evidence_mismatch")
    return {
        "verified": True,
        "archive_sha256": _sha256(path.read_bytes()),
        "source_commit": manifest["source"]["commit"],
        "source_run_id": manifest["source"]["run_id"],
        "observation_new_york_date": manifest["observation_new_york_date"],
        "event_count": manifest["ledger"]["event_count"],
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def recover_bundle(path: Path, output_dir: Path) -> dict:
    result = verify_bundle(path)
    if output_dir.exists():
        raise FileExistsError("recovery_output_must_not_exist")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    manifest, payloads = _read_archive(path)
    if _sha256(path.read_bytes()) != result["archive_sha256"]:
        raise ValueError("archive_changed_during_recovery")
    temporary = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}-recovery-",
                                      dir=output_dir.parent))
    try:
        all_payloads = {
            "manifest.json": (json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")) + "\n").encode(),
            **payloads,
        }
        for name, payload in all_payloads.items():
            target = temporary / name
            with target.open("xb") as handle:
                handle.write(payload)
            target.chmod(0o444)
        temporary.rename(output_dir)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return {**result, "recovered_to": str(output_dir)}


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build")
    build.add_argument("--input-dir", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--source-commit", required=True)
    build.add_argument("--source-run-id", required=True)
    build.add_argument("--created-at", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("archive", type=Path)
    recover = subparsers.add_parser("recover")
    recover.add_argument("archive", type=Path)
    recover.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        result = build_bundle(args.input_dir, args.output, args.source_commit,
                              args.source_run_id, args.created_at)
    elif args.command == "verify":
        result = verify_bundle(args.archive)
    else:
        result = recover_bundle(args.archive, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
