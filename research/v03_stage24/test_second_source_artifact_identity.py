"""Offline GitHub second source artifact listing integrity tests."""
import copy
import unittest
from second_source_artifact_identity import select_source_artifact
from test_second_trial_artifact_bridge import META,ART,SECOND_ID

class SourceArtifactIdentityTests(unittest.TestCase):
    def setUp(self):
        self.meta=copy.deepcopy(META)
        self.artifact=copy.deepcopy(ART)
        self.artifact["id"]=12799999999
        self.artifact["size_in_bytes"]=1200
        self.listing={"artifacts":[self.artifact]}

    def test_valid_real_shape(self):
        self.assertEqual(select_source_artifact(self.meta,self.listing)["id"],12799999999)

    def test_missing_artifact(self):
        self.listing["artifacts"]=[]
        with self.assertRaisesRegex(ValueError,"MISSING_OR_DUPLICATE_SOURCE_ARTIFACT"):
            select_source_artifact(self.meta,self.listing)

    def test_duplicate_artifact(self):
        self.listing["artifacts"].append(copy.deepcopy(self.artifact))
        with self.assertRaisesRegex(ValueError,"MISSING_OR_DUPLICATE_SOURCE_ARTIFACT"):
            select_source_artifact(self.meta,self.listing)

    def test_wrong_artifact_run(self):
        self.artifact["workflow_run"]["id"]=SECOND_ID+1
        with self.assertRaisesRegex(ValueError,"WRONG_SECOND_ARTIFACT_RUN"):
            select_source_artifact(self.meta,self.listing)

    def test_expired_artifact(self):
        self.artifact["expired"]=True
        with self.assertRaisesRegex(ValueError,"EXPIRED_SECOND_ARTIFACT"):
            select_source_artifact(self.meta,self.listing)

    def test_zero_size_artifact(self):
        self.artifact["size_in_bytes"]=0
        with self.assertRaisesRegex(ValueError,"EMPTY_OR_INVALID_SOURCE_ARTIFACT"):
            select_source_artifact(self.meta,self.listing)

    def test_wrong_workflow(self):
        self.meta["name"]="other"
        with self.assertRaisesRegex(ValueError,"WRONG_SECOND_WORKFLOW"):
            select_source_artifact(self.meta,self.listing)

    def test_malformed_listing(self):
        with self.assertRaisesRegex(ValueError,"INVALID_GITHUB_ARTIFACT_LIST"):
            select_source_artifact(self.meta,{"artifacts":None})

if __name__=="__main__":
    unittest.main()
