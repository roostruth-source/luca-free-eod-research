"""Offline regression for durable recovery workflow run-history guard."""
import io
import json
import os
import unittest
from unittest.mock import patch
from recovery_observation_gate import verify_no_prior_workflow_run

ENV = {
    "GITHUB_TOKEN": "synthetic-test-token",
    "GITHUB_REPOSITORY": "roostruth-source/luca-free-eod-research",
    "GITHUB_RUN_ID": "123",
    "GITHUB_SHA": "a" * 40,
}

def opener(payload):
    def open_request(request, timeout=15):
        assert timeout == 15
        assert "head_sha=" + "a" * 40 in request.full_url
        return io.BytesIO(json.dumps(payload).encode())
    return open_request

class WorkflowHistoryTests(unittest.TestCase):
    def test_first_run_allowed(self):
        with patch.dict(os.environ, ENV):
            verify_no_prior_workflow_run(opener({"total_count": 1, "workflow_runs": [{"id": 123}]}))

    def test_prior_run_blocked_even_if_failed(self):
        with patch.dict(os.environ, ENV):
            with self.assertRaisesRegex(ValueError, "PREVIOUS_OBSERVATION_RUN_BLOCKED"):
                verify_no_prior_workflow_run(opener({"total_count": 2, "workflow_runs": [
                    {"id": 123}, {"id": 122, "conclusion": "failure"}]}))

    def test_missing_credentials_fail_closed(self):
        with patch.dict(os.environ, {**ENV, "GITHUB_TOKEN": ""}):
            with self.assertRaisesRegex(ValueError, "RUN_HISTORY_CHECK_UNAVAILABLE"):
                verify_no_prior_workflow_run(opener({"total_count": 1, "workflow_runs": [{"id": 123}]}))

    def test_truncated_history_fails_closed(self):
        with patch.dict(os.environ, ENV):
            with self.assertRaisesRegex(ValueError, "RUN_HISTORY_INCOMPLETE"):
                verify_no_prior_workflow_run(opener({"total_count": 100, "workflow_runs": [{"id": 123}]}))

    def test_current_run_not_visible_fails_closed(self):
        with patch.dict(os.environ, ENV):
            with self.assertRaisesRegex(ValueError, "PREVIOUS_OBSERVATION_RUN_BLOCKED"):
                verify_no_prior_workflow_run(opener({"total_count": 0, "workflow_runs": []}))

if __name__ == "__main__":
    unittest.main()
