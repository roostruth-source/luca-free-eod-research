"""Regression tests for conservative mobile adapter. No network or orders."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ADAPTER = Path(__file__).with_name("iphone_mobile_adapter.py")

class MobileAdapterSafetyTests(unittest.TestCase):
    def run_adapter(self, feed):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "site_data").mkdir()
            (root / "site_data" / "latest.json").write_text(json.dumps(feed))
            result = subprocess.run([sys.executable, str(ADAPTER)], cwd=root,
                                    capture_output=True, text=True, timeout=15)
            output = root / "site_data" / "latest_mobile.json"
            return result, json.loads(output.read_text()) if output.exists() else None

    def valid_feed(self):
        from datetime import datetime, timezone
        return {
            "status": "PARTIAL_EOD_RESEARCH",
            "validated": False, "orders_enabled": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "asof": "2026-11-16",
            "rows": [{"ticker": "TEST", "date": "2026-11-16",
                      "close": 1.1, "prev_close": 1.0,
                      "volume": 100000, "avg_volume_20d": 10000}]
        }

    def test_research_only_and_unknown_risks(self):
        result, data = self.run_adapter(self.valid_feed())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(data["orders_enabled"])
        self.assertFalse(data["validated"])
        self.assertFalse(data["realtime"])
        self.assertFalse(data["sec_contracts_verified"])
        row = data["rows"][0]
        self.assertLessEqual(row["research_score"], 29)
        self.assertEqual(row["sec_status"], "UNVERIFIED")
        self.assertFalse(row["trading_allowed"])
        self.assertEqual(row["signal"], "RESEARCH_ONLY")
        self.assertIn("cb_active", row["unknown_risks"])

    def test_refuse_unvalidated_contract_claim(self):
        for key, value in (("validated", True), ("orders_enabled", True),
                           ("status", "VALIDATED")):
            with self.subTest(key=key):
                feed = self.valid_feed()
                feed[key] = value
                result, data = self.run_adapter(feed)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(data)

    def test_refuse_empty_rows_and_invalid_price(self):
        for rows in ([], [{"ticker": "TEST", "date": "2026-11-16",
                           "close": 0, "prev_close": 1,
                           "volume": 100, "avg_volume_20d": 10}]):
            with self.subTest(rows=rows):
                feed = self.valid_feed()
                feed["rows"] = rows
                result, data = self.run_adapter(feed)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(data)

if __name__ == "__main__":
    unittest.main()
