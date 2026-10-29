"""Offline tests for the third-trial two-key approval gate."""
import datetime as dt
import unittest

from third_trial_gate import (
    approval_sha256, validate, BASELINE_COMMIT, BRANCH, HEADER,
)


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 29, 14, 0, tzinfo=UTC)
NONCE = "a" * 64


def request(day="2026-10-29", expires=None, nonce=NONCE,
            approved_commit=BASELINE_COMMIT):
    expires = expires or NOW + dt.timedelta(minutes=8)
    return (f"{HEADER}\n"
            f"session_day_ny={day}\n"
            f"expires_at_utc={expires.isoformat()}\n"
            f"approval_nonce={nonce}\n"
            f"baseline_commit={BASELINE_COMMIT}\n"
            f"approved_code_commit={approved_commit}\n"
            "research_only=true\n"
            "orders_allowed=false\n")


def call(text=None, now=NOW, event="push", ref=BRANCH, attempt="1",
         history=1, commit_at=None, secret=None, archives=0):
    return validate(
        request() if text is None else text, now, event, ref, attempt, history,
        commit_at or now - dt.timedelta(minutes=2),
        secret or approval_sha256(NONCE), archives, BASELINE_COMMIT)


class ThirdTrialGateTests(unittest.TestCase):
    def test_fresh_two_key_user_approval_allows_research_only(self):
        result = call()
        self.assertTrue(result["allowed"])
        self.assertTrue(result["two_key_user_approval_verified"])
        self.assertEqual(result["all_grades"], "D")
        self.assertFalse(result["nyse_holiday_calendar_verified"])
        self.assertFalse(result["orders_allowed"])
        self.assertFalse(result["real_trades_allowed"])

    def test_missing_or_wrong_secret_blocks(self):
        with self.assertRaisesRegex(ValueError, "USER_APPROVAL_SECRET_MISMATCH"):
            call(secret="0" * 64)

    def test_expired_approval_blocks(self):
        with self.assertRaisesRegex(ValueError, "EXPIRED_OR_OVERSIZED_APPROVAL_WINDOW"):
            call(text=request(expires=NOW))

    def test_approval_window_over_twenty_minutes_blocks(self):
        with self.assertRaisesRegex(ValueError, "EXPIRED_OR_OVERSIZED_APPROVAL_WINDOW"):
            call(text=request(expires=NOW + dt.timedelta(minutes=21)))

    def test_stale_request_commit_blocks(self):
        with self.assertRaisesRegex(ValueError, "STALE_OR_FUTURE_REQUEST_COMMIT"):
            call(commit_at=NOW - dt.timedelta(minutes=11))

    def test_future_request_commit_blocks(self):
        with self.assertRaisesRegex(ValueError, "STALE_OR_FUTURE_REQUEST_COMMIT"):
            call(commit_at=NOW + dt.timedelta(seconds=1))

    def test_rerun_blocks(self):
        with self.assertRaisesRegex(ValueError, "RE_RUN_BLOCKED"):
            call(attempt="2")

    def test_modified_or_second_request_commit_blocks(self):
        with self.assertRaisesRegex(ValueError, "REPEATED_REQUEST_COMMIT_BLOCKED"):
            call(history=2)

    def test_existing_third_archive_blocks(self):
        with self.assertRaisesRegex(ValueError, "THIRD_ARCHIVE_ALREADY_EXISTS"):
            call(archives=1)

    def test_main_or_manual_dispatch_blocks(self):
        with self.assertRaisesRegex(ValueError, "WRONG_TRIGGER_OR_BRANCH"):
            call(ref="refs/heads/main")
        with self.assertRaisesRegex(ValueError, "WRONG_TRIGGER_OR_BRANCH"):
            call(event="workflow_dispatch")

    def test_wrong_day_and_weekend_block(self):
        with self.assertRaisesRegex(ValueError, "NOT_REQUESTED_US_WEEKDAY"):
            call(text=request(day="2026-10-30"))
        saturday = dt.datetime(2026, 10, 31, 14, 0, tzinfo=UTC)
        with self.assertRaisesRegex(ValueError, "NOT_REQUESTED_US_WEEKDAY"):
            call(now=saturday, text=request(day="2026-10-31",
                 expires=saturday + dt.timedelta(minutes=8)),
                 commit_at=saturday - dt.timedelta(minutes=2))

    def test_outside_morning_blocks(self):
        early = dt.datetime(2026, 10, 29, 13, 39, tzinfo=UTC)
        with self.assertRaisesRegex(ValueError, "OUTSIDE_RESEARCH_MORNING"):
            call(now=early, text=request(expires=early + dt.timedelta(minutes=8)),
                 commit_at=early - dt.timedelta(minutes=2))

    def test_unsafe_request_flags_block(self):
        with self.assertRaisesRegex(ValueError, "UNSAFE_REQUEST"):
            call(text=request().replace("orders_allowed=false", "orders_allowed=true"))
        with self.assertRaisesRegex(ValueError, "UNSAFE_REQUEST"):
            call(text=request().replace("research_only=true", "research_only=false"))

    def test_wrong_baseline_blocks(self):
        with self.assertRaisesRegex(ValueError, "UNSAFE_REQUEST"):
            call(text=request().replace(BASELINE_COMMIT, "0" * 40))

    def test_approved_code_must_equal_request_parent(self):
        with self.assertRaisesRegex(ValueError, "APPROVED_CODE_COMMIT_MISMATCH"):
            call(text=request(approved_commit="2" * 40))

    def test_bad_nonce_and_noncanonical_expiry_block(self):
        with self.assertRaisesRegex(ValueError, "BAD_APPROVAL_NONCE"):
            call(text=request(nonce="short"))
        with self.assertRaisesRegex(ValueError, "NONCANONICAL_REQUEST_TIME"):
            call(text=request().replace("+00:00", "Z"))

    def test_naive_clocks_block(self):
        with self.assertRaisesRegex(ValueError, "AWARE_NOW_REQUIRED"):
            call(now=NOW.replace(tzinfo=None))
        with self.assertRaisesRegex(ValueError, "AWARE_REQUEST_COMMIT_TIME_REQUIRED"):
            call(commit_at=NOW.replace(tzinfo=None))


if __name__ == "__main__":
    unittest.main()
