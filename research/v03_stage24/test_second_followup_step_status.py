"""Offline status and workflow fail-after-archive contract tests."""
import unittest
from pathlib import Path
from second_followup_step_status import build_status

WORKFLOW=Path(__file__).resolve().parents[2]/".github/workflows/luca-v03-second-followup-once.yml"

class FollowupPartialArchiveTests(unittest.TestCase):
    def test_complete(self):
        x=build_status("success","success","success")
        self.assertTrue(x["all_essential_steps_succeeded"])
        self.assertFalse(x["real_trades_allowed"])
        self.assertFalse(x["actual_fill_or_profit_verified"])

    def test_signal_api_failure(self):
        x=build_status("failure","success","success")
        self.assertFalse(x["all_essential_steps_succeeded"])
        self.assertEqual(x["quality"],"INCOMPLETE_EVIDENCE")

    def test_reference_api_failure(self):
        self.assertFalse(build_status("success","failure","success")["all_essential_steps_succeeded"])

    def test_quality_report_failure(self):
        self.assertFalse(build_status("success","success","failure")["all_essential_steps_succeeded"])

    def test_skipped_not_success(self):
        self.assertFalse(build_status("skipped","skipped","skipped")["all_essential_steps_succeeded"])

    def test_unknown_status_rejected(self):
        with self.assertRaisesRegex(ValueError,"INVALID_GITHUB_STEP_OUTCOME"):
            build_status("success","oops","success")

    def test_not_zero_profit_claim(self):
        x=build_status("failure","failure","skipped")
        self.assertTrue(x["partial_evidence_must_not_be_interpreted_as_zero_returns"])
        self.assertTrue(x["not_an_iex_coverage_measurement"])

    def test_workflow_archives_before_final_failure(self):
        c=WORKFLOW.read_text(encoding="utf8")
        self.assertLess(c.index("name: Archive source identity"),c.index("name: Fail job AFTER archiving"))
        self.assertIn("name: Record real followup step outcomes",c)
        self.assertIn("if: always()",c)
        self.assertIn("luca_v03_second_quality/step_status.json",c)
        self.assertIn("continue-on-error: true",c)
        self.assertIn('if [ "$SIGNAL_OUTCOME" != success ]',c)
        self.assertIn('if [ "$REFERENCE_OUTCOME" != success ]',c)
        self.assertIn('if [ "$QUALITY_OUTCOME" != success ]',c)

if __name__=="__main__":
    unittest.main()
