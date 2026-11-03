"""Offline authorization regression for independent recovery ref; no market APIs."""
import datetime as dt
import unittest
from third_trial_gate import BASELINE_COMMIT, HEADER, approval_sha256, validate
from recovery_observation_gate import REF

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 11, 4, 15, 0, tzinfo=UTC)
PARENT = "a" * 40
NONCE = "b" * 64

def request():
    return ("\n".join([
        HEADER,
        "session_day_ny=2026-11-04",
        "expires_at_utc=2026-11-04T15:10:00+00:00",
        "approval_nonce=" + NONCE,
        "baseline_commit=" + BASELINE_COMMIT,
        "approved_code_commit=" + PARENT,
        "research_only=true",
        "orders_allowed=false",
    ]) + "\n")

def check(**kwargs):
    args = dict(text=request(), now=NOW, event_name="push", ref=REF,
                run_attempt="1", request_history_commits=1,
                request_commit_at=NOW - dt.timedelta(minutes=1),
                approval_secret_hash=approval_sha256(NONCE),
                existing_archive_count=0, request_parent_commit=PARENT,
                expected_ref=REF)
    args.update(kwargs)
    return validate(**args)

class RecoveryAuthorizationTests(unittest.TestCase):
    def test_valid_offline_authorization(self):
        result = check()
        self.assertTrue(result["allowed"])
        self.assertFalse(result["orders_allowed"])
        self.assertFalse(result["nyse_holiday_calendar_verified"])

    def test_wrong_secret_fails(self):
        with self.assertRaisesRegex(ValueError, "USER_APPROVAL_SECRET_MISMATCH"):
            check(approval_secret_hash="0" * 64)

    def test_rerun_fails(self):
        with self.assertRaisesRegex(ValueError, "RE_RUN_BLOCKED"):
            check(run_attempt="2")

    def test_wrong_branch_fails(self):
        with self.assertRaisesRegex(ValueError, "WRONG_TRIGGER_OR_BRANCH"):
            check(ref="refs/heads/main")

    def test_existing_archive_fails(self):
        with self.assertRaisesRegex(ValueError, "THIRD_ARCHIVE_ALREADY_EXISTS"):
            check(existing_archive_count=1)

    def test_old_default_branch_unchanged(self):
        with self.assertRaisesRegex(ValueError, "WRONG_TRIGGER_OR_BRANCH"):
            check(expected_ref="refs/heads/research/v03-stage24-evidence")

    def test_expired_approval_fails(self):
        with self.assertRaisesRegex(ValueError, "EXPIRED_OR_OVERSIZED_APPROVAL_WINDOW"):
            check(now=NOW + dt.timedelta(minutes=11))

    def test_future_request_commit_fails(self):
        with self.assertRaisesRegex(ValueError, "STALE_OR_FUTURE_REQUEST_COMMIT"):
            check(request_commit_at=NOW + dt.timedelta(seconds=1))

    def test_stale_request_commit_fails(self):
        with self.assertRaisesRegex(ValueError, "STALE_OR_FUTURE_REQUEST_COMMIT"):
            check(request_commit_at=NOW - dt.timedelta(minutes=11))

    def test_repeated_request_history_fails(self):
        with self.assertRaisesRegex(ValueError, "REPEATED_REQUEST_COMMIT_BLOCKED"):
            check(request_history_commits=2)

    def test_wrong_approved_parent_fails(self):
        with self.assertRaisesRegex(ValueError, "APPROVED_CODE_COMMIT_MISMATCH"):
            check(request_parent_commit="c" * 40)

    def test_order_permission_fails(self):
        with self.assertRaisesRegex(ValueError, "UNSAFE_REQUEST"):
            check(text=request().replace("orders_allowed=false", "orders_allowed=true"))

if __name__ == "__main__":
    unittest.main()
