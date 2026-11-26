import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from daily_observation_guard import evaluate, EXPECTED_APPROVAL, EXPECTED_BRANCH

ET = ZoneInfo("America/New_York")


def safe_previous(raw="2026-11-25T09:45:00-05:00"):
    return {
        "schema_version": "LUCA_V10_PROSPECTIVE_LEDGER_1",
        "source_collected_at": raw,
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


class DailyObservationGuardTests(unittest.TestCase):
    def check(self, raw="2026-11-27T09:45:00-05:00", **changes):
        values = {
            "now": datetime.fromisoformat(raw),
            "event_name": "workflow_dispatch",
            "ref_name": EXPECTED_BRANCH,
            "approval": EXPECTED_APPROVAL,
            "restore_status": {"restore_status": "RESTORED"},
            "previous": safe_previous(),
        }
        values.update(changes)
        return evaluate(**values)

    def test_valid_manual_research_run_is_allowed(self):
        self.assertTrue(self.check()["allowed"])

    def test_first_run_without_prior_success_is_allowed(self):
        result = self.check(
            restore_status={"restore_status": "NO_PREVIOUS_SUCCESSFUL_RUN"},
            previous=None)
        self.assertTrue(result["allowed"])

    def test_holiday_weekend_and_wrong_time_block(self):
        holiday = self.check("2026-11-26T09:45:00-05:00")
        weekend = self.check("2026-11-28T09:45:00-05:00")
        late = self.check("2026-11-27T10:30:00-05:00")
        self.assertIn("NYSE_WEEKEND_OR_FULL_CLOSURE", holiday["reasons"])
        self.assertIn("NYSE_WEEKEND_OR_FULL_CLOSURE", weekend["reasons"])
        self.assertIn("OUTSIDE_0936_1030_NEW_YORK_WINDOW", late["reasons"])

    def test_wrong_approval_branch_or_event_block(self):
        result = self.check(event_name="schedule", ref_name="main", approval="yes")
        self.assertFalse(result["allowed"])
        self.assertIn("MANUAL_WORKFLOW_DISPATCH_REQUIRED", result["reasons"])
        self.assertIn("WRONG_RESEARCH_BRANCH", result["reasons"])
        self.assertIn("APPROVAL_PHRASE_MISMATCH", result["reasons"])

    def test_duplicate_date_and_restore_failure_block(self):
        duplicate = self.check(previous=safe_previous("2026-11-27T09:40:00-05:00"))
        failed = self.check(restore_status={"restore_status": "UNAVAILABLE"}, previous=None)
        self.assertIn("DUPLICATE_OR_OUT_OF_ORDER_NEW_YORK_DATE", duplicate["reasons"])
        self.assertIn("PREVIOUS_LEDGER_RECOVERY_NOT_SAFE", failed["reasons"])


if __name__ == "__main__":
    unittest.main()
