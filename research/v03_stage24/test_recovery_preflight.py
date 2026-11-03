"""Regression checks for the read-only LUCA recovery preflight."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from recovery_preflight import REQUEST, inspect

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 3, 15, 0, tzinfo=UTC)
OLD_REQUEST = """LUCA_V03_THIRD_PROSPECTIVE_ONCE
session_day_ny=2026-11-02
expires_at_utc=2026-11-02T16:24:00+00:00
approval_nonce=d5eb0d54c2b1d074a26a87bdcd781e829f2fb6f49c44f7918c08b77cb40e7c47
baseline_commit=6d8ef32fd0de22ed61675cbbccadefed0fe26945
approved_code_commit=98141cd1d9971c091cbbb77a80c9f2a1616051db
research_only=true
orders_allowed=false
"""

class RecoveryPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_request(self, content=OLD_REQUEST):
        path = self.root / REQUEST
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_missing_request_fails_closed(self):
        result = inspect(self.root, NOW)
        self.assertFalse(result["request_exists"])
        self.assertFalse(result["safe_to_reuse_request"])
        self.assertFalse(result["orders_allowed"])

    def test_expired_wrong_nonce_fails_closed(self):
        self.write_request()
        result = inspect(self.root, NOW)
        self.assertTrue(result["request_expired"])
        self.assertFalse(result["request_approval_hash_matches_expected"])
        self.assertFalse(result["safe_to_reuse_request"])
        self.assertEqual(result["validation_status"], "NOT_VALIDATED")

    def test_malformed_request_fails_closed(self):
        self.write_request("BAD HEADER\\n")
        result = inspect(self.root, NOW)
        self.assertEqual(result["reason"], "MALFORMED_REQUEST")
        self.assertFalse(result["safe_to_reuse_request"])

    def test_naive_datetime_rejected(self):
        with self.assertRaises(ValueError):
            inspect(self.root, dt.datetime(2026, 11, 3))

    def test_no_files_mutated(self):
        self.write_request()
        path = self.root / REQUEST
        before = path.read_bytes()
        inspect(self.root, NOW)
        self.assertEqual(path.read_bytes(), before)

if __name__ == "__main__":
    unittest.main()
