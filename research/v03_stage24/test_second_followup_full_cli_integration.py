"""End-to-end offline second followup rehearsal: real CLI interfaces, fake market bars.

Checks the actual GitHub workflow's JSON handoff chain using synthetic records,
without API keys, network, orders, schedules, or any real second run claims.
"""
from __future__ import annotations
import copy
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_two_session_iex_comparison import fixture,SECOND_ID
from test_second_trial_artifact_bridge import META,ART
from second_trial_artifact_bridge import main as bridge_main
from second_followup_gate import gate,BRANCH
from second_korean_research_report import main as korean_main
from evidence_quality_gate import main as quality_main
from fixed_clock_reference import fixed_reference_entries,prepare_result
from forward_outcomes_iex import build_report,validate_origins

UTC=dt.timezone.utc


def fake_bars(entry, n=60):
    return [{"t":(entry+dt.timedelta(minutes=i)).isoformat(),
             "o":1.00,"h":1.20,"l":0.90,"c":1.05,"v":200}
            for i in range(n)]


def json_write(root,path,doc):
    file=root/path
    file.parent.mkdir(parents=True,exist_ok=True)
    file.write_text(json.dumps(doc),encoding="utf8")


class SecondRealWorkflowOfflineIntegrationTests(unittest.TestCase):
    def replay(self,minutes):
        frozen,review,provenance=fixture(minutes)
        meta=copy.deepcopy(META)
        artifact=copy.deepcopy(ART)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            source=root/"source"
            json_write(root,Path("source/frozen_t0.json"),frozen)
            json_write(root,Path("source/forward_review.json"),review)
            json_write(root,Path("source/iex_timestamp_provenance.json"),provenance)
            json_write(root,Path("metadata.json"),meta)
            json_write(root,Path("artifact.json"),artifact)
            comparison=root/"comparison.json"
            with patch.object(sys,"argv",["bridge",
                "--second-metadata",str(root/"metadata.json"),
                "--second-artifact-metadata",str(root/"artifact.json"),
                "--second-artifact-dir",str(source),
                "--output",str(comparison)]):
                bridge_main()
            counts=json.loads(comparison.read_text())
            self.assertEqual(counts["second"]["observed"],len(minutes))
            self.assertTrue(counts["second_source_workflow_verified"])
            t0,reviewed,signals=validate_origins(frozen,review)
            maturity=t0+dt.timedelta(minutes=100)
            gate_record=gate(str(SECOND_ID)+"\n",meta,frozen,review,provenance,
                             maturity,"push",BRANCH,"1",1)
            self.assertTrue(gate_record["iex_timestamp_grid_verified"])
            outcomes_file=root/"outcomes.json"
            outcome=None
            if signals:
                outcome=build_report(frozen,review,
                                     {sym:fake_bars(when) for sym,when in signals.items()},maturity)
                json_write(root,Path("outcomes.json"),outcome)
            reference_entries=fixed_reference_entries(frozen,review)
            reference=prepare_result(frozen,review,
                    {sym:fake_bars(when) for sym,when in reference_entries.items()},maturity)
            json_write(root,Path("reference.json"),reference)
            quality_file=root/"quality.json"
            argv=["quality","--source",str(source),
                  "--reference",str(root/"reference.json"),
                  "--dest",str(quality_file)]
            if outcome is not None:
                argv.extend(["--outcomes",str(outcomes_file)])
            with patch.object(sys,"argv",argv):
                quality_main()
            quality=json.loads(quality_file.read_text())
            self.assertEqual(quality["pattern_observed_symbols"],len(signals))
            self.assertEqual(quality["validation_status"],"NOT_VALIDATED")
            self.assertFalse(quality["real_trades_allowed"])
            korean_file=root/"report.md"
            argv=["korean","--metadata",str(root/"metadata.json"),
                  "--source-dir",str(source),"--comparison",str(comparison),
                  "--reference",str(root/"reference.json"),"--output",str(korean_file)]
            if outcome is not None:
                argv.extend(["--outcomes",str(outcomes_file)])
            with patch.object(sys,"argv",argv):
                korean_main()
            korean=korean_file.read_text(encoding="utf8")
            self.assertIn("2차 IEX 수집:",korean)
            self.assertIn("실제 주문 금지",korean)
            self.assertIn("후속 IEX 분봉 확인",korean)
            self.assertNotIn("실전 매수 가능",korean)
            return quality,korean

    def test_real_cli_chain_one_synthetic_pattern_with_mature_60m(self):
        quality,report=self.replay((0,1,2,3,4,5,7,9,11))
        self.assertEqual(quality["pattern_observed_symbols"],1)
        self.assertEqual(quality["signal_outcome_evidence"],"OBSERVED_COMPLETE_IEX_ONLY")
        self.assertEqual(quality["fixed_clock_reference_evidence"],"OBSERVED_COMPLETE_IEX_ONLY")
        self.assertIn("전조 패턴 관측: 1종목",report)

    def test_real_cli_chain_no_pattern_does_not_fabricate_signal_result(self):
        quality,report=self.replay(())
        self.assertEqual(quality["pattern_observed_symbols"],0)
        self.assertEqual(quality["signal_outcome_evidence"],"AWAITING_OR_UNAVAILABLE")
        self.assertEqual(quality["fixed_clock_reference_evidence"],"OBSERVED_COMPLETE_IEX_ONLY")
        self.assertIn("전조 패턴 관측: 0종목",report)
        self.assertIn("후속 관찰 자료 없음",report)

    def test_real_cli_chain_sparse_grid_remains_not_predictive(self):
        quality,report=self.replay((0,1,2))
        self.assertEqual(quality["first_window_sparse_symbols"],1)
        self.assertEqual(quality["quality"],"INSUFFICIENT_FOR_PREDICTION")
        self.assertIn("분봉 누락·패턴 미관측(판정 불가)",report)


if __name__=="__main__":
    unittest.main()
