"""Synthetic-only checks for the offline signal/no-signal cohort inventory."""
import unittest
from offline_cohort_inventory import inventory

def fixture():
    return {"schema": "LUCA_V03_IEX_RAW_OHLCV_EVIDENCE_V1",
            "validation_status": "NOT_VALIDATED", "sec_status": "SEC_UNVERIFIED",
            "all_grades": "D", "orders_allowed": False, "real_trades_allowed": False,
            "symbols": 3,
            "rows": [
                {"symbol": "A", "grade": "D", "buy_allowed": False, "signals": [{"signal": {}}], "ohlcv": [{"t": "T"}], "missing_minutes": 0},
                {"symbol": "B", "grade": "D", "buy_allowed": False, "signals": [], "ohlcv": [{"t": "T"}], "missing_minutes": 0},
                {"symbol": "C", "grade": "D", "buy_allowed": False, "signals": [], "ohlcv": [], "missing_minutes": 35}]}

class InventoryTests(unittest.TestCase):
    def test_counts_all_candidates_including_no_signal(self):
        r = inventory(fixture())
        self.assertEqual((r["candidate_count"], r["signal_candidate_count"],
                          r["no_signal_candidate_count"]), (3, 1, 2))
        self.assertEqual(r["no_signal_symbols"], ["B", "C"])
    def test_missing_data_is_visible(self):
        self.assertEqual(inventory(fixture())["missing_or_empty_symbols"], ["C"])
    def test_never_claims_accuracy_or_outcomes(self):
        r = inventory(fixture())
        self.assertFalse(r["comparison_outcomes_calculated"])
        self.assertFalse(r["prediction_accuracy_verified"])
        self.assertFalse(r["orders_allowed"])
    def test_duplicate_symbol_rejected(self):
        raw = fixture()
        raw["rows"][2]["symbol"] = "B"
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            inventory(raw)
    def test_unsafe_flag_rejected(self):
        raw = fixture()
        raw["orders_allowed"] = True
        with self.assertRaisesRegex(ValueError, "UNSAFE"):
            inventory(raw)
    def test_wrong_candidate_count_rejected(self):
        raw = fixture()
        raw["symbols"] = 2
        with self.assertRaisesRegex(ValueError, "COUNT_MISMATCH"):
            inventory(raw)

if __name__ == "__main__":
    unittest.main()
