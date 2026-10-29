import datetime as dt
import unittest
import hashlib
import json
import math
from mobile_outcomes import build_report, markdown

UTC = dt.timezone.utc
START = dt.datetime(2026, 10, 29, 14, 0, tzinfo=UTC)

def sample(length=61, signal_indices=(0,)):
    bars = [{"t": (START + dt.timedelta(minutes=i)).isoformat(), "c": 100 + i} for i in range(length)]
    return {"schema": "LUCA_V03_IEX_RAW_OHLCV_EVIDENCE_V1",
            "validation_status": "NOT_VALIDATED", "sec_status": "SEC_UNVERIFIED",
            "orders_allowed": False, "real_trades_allowed": False, "all_grades": "D",
            "rows": [{"symbol": "TEST", "ohlcv": bars,
                      "signals": [{"signal": {"signal_bar_start_utc": bars[i]["t"]}} for i in signal_indices]}]}

class MobileOutcomeTests(unittest.TestCase):
    def test_all_horizons(self):
        r = build_report(sample())["signals"][0]["changes_pct"]
        self.assertEqual(r, {"5": 5.0, "15": 15.0, "30": 30.0, "60": 60.0})
    def test_short_window_never_invents_60min(self):
        r = build_report(sample(35))["signals"][0]["changes_pct"]
        self.assertIsNone(r["60"])
        self.assertEqual(r["30"], 30.0)
    def test_missing_minute_is_unknown_not_zero(self):
        raw = sample()
        raw["rows"][0]["ohlcv"] = [b for i,b in enumerate(raw["rows"][0]["ohlcv"]) if i != 15]
        self.assertIsNone(build_report(raw)["signals"][0]["changes_pct"]["15"])
    def test_multiple_signals_separately(self):
        r = build_report(sample(signal_indices=(0, 10)))["signals"]
        self.assertEqual(len(r), 2)
        self.assertEqual(r[1]["changes_pct"]["5"], round((115/110-1)*100,4))
    def test_duplicate_bars_rejected(self):
        raw=sample();raw["rows"][0]["ohlcv"].append(raw["rows"][0]["ohlcv"][0].copy())
        with self.assertRaisesRegex(ValueError, "DUPLICATE"):
            build_report(raw)
    def test_naive_timestamp_rejected(self):
        raw=sample();raw["rows"][0]["ohlcv"][0]["t"]="2026-10-29T14:00:00"
        with self.assertRaisesRegex(ValueError, "TIMEZONE"):
            build_report(raw)
    def test_unsafe_order_flag_rejected(self):
        raw=sample();raw["orders_allowed"]=True
        with self.assertRaisesRegex(ValueError, "UNSAFE"):
            build_report(raw)
    def test_hash_mismatch_rejected(self):
        raw=sample();raw["sha256"]="0"*64
        with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
            build_report(raw)
    def test_valid_hash_accepted(self):
        raw=sample()
        raw["sha256"]=hashlib.sha256(json.dumps(raw,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        self.assertEqual(len(build_report(raw)["signals"]),1)
    def test_nan_price_rejected(self):
        raw=sample();raw["rows"][0]["ohlcv"][0]["c"]=math.nan
        with self.assertRaisesRegex(ValueError, "INVALID_CLOSE"):
            build_report(raw)
    def test_bad_row_rejected(self):
        raw=sample();raw["rows"]=[None]
        with self.assertRaisesRegex(ValueError, "INVALID_ROW"):
            build_report(raw)
    def test_unsafe_row_rejected(self):
        raw=sample();raw["rows"][0]["buy_allowed"]=True
        with self.assertRaisesRegex(ValueError, "UNSAFE_ROW"):
            build_report(raw)
    def test_no_signal_markdown(self):
        raw=sample(signal_indices=())
        self.assertIn("신호 없음", markdown(build_report(raw)))
    def test_missing_baseline(self):
        raw=sample();raw["rows"][0]["ohlcv"]=raw["rows"][0]["ohlcv"][1:]
        self.assertTrue(all(x is None for x in build_report(raw)["signals"][0]["changes_pct"].values()))

if __name__=="__main__":
    unittest.main()
