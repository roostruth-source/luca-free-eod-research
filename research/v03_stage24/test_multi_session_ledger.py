"""Research-only offline multi-day ledger integrity tests."""
import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from multi_session_ledger import one_session,build_ledger
from followup_bridge import RUN_WORKFLOW,RESEARCH_BRANCH
from test_fixed_clock_reference import pair,prices,READY
from test_forward_outcomes_iex import bars,LATER
from fixed_clock_reference import prepare_result
from forward_outcomes_iex import build_report
from prospective_iex_research import digest_frozen


def fixture(root,run_id=40487785767,with_signal=True,with_outcome=True,with_reference=True):
    d=Path(root)/str(run_id)
    d.mkdir(parents=True,exist_ok=True)
    f,r=pair()
    if not with_signal:
        r["results"][0]["pattern_count"]=0
        r["results"][0]["first_pattern"]=None
    meta={"databaseId":run_id,"name":RUN_WORKFLOW,"headBranch":RESEARCH_BRANCH,
          "event":"push","status":"completed","conclusion":"success"}
    for filename,obj in (("followup_source_metadata.json",meta),
                         ("frozen_t0.json",f),("forward_review.json",r)):
        (d/filename).write_text(json.dumps(obj),encoding="utf8")
    if with_signal and with_outcome:
        (d/"outcomes.json").write_text(json.dumps(build_report(f,r,{"GPUS":bars()},LATER)),encoding="utf8")
    if with_reference:
        (d/"fixed_clock_reference.json").write_text(
            json.dumps(prepare_result(f,r,{"GPUS":prices(),"LAES":prices()},READY)),encoding="utf8")
    return d


