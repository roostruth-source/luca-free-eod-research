import datetime as dt
import unittest
import hashlib
import json
import math
from mobile_outcomes import build_report, markdown

UTC = dt.timezone.utc
START = dt.datetime(2026, 10, 29, 14, 0, tzinfo=UTC)

def sample(length=66, signal_indices=(5,)):
    bars = [{"t": (START + dt.timedelta(minutes=i)).isoformat(), "c": 100 + i} for i in range(length)]
    return {"schema": "LUCA_V03_IEX_RAW_OHLCV_EVIDENCE_V1",
            "validation_status": "NOT_VALIDATED", "sec_status": "SEC_UNVERIFIED",
            "orders_allowed": False, "real_trades_allowed": False, "all_grades": "D",
            "rows": [{"symbol": "TEST", "ohlcv": bars,
                      "signals": [{"signal": {"signal_bar_start_utc": bars[i]["t"]}, "calculation_input_ohlcv": bars[i-5:i+1]} for i in signal_indices]}]}

class MobileOutcomeTests(unittest.TestCase):
    def test_all_horizons(self):
        r = build_report(sample())["signals"][0]["changes_pct"]
        self.assertEqual(r, {str(n): round(((105+n)/105-1)*100,4) for n in (5,15,30,60)})
    def test_short_window_never_invents_60min(self):
        r = build_report(sample(35))["signals"][0]["changes_pct"]
        self.assertIsNone(r["60"])
        self.assertIsNone(r["30"])
    def test_missing_minute_is_unknown_not_zero(self):
        raw = sample()
        raw["rows"][0]["ohlcv"] = [b for i,b in enumerate(raw["rows"][0]["ohlcv"]) if i != 20]
        self.assertIsNone(build_report(raw)["signals"][0]["changes_pct"]["15"])
    def test_multiple_signals_separately(self):
        r = build_report(sample(signal_indices=(5, 10)))["signals"]
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
    def test_early_signal_timestamp_rejected(self):
        raw = sample()
        raw["rows"][0]["signals"][0]["signal"]["signal_bar_start_utc"] = raw["rows"][0]["ohlcv"][0]["t"]
        with self.assertRaisesRegex(ValueError, "SIGNAL_TIMESTAMP_NOT_LAST_INPUT_BAR"):
            build_report(raw)

    def test_nonconsecutive_signal_bars_rejected(self):
        raw = sample()
        raw["rows"][0]["signals"][0]["calculation_input_ohlcv"][2] = raw["rows"][0]["ohlcv"][9]
        with self.assertRaisesRegex(ValueError, "SIGNAL_INPUT_NOT_CONTIGUOUS"):
            build_report(raw)

    def test_changed_signal_input_price_rejected(self):
        raw = sample()
        raw["rows"][0]["signals"][0]["calculation_input_ohlcv"][3] = dict(raw["rows"][0]["ohlcv"][3], c=999)
        with self.assertRaisesRegex(ValueError, "SIGNAL_INPUT_BAR_MISMATCH"):
            build_report(raw)

    def test_five_signal_bars_rejected(self):
        raw = sample()
        raw["rows"][0]["signals"][0]["calculation_input_ohlcv"].pop()
        with self.assertRaisesRegex(ValueError, "INVALID_SIGNAL_INPUT_WINDOW"):
            build_report(raw)

    def test_no_signal_markdown(self):
        raw=sample(signal_indices=())
        self.assertIn("신호 없음", markdown(build_report(raw)))
    def test_missing_baseline(self):
        raw=sample();raw["rows"][0]["ohlcv"]=raw["rows"][0]["ohlcv"][6:]
        with self.assertRaisesRegex(ValueError, "SIGNAL_INPUT_BAR_MISMATCH"):
            build_report(raw)

if __name__=="__main__":
    unittest.main()
