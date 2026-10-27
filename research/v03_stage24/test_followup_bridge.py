"""Offline source run/artifact bridge tests; no network or orders."""
import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from followup_bridge import read_run_id,validate_github_run,verify_downloaded_files,RUN_WORKFLOW,RESEARCH_BRANCH
from prospective_iex_research import digest_frozen,next_bar_start

T0=dt.datetime(2026,10,27,13,45,11,tzinfo=dt.timezone.utc)
REVIEWED=T0+dt.timedelta(minutes=17)
FROZEN={"schema":"LUCA_V03_PROSPECTIVE_FREEZE_V1",
        "selected_at_utc":T0.isoformat(),"session_day_ny":"2026-10-27",
        "candidates":["GPUS"],"candidate_count":1,"selection_cap":12,
        "validation_status":"NOT_VALIDATED","real_trades_allowed":False}
FROZEN["sha256"]=digest_frozen(FROZEN)
REVIEW={"schema":"LUCA_V03_PROSPECTIVE_IEX_REVIEW_V1",
        "selected_at_utc":T0.isoformat(),
        "first_allowed_bar_start_utc":next_bar_start(T0).isoformat(),
        "last_allowed_bar_start_utc":(REVIEWED-dt.timedelta(minutes=2)).replace(second=0,microsecond=0).isoformat(),
        "reviewed_at_utc":REVIEWED.isoformat(),"feed":"IEX_SINGLE_EXCHANGE_NOT_SIP",
        "candidate_selection_before_bars":True,
        "results":[{"symbol":"GPUS","grade":"D","pattern_count":0,
                    "first_pattern":None,"buy_allowed":False}],
        "prediction_accuracy_verified":False,"validation_status":"NOT_VALIDATED",
        "real_trades_allowed":False}
METADATA={"databaseId":123456789,"name":RUN_WORKFLOW,"headBranch":RESEARCH_BRANCH,
          "event":"push","status":"completed","conclusion":"success"}

class BridgeTests(unittest.TestCase):
    def test_run_id(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"run.txt"
            p.write_text("123456789\n")
            self.assertEqual(read_run_id(p),123456789)
            p.write_text("123456789; curl bad")
            with self.assertRaisesRegex(ValueError,"INVALID_RUN_ID"):
                read_run_id(p)

    def test_success_provenance(self):
        x=validate_github_run(METADATA,123456789)
        self.assertTrue(x["research_only"])
        self.assertFalse(x["real_trades_allowed"])

    def test_wrong_run_rejected(self):
        with self.assertRaisesRegex(ValueError,"WRONG_RUN_ID"):
            validate_github_run(METADATA,123456788)

    def test_failed_run_rejected(self):
        v=dict(METADATA,conclusion="failure")
        with self.assertRaisesRegex(ValueError,"PROSPECTIVE_RUN_NOT_SUCCESSFUL"):
            validate_github_run(v,123456789)

    def test_other_branch_rejected(self):
        v=dict(METADATA,headBranch="main")
        with self.assertRaisesRegex(ValueError,"WRONG_BRANCH_OR_EVENT"):
            validate_github_run(v,123456789)

    def test_wrong_name_rejected(self):
        v=dict(METADATA,name="LUCA daily production scanner")
        with self.assertRaisesRegex(ValueError,"WRONG_WORKFLOW"):
            validate_github_run(v,123456789)

    def test_missing_artifacts_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,"MISSING_OR_INCOMPLETE_PROSPECTIVE_ARTIFACT"):
                verify_downloaded_files(d)

    def test_real_freeze_and_review_pair(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,"frozen_t0.json").write_text(json.dumps(FROZEN))
            Path(d,"forward_review.json").write_text(json.dumps(REVIEW))
            a=verify_downloaded_files(d)
            self.assertTrue(a["hash_verified"])
            self.assertEqual(a["forward_signal_symbols"],0)
            self.assertFalse(a["real_trades_allowed"])

    def test_mixed_sources_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,"frozen_t0.json").write_text(json.dumps(FROZEN))
            x=copy.deepcopy(REVIEW);x["selected_at_utc"]=(T0+dt.timedelta(minutes=1)).isoformat()
            Path(d,"forward_review.json").write_text(json.dumps(x))
            with self.assertRaisesRegex(ValueError,"T0_REVIEW_MISMATCH"):
                verify_downloaded_files(d)

    def test_forced_buy_approval_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,"frozen_t0.json").write_text(json.dumps(FROZEN))
            x=copy.deepcopy(REVIEW);x["results"][0]["grade"]="A"
            Path(d,"forward_review.json").write_text(json.dumps(x))
            with self.assertRaisesRegex(ValueError,"UNSAFE_RESEARCH_GRADE"):
                verify_downloaded_files(d)

if __name__=="__main__":
    unittest.main()
