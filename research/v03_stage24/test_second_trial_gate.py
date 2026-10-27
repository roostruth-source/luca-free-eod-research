"""Offline-only one-time future prospective trial gate tests."""
import datetime as dt
import unittest
from second_trial_gate import validate,BRANCH,HEADER

UTC=dt.timezone.utc
WED=dt.datetime(2026,10,28,14,0,tzinfo=UTC)
MON_EST=dt.datetime(2026,11,2,15,0,tzinfo=UTC)

def request(day="2026-10-28"):
    return HEADER+"\nsession_day_ny="+day+"\nresearch_only=true\n"

def call(now=WED,text=None,event="push",ref=BRANCH,attempt="1",history=1):
    return validate(request() if text is None else text,now,event,ref,attempt,history)

class FutureGateTests(unittest.TestCase):
    def test_exact_future_weekday_morning_allowed(self):
        x=call()
        self.assertTrue(x["allowed"])
        self.assertFalse(x["real_trades_allowed"])
        self.assertTrue(x["not_nyse_holiday_verified"])
        self.assertEqual(x["validation_status"],"NOT_VALIDATED")

    def test_ny_dst_change_handled(self):
        x=call(now=MON_EST,text=request("2026-11-02"))
        self.assertEqual(x["session_day_ny"],"2026-11-02")

    def test_wrong_session_day_blocks(self):
        with self.assertRaisesRegex(ValueError,"NOT_REQUESTED_US_WEEKDAY"):
            call(text=request("2026-10-29"))

    def test_us_weekend_blocks(self):
        sat=dt.datetime(2026,10,31,14,0,tzinfo=UTC)
        with self.assertRaisesRegex(ValueError,"NOT_REQUESTED_US_WEEKDAY"):
            call(now=sat,text=request("2026-10-31"))

    def test_too_early_blocks(self):
        with self.assertRaisesRegex(ValueError,"OUTSIDE_RESEARCH_MORNING"):
            call(now=dt.datetime(2026,10,28,13,39,tzinfo=UTC))

    def test_too_late_blocks(self):
        with self.assertRaisesRegex(ValueError,"OUTSIDE_RESEARCH_MORNING"):
            call(now=dt.datetime(2026,10,28,15,21,tzinfo=UTC))

    def test_repeat_workflow_run_blocks(self):
        with self.assertRaisesRegex(ValueError,"RE_RUN_BLOCKED"):
            call(attempt="2")

    def test_modified_request_file_blocks(self):
        with self.assertRaisesRegex(ValueError,"REPEATED_REQUEST_COMMIT_BLOCKED"):
            call(history=2)

    def test_missing_history_blocks(self):
        with self.assertRaisesRegex(ValueError,"REPEATED_REQUEST_COMMIT_BLOCKED"):
            call(history=0)

    def test_wrong_branch_blocks(self):
        with self.assertRaisesRegex(ValueError,"WRONG_TRIGGER_OR_BRANCH"):
            call(ref="refs/heads/main")

    def test_manual_dispatch_blocks(self):
        with self.assertRaisesRegex(ValueError,"WRONG_TRIGGER_OR_BRANCH"):
            call(event="workflow_dispatch")

    def test_wrong_format_blocks(self):
        with self.assertRaisesRegex(ValueError,"BAD_REQUEST_FORMAT"):
            call(text=request()+"allow_orders=true\n")

    def test_request_cannot_enable_trades(self):
        with self.assertRaisesRegex(ValueError,"BAD_REQUEST_FORMAT"):
            call(text=HEADER+"\nsession_day_ny=2026-10-28\nresearch_only=false\n")

    def test_invalid_date_blocks(self):
        with self.assertRaisesRegex(ValueError,"BAD_SESSION_DAY"):
            call(text=request("2026-13-42"))

    def test_naive_clock_blocks(self):
        with self.assertRaisesRegex(ValueError,"AWARE_NOW_REQUIRED"):
            call(now=dt.datetime(2026,10,28,14,0))

if __name__=="__main__":
    unittest.main()