class MultiSessionLedgerTests(unittest.TestCase):
    def test_single_valid_session(self):
        with tempfile.TemporaryDirectory() as d:
            folder=fixture(d)
            row=one_session(folder)
            self.assertEqual(row["source_run_id"],40487785767)
            self.assertEqual(row["session_date_ny"],"2026-10-27")
            self.assertEqual(row["initial_pattern_symbols"],1)
            self.assertEqual(row["initial_no_pattern_symbols"],1)
            self.assertEqual(row["signal_outcomes_status"],"OBSERVED_COMPLETE_IEX_ONLY")
            self.assertFalse(row["real_trades_allowed"])

    def test_aggregate_5_15_30_60_evidence_counts(self):
        with tempfile.TemporaryDirectory() as d:
            row=one_session(fixture(d))
            ledger=build_ledger([row])
            totals=ledger["totals"]
            self.assertEqual(totals["sessions"],1)
            self.assertEqual(totals["frozen_candidates"],2)
            self.assertEqual(totals["signal_horizons_complete"],{"5":1,"15":1,"30":1,"60":1})
            self.assertEqual(totals["reference_horizons_complete"],{"5":2,"15":2,"30":2,"60":2})
            self.assertFalse(ledger["predictive_accuracy_verified"])
            self.assertTrue(ledger["no_profit_or_win_rate_claim"])

    def test_zero_signal_not_fabricated(self):
        with tempfile.TemporaryDirectory() as d:
            row=one_session(fixture(d,with_signal=False))
            ledger=build_ledger([row])
            self.assertEqual(ledger["totals"]["initial_pattern_symbols"],0)
            self.assertEqual(ledger["totals"]["initial_no_pattern_symbols"],2)
            self.assertEqual(ledger["totals"]["sessions_with_signal_outcomes"],0)
            self.assertEqual(ledger["totals"]["sessions_with_reference"],1)

    def test_missing_outcomes_not_zero(self):
        with tempfile.TemporaryDirectory() as d:
            row=one_session(fixture(d,with_outcome=False))
            ledger=build_ledger([row])
            self.assertFalse(ledger["research_sessions"][0]["outcome_records_present"])
            self.assertEqual(ledger["totals"]["sessions_with_signal_outcomes"],0)

    def test_missing_reference_not_zero(self):
        with tempfile.TemporaryDirectory() as d:
            row=one_session(fixture(d,with_reference=False))
            ledger=build_ledger([row])
            self.assertEqual(ledger["totals"]["sessions_with_reference"],0)
            self.assertEqual(ledger["research_sessions"][0]["reference_status"],"AWAITING_OR_UNAVAILABLE")

    def test_duplicate_run_id_fails(self):
        with tempfile.TemporaryDirectory() as d:
            row=one_session(fixture(d))
            with self.assertRaisesRegex(ValueError,"DUPLICATE_OR_INVALID_RUN_ID"):
                build_ledger([row,copy.deepcopy(row)])

    def test_different_run_same_freeze_fails(self):
        with tempfile.TemporaryDirectory() as d:
            row=one_session(fixture(d))
            other=copy.deepcopy(row);other["source_run_id"]+=1
            with self.assertRaisesRegex(ValueError,"DUPLICATE_OR_INVALID_T0_FREEZE"):
                build_ledger([row,other])

    def test_same_ny_date_with_different_freeze_fails(self):
        with tempfile.TemporaryDirectory() as d:
            row=one_session(fixture(d))
            other=copy.deepcopy(row);other["source_run_id"]+=1
            other["freeze_sha256"]="a"*64
            with self.assertRaisesRegex(ValueError,"DUPLICATE_NY_SESSION_DATE"):
                build_ledger([row,other])

    def test_valid_two_separate_sessions_sorted(self):
        with tempfile.TemporaryDirectory() as d:
            row=one_session(fixture(d))
            other=copy.deepcopy(row)
            other["source_run_id"]+=1
            other["freeze_sha256"]="a"*64
            other["session_date_ny"]="2026-10-28"
            ledger=build_ledger([other,row])
            self.assertEqual(ledger["totals"]["sessions"],2)
            self.assertEqual([x["session_date_ny"] for x in ledger["research_sessions"]],
                             ["2026-10-27","2026-10-28"])
            self.assertEqual(ledger["totals"]["initial_pattern_symbols"],2)

    def test_failed_source_run_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=fixture(d)
            path=folder/"followup_source_metadata.json"
            meta=json.loads(path.read_text());meta["conclusion"]="failure"
            path.write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,"PROSPECTIVE_RUN_NOT_SUCCESSFUL"):
                one_session(folder)

    def test_wrong_source_workflow_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=fixture(d)
            path=folder/"followup_source_metadata.json"
            meta=json.loads(path.read_text());meta["name"]="Production"
            path.write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,"WRONG_WORKFLOW"):
                one_session(folder)

    def test_wrong_branch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=fixture(d)
            path=folder/"followup_source_metadata.json"
            meta=json.loads(path.read_text());meta["headBranch"]="main"
            path.write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,"WRONG_BRANCH_OR_EVENT"):
                one_session(folder)

    def test_wrong_source_id_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=fixture(d)
            path=folder/"followup_source_metadata.json"
            meta=json.loads(path.read_text());meta["databaseId"]=999999999
            path.write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,"WRONG_RUN_ID"):
                one_session(folder)

    def test_invalid_folder_name_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=fixture(d)
            folder.rename(Path(d)/"../unsafe")
            with self.assertRaisesRegex(ValueError,"RUN_DIRECTORY_MUST_BE_SOURCE_ID"):
                one_session(Path(d)/"../unsafe")

    def test_wrong_t0_hash_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=fixture(d)
            path=folder/"frozen_t0.json"
            f=json.loads(path.read_text());f["selected_at_utc"]="2026-10-27T13:46:00+00:00"
            path.write_text(json.dumps(f))
            with self.assertRaisesRegex(ValueError,"T0_HASH_MISMATCH"):
                one_session(folder)

    def test_forged_outcome_symbol_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=fixture(d)
            path=folder/"outcomes.json"
            data=json.loads(path.read_text());data["signals"][0]["symbol"]="AAPL"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"OUTCOME_SIGNAL_UNIVERSE_DRIFT"):
                one_session(folder)

    def test_reference_clock_changed_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            folder=fixture(d)
            path=folder/"fixed_clock_reference.json"
            data=json.loads(path.read_text());data["reference_utc"]="2026-10-27T13:53:00+00:00"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"REFERENCE_CLOCK_CHANGED_AFTER_T0"):
                one_session(folder)

    def test_fake_buy_approval_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            row=one_session(fixture(d))
            row["real_trades_allowed"]=True
            with self.assertRaisesRegex(ValueError,"UNSAFE_OR_INVALID_SESSION"):
                build_ledger([row])

    def test_no_real_evidence_does_not_make_valid_study(self):
        ledger=build_ledger([])
        self.assertEqual(ledger["totals"]["sessions"],0)
        self.assertFalse(ledger["predictive_accuracy_verified"])
        self.assertTrue(ledger["failed_run_counts_not_available"])

    def test_reject_tampered_completeness_claim(self):
        with tempfile.TemporaryDirectory() as d:
            folder=fixture(d)
            path=folder/"outcomes.json"
            data=json.loads(path.read_text());data["complete_horizons"]=100
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"OUTCOME_COMPLETENESS_DRIFT"):
                one_session(folder)


if __name__=="__main__":
    unittest.main()
