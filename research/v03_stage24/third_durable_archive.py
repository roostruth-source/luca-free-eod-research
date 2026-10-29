"""Create and verify an immutable, git-backed third-trial evidence directory.

GitHub Actions artifacts remain a short-lived convenience copy. The workflow
uses this module to create a content-hashed directory that is committed to the
isolated research branch. Existing evidence directories are never overwritten.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from iex_raw_evidence import canonical_sha256, replay_raw_evidence
from third_trial_gate import BASELINE_COMMIT


UTC = dt.timezone.utc
REQUIRED = (
    "frozen_t0.json",
    "forward_review.json",
    "iex_timestamp_provenance.json",
    "iex_raw_ohlcv_evidence.json",
    "replay_result.json",
)
MANIFEST = "durable_manifest.json"
MAX_FILE_BYTES = 1_000_000


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf8"))


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        while True:
            chunk = source.read(64 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _safe(document, require_grade=False):
    if (document.get("validation_status") != "NOT_VALIDATED" or
            document.get("sec_status") != "SEC_UNVERIFIED" or
            document.get("real_trades_allowed") is not False):
        raise ValueError("UNSAFE_EVIDENCE_STATUS")
    if require_grade and (document.get("all_grades") != "D" or
                          document.get("orders_allowed") is not False):
        raise ValueError("UNSAFE_GRADE_OR_ORDER_STATUS")


def validate_complete_source(source):
    root = Path(source)
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        raise ValueError("MISSING_COMPLETE_EVIDENCE:" + ",".join(missing))
    for name in REQUIRED:
        size = (root / name).stat().st_size
        if not 0 < size <= MAX_FILE_BYTES:
            raise ValueError("INVALID_EVIDENCE_SIZE:" + name)
    frozen = _load(root / "frozen_t0.json")
    review = _load(root / "forward_review.json")
    timestamps = _load(root / "iex_timestamp_provenance.json")
    raw = _load(root / "iex_raw_ohlcv_evidence.json")
    saved_replay = _load(root / "replay_result.json")
    for document in (frozen, review, timestamps):
        _safe(document)
    _safe(raw, require_grade=True)
    _safe(saved_replay, require_grade=True)
    replay = replay_raw_evidence(raw, frozen, review, timestamps)
    if replay != saved_replay:
        raise ValueError("SAVED_REPLAY_RESULT_MISMATCH")
    return replay


def _valid_run_id(run_id):
    return type(run_id) is str and run_id.isdecimal() and 1 <= len(run_id) <= 20


def _valid_commit(sha):
    return (type(sha) is str and len(sha) == 40 and
            all(char in "0123456789abcdef" for char in sha))


def build_archive(source, archive_root, run_id, source_commit,
                  created_at, synthetic_only=False, allow_incomplete=False):
    if not _valid_run_id(run_id):
        raise ValueError("BAD_RUN_ID")
    if not _valid_commit(source_commit):
        raise ValueError("BAD_SOURCE_COMMIT")
    if type(created_at) is not dt.datetime or created_at.tzinfo is None:
        raise ValueError("AWARE_CREATED_AT_REQUIRED")
    created_at = created_at.astimezone(UTC)
    source = Path(source)
    root = Path(archive_root)
    target = root / run_id
    if target.exists():
        raise FileExistsError("DURABLE_ARCHIVE_ALREADY_EXISTS")
    if not (source / "iex_raw_ohlcv_evidence.json").is_file():
        raise ValueError("NO_RAW_OHLCV_TO_ARCHIVE")
    complete = True
    failure = None
    try:
        replay = validate_complete_source(source)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        if not allow_incomplete:
            raise
        complete = False
        replay = None
        failure = str(exc)[:200]
    root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="." + run_id + "-", dir=root))
    try:
        copied = []
        for name in REQUIRED:
            original = source / name
            if not original.is_file():
                continue
            if not 0 < original.stat().st_size <= MAX_FILE_BYTES:
                raise ValueError("INVALID_EVIDENCE_SIZE:" + name)
            shutil.copyfile(original, temporary / name)
            copied.append(name)
        files = {
            name: {
                "sha256": _file_sha256(temporary / name),
                "bytes": (temporary / name).stat().st_size,
            }
            for name in copied
        }
        manifest = {
            "schema": "LUCA_V03_THIRD_DURABLE_ARCHIVE_V1",
            "run_id": run_id,
            "source_commit": source_commit,
            "baseline_commit": BASELINE_COMMIT,
            "created_at_utc": created_at.isoformat(),
            "archive_status": "COMPLETE_REPLAY_VERIFIED" if complete else "INCOMPLETE_FAIL_CLOSED",
            "failure_reason": failure,
            "synthetic_only": synthetic_only is True,
            "replay_verified": complete,
            "raw_ohlcv_present": "iex_raw_ohlcv_evidence.json" in copied,
            "storage": "GIT_RESEARCH_BRANCH_IMMUTABLE_RUN_DIRECTORY",
            "github_actions_retention_is_only_secondary_copy": True,
            "files": files,
            "validation_status": "NOT_VALIDATED",
            "sec_status": "SEC_UNVERIFIED",
            "all_grades": "D",
            "real_trades_allowed": False,
            "orders_allowed": False,
        }
        if replay is not None:
            manifest["replay_summary_sha256"] = canonical_sha256(replay)
        manifest["sha256"] = canonical_sha256(manifest)
        (temporary / MANIFEST).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
        temporary.replace(target)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    verify_archive(target, require_complete=complete)
    return target, manifest


def verify_archive(directory, require_complete=True):
    root = Path(directory)
    manifest = _load(root / MANIFEST)
    if manifest.get("schema") != "LUCA_V03_THIRD_DURABLE_ARCHIVE_V1":
        raise ValueError("BAD_DURABLE_MANIFEST_SCHEMA")
    supplied = manifest.get("sha256")
    unhashed = {key: value for key, value in manifest.items() if key != "sha256"}
    if supplied != canonical_sha256(unhashed):
        raise ValueError("DURABLE_MANIFEST_HASH_MISMATCH")
    if (manifest.get("validation_status") != "NOT_VALIDATED" or
            manifest.get("sec_status") != "SEC_UNVERIFIED" or
            manifest.get("all_grades") != "D" or
            manifest.get("real_trades_allowed") is not False or
            manifest.get("orders_allowed") is not False):
        raise ValueError("UNSAFE_DURABLE_MANIFEST")
    files = manifest.get("files")
    if type(files) is not dict or "iex_raw_ohlcv_evidence.json" not in files:
        raise ValueError("RAW_OHLCV_NOT_IN_MANIFEST")
    if set(path.name for path in root.iterdir() if path.is_file()) != set(files) | {MANIFEST}:
        raise ValueError("UNLISTED_DURABLE_FILE")
    for name, details in files.items():
        path = root / name
        if (not path.is_file() or type(details) is not dict or
                details.get("bytes") != path.stat().st_size or
                details.get("sha256") != _file_sha256(path)):
            raise ValueError("DURABLE_FILE_HASH_MISMATCH:" + name)
    if require_complete:
        if (manifest.get("archive_status") != "COMPLETE_REPLAY_VERIFIED" or
                manifest.get("replay_verified") is not True or set(files) != set(REQUIRED)):
            raise ValueError("DURABLE_ARCHIVE_NOT_COMPLETE")
        replay = validate_complete_source(root)
        if manifest.get("replay_summary_sha256") != canonical_sha256(replay):
            raise ValueError("DURABLE_REPLAY_HASH_MISMATCH")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--synthetic-only", action="store_true")
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    target, manifest = build_archive(
        args.source, args.archive_root, args.run_id, args.source_commit,
        dt.datetime.now(UTC), args.synthetic_only, args.allow_incomplete)
    print(json.dumps({
        "archive": str(target), "status": manifest["archive_status"],
        "synthetic_only": manifest["synthetic_only"],
        "validation_status": "NOT_VALIDATED", "orders_allowed": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
