"""Offline, synthetic test cases. No network, orders or frozen-rule edits."""
import copy
import json
from pathlib import Path
import unittest
from sec_asof_guard import annotate_case, annotate_replay

HERE = Path(__file__).resolve().parent


class SecAsOfGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = json.loads((HERE / "sec_snapshot_2026-10-26.json").read_text(encoding="utf8"))

    def test_gpus_is_blocked(self):
        r = annotate_case({"day": "2026-10-26", "symbol": "GPUS"}, self.snapshot)
        self.assertEqual(r["sec_risk"], "HIGH")
        self.assertFalse(r["actual_buy_allowed"])
        self.assertEqual(r["buy_grade"], "BLOCKED")

    def test_laes_is_blocked(self):
        r = annotate_case({"day": "2026-10-26", "symbol": "LAES"}, self.snapshot)
        self.assertEqual(r["reason"], "DILUTION_RISK")

    def test_unknown_is_also_blocked(self):
        r = annotate_case({"day": "2026-10-26", "symbol": "NIKI"}, self.snapshot)
        self.assertEqual(r["reason"], "SEC_NOT_VERIFIED")
        self.assertFalse(r["actual_buy_allowed"])

    def test_stale_day_rejected(self):
        with self.assertRaisesRegex(ValueError, "SEC_SNAPSHOT_DAY_MISMATCH"):
            annotate_case({"day": "2026-10-27", "symbol": "GPUS"}, self.snapshot)

    def test_future_filing_rejected(self):
        s = copy.deepcopy(self.snapshot)
        s["symbols"]["GPUS"]["filings"][0]["filing_date"] = "2026-10-27"
        with self.assertRaisesRegex(ValueError, "FUTURE_SEC_FILING_LEAKAGE"):
            annotate_case({"day": "2026-10-26", "symbol": "GPUS"}, s)

    def test_fake_source_rejected(self):
        s = copy.deepcopy(self.snapshot)
        s["symbols"]["GPUS"]["filings"][0]["url"] = "https://example.com/fake"
        with self.assertRaisesRegex(ValueError, "SEC_SOURCE_NOT_PRIMARY"):
            annotate_case({"day": "2026-10-26", "symbol": "GPUS"}, s)

    def test_incomplete_universe_rejected(self):
        s = copy.deepcopy(self.snapshot)
        del s["symbols"]["NIKI"]
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_SEC_UNIVERSE"):
            annotate_case({"day": "2026-10-26", "symbol": "GPUS"}, s)

    def test_unsafe_snapshot_rejected(self):
        s = copy.deepcopy(self.snapshot)
        s["real_trades_allowed"] = True
        with self.assertRaisesRegex(ValueError, "UNSAFE_TRADING_FLAG"):
            annotate_case({"day": "2026-10-26", "symbol": "GPUS"}, s)

    def test_future_replay_rejected(self):
        r = {"days_downloaded": ["2026-10-27"], "cases": [],
             "real_trades_allowed": False, "validation_status": "NOT_VALIDATED"}
        with self.assertRaisesRegex(ValueError, "SEC_REPLAY_DATE_MISMATCH"):
            annotate_replay(r, self.snapshot)

    def test_replay_all_blocked(self):
        r = {"days_downloaded": ["2026-10-26"],
             "cases": [{"day": "2026-10-26", "symbol": "GPUS"},
                       {"day": "2026-10-26", "symbol": "LAES"}],
             "real_trades_allowed": False, "validation_status": "NOT_VALIDATED"}
        out = annotate_replay(r, self.snapshot)
        self.assertEqual(out["signal_count"], 2)
        self.assertTrue(all(not x["actual_buy_allowed"] for x in out["cases"]))
        self.assertFalse(out["real_trades_allowed"])

    def test_wrong_symbol_rejected(self):
        with self.assertRaisesRegex(ValueError, "NOT_STUDY_SYMBOL"):
            annotate_case({"day": "2026-10-26", "symbol": "AAPL"}, self.snapshot)


if __name__ == "__main__":
    unittest.main()
