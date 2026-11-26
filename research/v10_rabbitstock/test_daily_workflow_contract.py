import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DAILY = ROOT / ".github/workflows/luca-v10-daily-observation.yml"
OFFLINE = ROOT / ".github/workflows/luca-v10-research-build-ci.yml"


class DailyWorkflowContractTests(unittest.TestCase):
    def test_daily_workflow_is_manual_research_only_and_read_only(self):
        text = DAILY.read_text()
        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("schedule:", text)
        self.assertNotIn("\n  push:", text)
        self.assertNotIn("\n  pull_request:", text)
        self.assertIn("contents: read", text)
        self.assertIn("actions: read", text)
        self.assertNotIn("contents: write", text)
        self.assertIn("RUN_V10_WATCH_ONLY", text)
        self.assertIn("research/v10-rabbitstock-eval", text)
        self.assertNotIn("/v2/orders", text)

    def test_guard_and_offline_tests_precede_market_collection(self):
        text = DAILY.read_text()
        self.assertLess(text.index("python -m unittest discover -v"),
                        text.index("run_live_research.py"))
        self.assertLess(text.index("daily_observation_guard.py"),
                        text.index("run_live_research.py"))
        self.assertIn("--max-new-events 12", text)
        self.assertIn("retention-days: 90", text)
        self.assertIn("luca-v10-research-build-ci.yml", text)
        self.assertIn("NO_PREVIOUS_SUCCESSFUL_RUN", text)
        self.assertIn("archive_bundle.py build", text)
        self.assertIn("archive_bundle.py verify", text)
        self.assertIn("luca_v10_archive_bundle.zip", text)
        self.assertLess(text.index("Verify final safety flags"),
                        text.index("archive_bundle.py build"))

    def test_push_and_pr_ci_have_no_live_market_or_secret_steps(self):
        text = OFFLINE.read_text()
        self.assertNotIn("workflow_dispatch:", text)
        self.assertNotIn("run_live_research.py", text)
        self.assertNotIn("ALPACA_KEY", text)
        self.assertNotIn("ALPACA_SECRET", text)
        self.assertNotIn("SEC_USER_AGENT", text)
        self.assertNotIn("prospective_outcomes.py", text)


if __name__ == "__main__":
    unittest.main()
