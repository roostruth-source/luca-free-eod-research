"""Fake-git tests for long-term archive publication; no GitHub write occurs."""
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from test_third_durable_archive import SOURCE_COMMIT, source_directory
from third_archive_publish import (
    ARCHIVE_PATH, BRANCH, PublishFailed, publish_archive,
    record_failure, verify_success_status,
)
from third_durable_archive import build_archive


UTC = dt.timezone.utc
HEAD = "a" * 40


class FakeGit:
    def __init__(self, fail_command=None):
        self.fail_command = fail_command
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        joined = " ".join(args)
        if self.fail_command and self.fail_command in joined:
            return SimpleNamespace(returncode=128, stdout="", stderr="permission denied")
        if args[:4] == ["git", "diff", "--cached", "--quiet"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="")
        if args[:3] == ["git", "rev-parse", "HEAD"]:
            return SimpleNamespace(returncode=0, stdout=HEAD + "\n", stderr="")
        if args[:3] == ["git", "ls-remote", "origin"]:
            return SimpleNamespace(
                returncode=0,
                stdout=f"{HEAD}\trefs/heads/{BRANCH}\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


class ThirdArchivePublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        source = source_directory(self.root)
        self.archive_root = self.root / "durable"
        build_archive(
            source, self.archive_root, "123456", SOURCE_COMMIT,
            dt.datetime(2026, 10, 29, 3, 0, tzinfo=UTC), synthetic_only=True)
        self.status = self.root / "publish_status.json"

    def test_success_only_after_remote_ref_matches(self):
        git = FakeGit()
        result = publish_archive(
            self.repo, self.archive_root, "123456", self.status, git)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(result["long_term_archive_committed"])
        self.assertTrue(result["remote_ref_verified"])
        self.assertEqual(verify_success_status(self.status), result)
        self.assertTrue((self.repo / ARCHIVE_PATH / "123456" /
                         "iex_raw_ohlcv_evidence.json").is_file())

    def test_permission_or_push_failure_is_recorded_and_not_success(self):
        git = FakeGit("git push")
        with self.assertRaisesRegex(PublishFailed, "PUSH_RESEARCH_BRANCH"):
            publish_archive(
                self.repo, self.archive_root, "123456", self.status, git)
        status = json.loads(self.status.read_text())
        self.assertEqual(status["status"], "FAILED")
        self.assertFalse(status["long_term_archive_committed"])
        self.assertFalse(status["remote_ref_verified"])
        self.assertTrue(status["raw_ohlcv_present_in_actions_fallback"])
        self.assertIn("permission denied", status["failure_reason"])
        with self.assertRaisesRegex(ValueError, "LONG_TERM_ARCHIVE_NOT_CONFIRMED"):
            verify_success_status(self.status)

    def test_remote_readback_mismatch_is_failure(self):
        class WrongRemote(FakeGit):
            def __call__(self, args, **kwargs):
                result = super().__call__(args, **kwargs)
                if args[:3] == ["git", "ls-remote", "origin"]:
                    result.stdout = "b" * 40 + f"\trefs/heads/{BRANCH}\n"
                return result
        with self.assertRaisesRegex(PublishFailed, "VERIFY_REMOTE_REF"):
            publish_archive(
                self.repo, self.archive_root, "123456", self.status,
                WrongRemote())

    def test_existing_destination_is_never_overwritten(self):
        target = self.repo / ARCHIVE_PATH / "123456"
        target.mkdir(parents=True)
        marker = target / "keep.txt"
        marker.write_text("keep")
        with self.assertRaisesRegex(PublishFailed, "LONG_TERM_ARCHIVE_ALREADY_EXISTS"):
            publish_archive(
                self.repo, self.archive_root, "123456", self.status,
                FakeGit())
        self.assertEqual(marker.read_text(), "keep")

    def test_missing_raw_failure_status_fails_final_enforcement(self):
        status = record_failure(
            self.status, "123456", "RAW_OHLCV_MISSING", raw_present=False)
        self.assertEqual(status["status"], "FAILED")
        self.assertFalse(status["raw_ohlcv_present_in_actions_fallback"])
        with self.assertRaisesRegex(ValueError, "LONG_TERM_ARCHIVE_NOT_CONFIRMED"):
            verify_success_status(self.status)

    def test_status_file_is_create_only(self):
        record_failure(self.status, "123456", "FIRST")
        before = self.status.read_bytes()
        with self.assertRaisesRegex(FileExistsError, "PUBLISH_STATUS_ALREADY_EXISTS"):
            record_failure(self.status, "123456", "SECOND")
        self.assertEqual(self.status.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
