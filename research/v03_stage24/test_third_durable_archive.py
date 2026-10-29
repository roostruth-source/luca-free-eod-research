"""Offline durable archive tests using synthetic evidence only."""
import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from iex_raw_evidence import replay_raw_evidence
from test_iex_raw_evidence import fixture
from third_durable_archive import build_archive, verify_archive


UTC = dt.timezone.utc
SOURCE_COMMIT = "1" * 40


def source_directory(root):
    frozen, _, review, timestamps, raw = fixture()
    replay = replay_raw_evidence(raw, frozen, review, timestamps)
    documents = {
        "frozen_t0.json": frozen,
        "forward_review.json": review,
        "iex_timestamp_provenance.json": timestamps,
        "iex_raw_ohlcv_evidence.json": raw,
        "replay_result.json": replay,
    }
    source = Path(root) / "source"
    source.mkdir()
    for name, document in documents.items():
        (source / name).write_text(json.dumps(document) + "\n", encoding="utf8")
    return source


class DurableArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = source_directory(self.root)
        self.archives = self.root / "archives"

    def build(self, **kwargs):
        return build_archive(
            self.source, self.archives, "123456", SOURCE_COMMIT,
            dt.datetime(2026, 10, 29, 3, 0, tzinfo=UTC),
            synthetic_only=True, **kwargs)

    def test_complete_replay_verified_git_archive(self):
        target, manifest = self.build()
        self.assertEqual(manifest["archive_status"], "COMPLETE_REPLAY_VERIFIED")
        self.assertTrue(manifest["replay_verified"])
        self.assertTrue(manifest["synthetic_only"])
        self.assertEqual(manifest["all_grades"], "D")
        self.assertFalse(manifest["orders_allowed"])
        self.assertEqual(verify_archive(target), manifest)

    def test_raw_ohlcv_and_all_replay_inputs_persist(self):
        target, manifest = self.build()
        self.assertEqual(set(manifest["files"]), {
            "frozen_t0.json", "forward_review.json",
            "iex_timestamp_provenance.json", "iex_raw_ohlcv_evidence.json",
            "replay_result.json",
        })
        self.assertTrue((target / "iex_raw_ohlcv_evidence.json").is_file())

    def test_duplicate_run_directory_never_overwrites(self):
        target, _ = self.build()
        before = (target / "durable_manifest.json").read_bytes()
        with self.assertRaisesRegex(FileExistsError, "DURABLE_ARCHIVE_ALREADY_EXISTS"):
            self.build()
        self.assertEqual((target / "durable_manifest.json").read_bytes(), before)

    def test_tampered_archived_bar_fails_hash_verification(self):
        target, _ = self.build()
        raw_path = target / "iex_raw_ohlcv_evidence.json"
        raw = json.loads(raw_path.read_text())
        raw["rows"][0]["ohlcv"][0]["c"] = 9.9
        raw_path.write_text(json.dumps(raw) + "\n")
        with self.assertRaisesRegex(ValueError, "DURABLE_FILE_HASH_MISMATCH"):
            verify_archive(target)

    def test_missing_replay_can_be_quarantined_fail_closed(self):
        (self.source / "replay_result.json").unlink()
        target, manifest = self.build(allow_incomplete=True)
        self.assertEqual(manifest["archive_status"], "INCOMPLETE_FAIL_CLOSED")
        self.assertFalse(manifest["replay_verified"])
        self.assertTrue(manifest["raw_ohlcv_present"])
        self.assertFalse(manifest["orders_allowed"])
        self.assertEqual(verify_archive(target, require_complete=False), manifest)

    def test_incomplete_without_explicit_mode_blocks(self):
        (self.source / "replay_result.json").unlink()
        with self.assertRaisesRegex(ValueError, "MISSING_COMPLETE_EVIDENCE"):
            self.build()

    def test_no_raw_ohlcv_never_creates_archive(self):
        (self.source / "iex_raw_ohlcv_evidence.json").unlink()
        with self.assertRaisesRegex(ValueError, "NO_RAW_OHLCV_TO_ARCHIVE"):
            self.build(allow_incomplete=True)
        self.assertFalse(self.archives.exists())

    def test_changed_saved_replay_blocks_complete_archive(self):
        replay_path = self.source / "replay_result.json"
        changed = json.loads(replay_path.read_text())
        changed["bars_replayed"] += 1
        replay_path.write_text(json.dumps(changed) + "\n")
        with self.assertRaisesRegex(ValueError, "SAVED_REPLAY_RESULT_MISMATCH"):
            self.build()

    def test_unsafe_raw_grade_blocks_complete_archive(self):
        raw_path = self.source / "iex_raw_ohlcv_evidence.json"
        raw = json.loads(raw_path.read_text())
        raw["all_grades"] = "A"
        raw_path.write_text(json.dumps(raw) + "\n")
        with self.assertRaisesRegex(ValueError, "UNSAFE_GRADE_OR_ORDER_STATUS"):
            self.build()

    def test_bad_run_or_commit_identity_blocks(self):
        with self.assertRaisesRegex(ValueError, "BAD_RUN_ID"):
            build_archive(self.source, self.archives, "../bad", SOURCE_COMMIT,
                          dt.datetime.now(UTC), synthetic_only=True)
        with self.assertRaisesRegex(ValueError, "BAD_SOURCE_COMMIT"):
            build_archive(self.source, self.archives, "123", "bad",
                          dt.datetime.now(UTC), synthetic_only=True)


if __name__ == "__main__":
    unittest.main()
