"""Offline fail-closed regression tests for the LUCA research release gate."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "research_prototypes"))
from release_gate_v10 import check


class ReleaseGateTests(unittest.TestCase):
    def run_case(self, test_source=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if test_source is not None:
                (root / "test_sample.py").write_text(test_source, encoding="utf-8")
            report = check(root, root / "status.json")
            self.assertEqual(json.loads((root / "status.json").read_text()), report)
            self.assertEqual(report["status"], "NOT_VALIDATED")
            self.assertEqual(report["sec_status"], "SEC_UNVERIFIED")
            self.assertFalse(report["orders_enabled"])
            self.assertFalse(report["production_approved"])
            return report

    def test_zero_tests_fail_closed(self):
        report = self.run_case()
        self.assertFalse(report["tests_passed"])
        self.assertEqual(report["test_error"], "NO_TESTS_DISCOVERED")

    def test_failing_test_fail_closed(self):
        report = self.run_case("import unittest\nclass T(unittest.TestCase):\n def test_no(self): self.fail('bad')\n")
        self.assertFalse(report["tests_passed"])
        self.assertEqual(report["tests_discovered"], 1)

    def test_passing_tests_do_not_authorize_production(self):
        report = self.run_case("import unittest\nclass T(unittest.TestCase):\n def test_yes(self): self.assertTrue(True)\n")
        self.assertTrue(report["tests_passed"])
        self.assertEqual(report["tests_discovered"], 1)
        self.assertEqual(len(report["release_blockers"]), 7)


if __name__ == "__main__":
    unittest.main()
