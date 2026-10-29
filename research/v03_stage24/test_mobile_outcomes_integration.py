"""Offline integration checks: archived raw IEX evidence -> mobile JSON contract.
No market API, trading, or GitHub workflow invocation.
"""
from __future__ import annotations
import datetime as dt
import json
import unittest
from pathlib import Path
from mobile_outcomes import build_report, markdown

UTC = dt.timezone.utc
START = dt.datetime(2026, 10, 29, 14, 0, tzinfo=UTC)

def synthetic_raw(minutes=35):
    bars = []
    for i in range(minutes):
        bars.append({"t": (START + dt.timedelta(minutes=i)).isoformat(),
                     "o": 100+i, "h": 101+i, "l": 99+i, "c": 100+i, "v": 200})
    return {"schema": "LUCA_V03_IEX_RAW_OHLCV_EVIDENCE_V1",
            "feed": "IEX_SINGLE_EXCHANGE_NOT_SIP",
            "validation_status": "NOT_VALIDATED", "sec_status": "SEC_UNVERIFIED",
            "all_grades": "D", "orders_allowed": False, "real_trades_allowed": False,
            "rows": [{"symbol": "TESTA", "grade": "D", "buy_allowed": False,
                      "ohlcv": bars,
                      "signals": [{"signal": {"signal_bar_start_utc": bars[0]["t"]},
                                   "calculation_input_ohlcv": bars[:6]}]}]}

class MobileIntegrationTests(unittest.TestCase):
    def test_real_archive_field_shapes(self):
        report = build_report(synthetic_raw())
        self.assertEqual(report["schema"], "LUCA_V03_MOBILE_OUTCOMES_V1")
        self.assertEqual(report["signals"][0]["symbol"], "TESTA")
        self.assertIsNone(report["signals"][0]["changes_pct"]["60"])
        self.assertEqual(report["signals"][0]["changes_pct"]["5"], 5.0)
        self.assertFalse(report["orders_allowed"])
        self.assertIn("확인 불가", markdown(report))
    def test_json_serialization_has_no_nan(self):
        encoded = json.dumps(build_report(synthetic_raw()), allow_nan=False)
        self.assertEqual(json.loads(encoded)["signals"][0]["changes_pct"]["60"], None)
    def test_unobserved_future_not_fabricated(self):
        raw = synthetic_raw(6)
        changes = build_report(raw)["signals"][0]["changes_pct"]
        self.assertEqual(changes["5"], 5.0)
        self.assertIsNone(changes["15"])
        self.assertIsNone(changes["30"])
        self.assertIsNone(changes["60"])
    def test_mobile_viewer_accepts_report_contract(self):
        report = build_report(synthetic_raw())
        viewer = Path(__file__).with_name("mobile_outcomes_viewer.html").read_text(encoding="utf8")
        self.assertIn(report["schema"], viewer)
        for key in ("changes_pct", "signal_bar_start_utc", "signal_index", "orders_allowed"):
            self.assertIn(key, viewer)

if __name__ == "__main__":
    unittest.main()
