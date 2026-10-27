"""Synthetic-only GitHub run/artifact identity regression tests."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from second_trial_artifact_bridge import (
    verify_second_run,build_verified_comparison,SECOND_WORKFLOW,BRANCH,main)
from test_two_session_iex_comparison import FIRST,SECOND_ID,fixture

META={"databaseId":SECOND_ID,"name":SECOND_WORKFLOW,"headBranch":BRANCH,
      "event":"push","status":"completed","conclusion":"success"}
ART={"name":f"luca-v03-second-prospective-{SECOND_ID}","expired":False,
     "workflow_run":{"id":SECOND_ID}}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.meta=copy.deepcopy(META)
        self.art=copy.deepcopy(ART)
        self.first=copy.deepcopy(FIRST)
        self.f,self.r,self.p=fixture()

    def build(self):
        return build_verified_comparison(self.first,self.meta,self.f,self.r,self.p,self.art)

    def test_authentic_matching_source_and_artifact(self):
        x=self.build()
        self.assertEqual(x["second_source_run_id"],SECOND_ID)
        self.assertTrue(x["second_source_workflow_verified"])
        self.assertTrue(x["second_artifact_metadata_verified"])
        self.assertFalse(x["real_trades_allowed"])
        self.assertFalse(x["not_a_prediction_win_rate"] is False)

    def test_wrong_workflow_blocks(self):
        self.meta["name"]="LUCA V03 forward IEX once on isolated request file"
        with self.assertRaisesRegex(ValueError,"WRONG_SECOND_WORKFLOW"):
            self.build()

    def test_wrong_branch_blocks(self):
        self.meta["headBranch"]="main"
        with self.assertRaisesRegex(ValueError,"WRONG_SECOND_BRANCH_OR_EVENT"):
            self.build()

    def test_manual_dispatch_blocks(self):
        self.meta["event"]="workflow_dispatch"
        with self.assertRaisesRegex(ValueError,"WRONG_SECOND_BRANCH_OR_EVENT"):
            self.build()

    def test_incomplete_run_blocks(self):
        self.meta["status"]="in_progress"
        with self.assertRaisesRegex(ValueError,"SECOND_RUN_NOT_SUCCESSFUL"):
            self.build()

    def test_failed_run_blocks(self):
        self.meta["conclusion"]="failure"
        with self.assertRaisesRegex(ValueError,"SECOND_RUN_NOT_SUCCESSFUL"):
            self.build()

    def test_first_source_id_cannot_be_second(self):
        self.meta["databaseId"]=40517830351
        with self.assertRaisesRegex(ValueError,"INVALID_SECOND_RUN_ID"):
            self.build()

    def test_wrong_artifact_name_blocks(self):
        self.art["name"]="luca-v03-second-prospective-99999999"
        with self.assertRaisesRegex(ValueError,"WRONG_SECOND_ARTIFACT_NAME"):
            self.build()

    def test_artifact_from_other_run_blocks(self):
        self.art["workflow_run"]["id"]=99999999
        with self.assertRaisesRegex(ValueError,"WRONG_SECOND_ARTIFACT_RUN"):
            self.build()

    def test_expired_artifact_blocks(self):
        self.art["expired"]=True
        with self.assertRaisesRegex(ValueError,"EXPIRED_SECOND_ARTIFACT"):
            self.build()

    def test_missing_timestamp_evidence_blocks(self):
        self.p["rows"][0]["missing_iex_bar_start_utc"]=[]
        with self.assertRaisesRegex(ValueError,"INCONSISTENT_TIMESTAMP_GRID"):
            self.build()

    def test_no_artifact_metadata_marked_unverified(self):
        x=build_verified_comparison(self.first,self.meta,self.f,self.r,self.p)
        self.assertFalse(x["second_artifact_metadata_verified"])

    def test_immutable_output_requires_all_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse((Path(d)/"two_session_comparison.json").exists())
            self.assertEqual(verify_second_run(self.meta,self.art),SECOND_ID)

if __name__=="__main__":
    unittest.main()
