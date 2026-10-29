"""Static no-execution contract for the dormant third-only workflow."""
import re
import unittest
from pathlib import Path

from third_trial_gate import REQUEST_PATH, BASELINE_COMMIT
from third_trial_dry_run import EXPECTED_FIND_PATTERNS_SHA256


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/luca-v03-third-prospective-once.yml"


class ThirdWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = WORKFLOW.read_text(encoding="utf8")

    def test_only_new_absent_third_request_can_trigger(self):
        self.assertIn("paths:\n      - '" + REQUEST_PATH + "'", self.text)
        self.assertNotIn("workflow_dispatch", self.text)
        self.assertNotRegex(self.text, r"(?m)^\s*schedule:")
        self.assertFalse((ROOT / REQUEST_PATH).exists())

    def test_exact_research_branch_and_attempt_one(self):
        self.assertIn("research/v03-stage24-evidence", self.text)
        self.assertIn("github.run_attempt == 1", self.text)
        self.assertIn("cancel-in-progress: false", self.text)

    def test_old_first_second_requests_and_workflows_not_reused(self):
        self.assertNotIn("second_prospective_request", self.text)
        self.assertNotIn("second_followup_request", self.text)
        self.assertNotIn("luca_v03_second_forward", self.text)
        self.assertNotIn("followup_live_request", self.text)

    def test_gate_tests_and_synthetic_replay_precede_market_secrets(self):
        gate = self.text.index("third_trial_gate.py")
        tests = self.text.index("unittest discover")
        dry = self.text.index("third_trial_dry_run.py")
        market = self.text.index("ALPACA_KEY")
        self.assertLess(gate, tests)
        self.assertLess(tests, dry)
        self.assertLess(dry, market)
        self.assertIn("LUCA_V03_THIRD_APPROVAL_SHA256", self.text)

    def test_raw_replay_and_long_term_archive_are_mandatory_paths(self):
        self.assertIn("iex_raw_ohlcv_evidence.json", self.text)
        self.assertIn("iex_raw_evidence.py", self.text)
        self.assertIn("replay_result.json", self.text)
        self.assertIn("third_durable_archive.py", self.text)
        self.assertIn("third_archives/$RUN_ID", self.text)
        self.assertIn("git push origin HEAD:research/v03-stage24-evidence", self.text)
        self.assertIn("retention-days: 7", self.text)

    def test_no_production_site_orders_or_api_radar(self):
        lowered = self.text.lower()
        self.assertNotIn("/api/radar", lowered)
        self.assertNotIn("/orders", lowered)
        self.assertNotIn("deploy", lowered)
        self.assertNotIn("index.html", lowered)
        self.assertNotIn("latest.html", lowered)

    def test_write_permission_exists_only_for_durable_evidence_commit(self):
        self.assertIn("permissions:\n  contents: write", self.text)
        self.assertEqual(self.text.count("git push"), 1)
        self.assertIn("test ! -e \"$target\"", self.text)
        self.assertIn("git add -- \"$target\"", self.text)

    def test_baseline_formula_and_request_constants_are_fixed(self):
        self.assertEqual(BASELINE_COMMIT, "6d8ef32fd0de22ed61675cbbccadefed0fe26945")
        self.assertEqual(EXPECTED_FIND_PATTERNS_SHA256,
                         "8b51d1b83ccd7791a39b84e69b8df17d04a867587aa23eb325765208e958d3e6")


if __name__ == "__main__":
    unittest.main()
