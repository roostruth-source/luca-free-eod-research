"""No-network failure-inclusive source-run inventory tests."""
import copy
import unittest
from source_run_inventory import build_inventory,SOURCE_WORKFLOW,SOURCE_PATH,SOURCE_BRANCH

def run(rid=40490000001,conclusion="success",status="completed",**kw):
    row={"id":rid,"name":SOURCE_WORKFLOW,"path":SOURCE_PATH,
         "head_branch":SOURCE_BRANCH,"event":"push",
         "created_at":"2026-10-27T14:00:00Z",
         "run_started_at":"2026-10-27T14:00:02Z",
         "status":status,"conclusion":conclusion}
    row.update(kw)
    return row

def payload(*rows,total=None):
    return {"total_count":len(rows) if total is None else total,
            "workflow_runs":list(rows)}

class SourceRunInventoryTests(unittest.TestCase):
    def test_empty_valid_inventory_is_not_a_market_success(self):
        a=build_inventory(payload())
        self.assertEqual(a["runs_listed"],0)
        self.assertTrue(a["github_success_is_not_market_success"])
        self.assertFalse(a["prediction_accuracy_verified"])

    def test_success_not_equal_stock_success(self):
        a=build_inventory(payload(run()))
        self.assertEqual(a["github_success_count"],1)
        self.assertEqual(a["runs"][0]["study_status"],"GITHUB_SUCCESS_EVIDENCE_NOT_YET_VERIFIED")
        self.assertFalse(a["runs"][0]["actual_pattern_success_verified"])

    def test_failed_runs_retained(self):
        a=build_inventory(payload(run(),run(40490000002,conclusion="failure")))
        self.assertEqual(a["github_failed_or_cancelled_count"],1)
        self.assertEqual(a["runs"][1]["study_status"],"GITHUB_FAILURE")

    def test_cancelled_retained(self):
        a=build_inventory(payload(run(conclusion="cancelled")))
        self.assertEqual(a["github_failed_or_cancelled_count"],1)

    def test_timed_out_retained(self):
        a=build_inventory(payload(run(conclusion="timed_out")))
        self.assertEqual(a["github_failed_or_cancelled_count"],1)

    def test_skipped_retained(self):
        a=build_inventory(payload(run(conclusion="skipped")))
        self.assertEqual(a["github_failed_or_cancelled_count"],1)

    def test_pending_not_failure(self):
        a=build_inventory(payload(run(status="in_progress",conclusion=None)))
        self.assertEqual(a["github_pending_count"],1)
        self.assertEqual(a["github_failed_or_cancelled_count"],0)
        self.assertEqual(a["runs"][0]["study_status"],"GITHUB_PENDING_NOT_FAILURE")

    def test_queued_not_failure(self):
        a=build_inventory(payload(run(status="queued",conclusion=None)))
        self.assertEqual(a["github_pending_count"],1)

    def test_no_duplicates(self):
        with self.assertRaisesRegex(ValueError,"DUPLICATE_OR_BAD_RUN_ID"):
            build_inventory(payload(run(),run()))

    def test_no_other_workflow(self):
        with self.assertRaisesRegex(ValueError,"WRONG_WORKFLOW_IN_API_RESPONSE"):
            build_inventory(payload(run(name="Other workflow")))

    def test_no_other_file(self):
        with self.assertRaisesRegex(ValueError,"WRONG_WORKFLOW_FILE"):
            build_inventory(payload(run(path=".github/workflows/production.yml")))

    def test_workflow_path_with_ref(self):
        a=build_inventory(payload(run(path=SOURCE_PATH+"@"+SOURCE_BRANCH)))
        self.assertEqual(a["runs_listed"],1)

    def test_no_main_branch(self):
        with self.assertRaisesRegex(ValueError,"WRONG_BRANCH_OR_EVENT"):
            build_inventory(payload(run(head_branch="main")))

    def test_no_dispatch(self):
        with self.assertRaisesRegex(ValueError,"WRONG_BRANCH_OR_EVENT"):
            build_inventory(payload(run(event="workflow_dispatch")))

    def test_pagination_missing_must_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"PAGINATED_RUNS_INCOMPLETE"):
            build_inventory(payload(run(),total=100))

    def test_broken_total_count(self):
        with self.assertRaisesRegex(ValueError,"INVALID_TOTAL_COUNT"):
            build_inventory(payload(run(),total=0))

    def test_completed_without_conclusion(self):
        with self.assertRaisesRegex(ValueError,"UNKNOWN_COMPLETED_CONCLUSION"):
            build_inventory(payload(run(conclusion=None)))

    def test_active_with_conclusion(self):
        with self.assertRaisesRegex(ValueError,"ACTIVE_RUN_HAS_CONCLUSION"):
            build_inventory(payload(run(status="in_progress",conclusion="success")))

    def test_unexpected_status_rejected(self):
        with self.assertRaisesRegex(ValueError,"UNKNOWN_RUN_STATUS"):
            build_inventory(payload(run(status="surprise",conclusion=None)))

    def test_naive_time_rejected(self):
        with self.assertRaisesRegex(ValueError,"NAIVE_TIMESTAMP"):
            build_inventory(payload(run(created_at="2026-10-27T14:00:00")))

    def test_reverse_timestamps_rejected(self):
        with self.assertRaisesRegex(ValueError,"RUN_START_BEFORE_CREATION"):
            build_inventory(payload(run(run_started_at="2026-10-27T13:59:00Z")))

    def test_order_sorted_by_created_and_run_id(self):
        a=build_inventory(payload(run(40490000002),run(40490000001)))
        self.assertEqual([x["source_run_id"] for x in a["runs"]],[40490000001,40490000002])

    def test_no_trading_grade_ever(self):
        a=build_inventory(payload(run(),run(40490000002,conclusion="failure")))
        self.assertFalse(a["real_trades_allowed"])
        self.assertEqual(a["validation_status"],"NOT_VALIDATED")
        self.assertTrue(all(not x["real_trades_allowed"] for x in a["runs"]))

    def test_all_finished_non_successes_counted(self):
        endings=["failure","cancelled","timed_out","skipped","neutral","action_required","stale"]
        a=build_inventory(payload(*[run(40490000001+i,conclusion=c) for i,c in enumerate(endings)]))
        self.assertEqual(a["github_failed_or_cancelled_count"],len(endings))

if __name__=="__main__":
    unittest.main()
