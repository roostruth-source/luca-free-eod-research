"""Offline-only second prospective 60min followup gate tests."""
import copy
import datetime as dt
import unittest
from second_followup_gate import gate,BRANCH
from test_second_trial_artifact_bridge import META,SECOND_ID
from test_two_session_iex_comparison import fixture

UTC=dt.timezone.utc

class SecondFollowupGateTests(unittest.TestCase):
    def setUp(self):
        self.f,self.r,self.p=fixture()
        self.meta=copy.deepcopy(META)
        self.now=dt.datetime.fromisoformat(self.f["selected_at_utc"])+dt.timedelta(minutes=100)

    def call(self,**kw):
        args=dict(run_id_text=str(SECOND_ID)+"\n",meta=self.meta,
                  frozen=self.f,review=self.r,provenance=self.p,
                  now=self.now,event="push",ref=BRANCH,attempt="1",history=1)
        args.update(kw)
        return gate(**args)

    def test_valid_mature_second_source_research_only(self):
        x=self.call()
        self.assertEqual(x["verified_second_run_id"],SECOND_ID)
        self.assertTrue(x["ready_for_fixed_clock_60min"])
        self.assertFalse(x["real_trades_allowed"])
        self.assertEqual(x["validation_status"],"NOT_VALIDATED")

    def test_exact_82_minute_boundary(self):
        at=dt.datetime.fromisoformat(self.f["selected_at_utc"])+dt.timedelta(minutes=82)
        x=self.call(now=at)
        self.assertTrue(x["ready_for_fixed_clock_60min"])

    def test_source_not_yet_mature(self):
        t=dt.datetime.fromisoformat(self.f["selected_at_utc"])+dt.timedelta(minutes=80)
        with self.assertRaisesRegex(ValueError,"FOLLOWUP_NOT_YET_MATURE"):
            self.call(now=t)

    def test_source_too_old(self):
        with self.assertRaisesRegex(ValueError,"FOLLOWUP_TOO_LATE"):
            self.call(now=self.now+dt.timedelta(hours=9))

    def test_wrong_source_run_id(self):
        with self.assertRaisesRegex(ValueError,"SECOND_SOURCE_RUN_ID_MISMATCH"):
            self.call(run_id_text="40699999999")

    def test_first_source_run_blocked(self):
        with self.assertRaisesRegex(ValueError,"SECOND_SOURCE_RUN_ID_MISMATCH"):
            self.call(run_id_text="40517830351")

    def test_source_run_not_successful(self):
        self.meta["conclusion"]="failure"
        with self.assertRaisesRegex(ValueError,"SECOND_RUN_NOT_SUCCESSFUL"):
            self.call()

    def test_wrong_second_session_day(self):
        self.f["session_day_ny"]="2026-10-27"
        with self.assertRaises(ValueError):
            self.call()

    def test_provenance_hash_mismatch(self):
        self.p["frozen_t0_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"MISSING_SECOND_IEX_PROVENANCE"):
            self.call()

    def test_provenance_missing_http(self):
        self.p["api_fetch"]["all_pages_successful"]=None
        with self.assertRaisesRegex(ValueError,"UNVERIFIED_IEX_HTTP"):
            self.call()

    def test_wrong_review_time_in_provenance(self):
        self.p["reviewed_at_utc"]="2026-10-28T14:55:00+00:00"
        with self.assertRaisesRegex(ValueError,"SECOND_PROVENANCE_ORIGIN_MISMATCH"):
            self.call()

    def test_changed_bar_counts_block(self):
        self.p["rows"][0]["observed_minutes"]=0
        with self.assertRaisesRegex(ValueError,"SECOND_PROVENANCE_COUNTS_MISMATCH"):
            self.call()

    def test_second_timestamp_grid_must_be_real_and_complete(self):
        self.p["rows"][0]["missing_iex_bar_start_utc"]=[]
        with self.assertRaisesRegex(ValueError,"INCONSISTENT_TIMESTAMP_GRID"):
            self.call()

    def test_second_timestamp_duplicate_rejected(self):
        self.p["rows"][0]["observed_bar_start_utc"][1]=self.p["rows"][0]["observed_bar_start_utc"][0]
        with self.assertRaisesRegex(ValueError,"INCONSISTENT_TIMESTAMP_GRID"):
            self.call()

    def test_second_http_final_page_must_be_recorded(self):
        self.p["api_fetch"]["final_page_token_absent"]=False
        with self.assertRaisesRegex(ValueError,"SECOND_HTTP_INCOMPLETE"):
            self.call()

    def test_second_http_must_be_get_only(self):
        self.p["api_fetch"]["get_only_confirmed"]=False
        with self.assertRaisesRegex(ValueError,"SECOND_HTTP_INCOMPLETE"):
            self.call()

    def test_wrong_expected_minute_grid_rejected(self):
        self.p["expected_minutes_per_symbol"]=14
        with self.assertRaisesRegex(ValueError,"SECOND_WINDOW_MISMATCH"):
            self.call()

    def test_wrong_missing_bar_cause_rejected(self):
        self.p["rows"][0]["missing_cause"]="PROVEN_NO_TRADES"
        with self.assertRaisesRegex(ValueError,"UNJUSTIFIED_GAP_CAUSE"):
            self.call()

    def test_valid_gate_records_verified_grid(self):
        x=self.call()
        self.assertTrue(x["iex_timestamp_grid_verified"])
        self.assertTrue(x["iex_http_pages_verified"])
        self.assertEqual(x["observed_iex_bars"],9)
        self.assertEqual(x["expected_iex_bars"],15)
        self.assertTrue(x["first_real_archive_verified"])

    def test_rerun_attempt_blocked(self):
        with self.assertRaisesRegex(ValueError,"WRONG_FOLLOWUP_TRIGGER"):
            self.call(attempt="2")

    def test_second_request_history_must_be_unique(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_FOLLOWUP_REQUEST"):
            self.call(history=2)

    def test_wrong_branch_blocks(self):
        with self.assertRaisesRegex(ValueError,"WRONG_FOLLOWUP_TRIGGER"):
            self.call(ref="refs/heads/main")

    def test_bad_request_blocks(self):
        with self.assertRaisesRegex(ValueError,"INVALID_FOLLOWUP_REQUEST"):
            self.call(run_id_text="0000000001")

if __name__=="__main__":
    unittest.main()
