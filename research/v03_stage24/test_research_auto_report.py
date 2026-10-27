"""Integration tests: frozen replay excerpt -> SEC risk -> research report. No network."""
import copy
import json
from pathlib import Path
import unittest
from research_auto_report import build_report, to_markdown

ROOT = Path(__file__).resolve().parent


class AutoReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.replay = json.loads((ROOT/"fixture_frozen_excerpt_2026-10-26.json").read_text(encoding="utf8"))
        cls.sec = json.loads((ROOT/"sec_snapshot_2026-10-26.json").read_text(encoding="utf8"))

    def test_real_replay_excerpt_end_to_end(self):
        out=build_report(self.replay,self.sec)
        self.assertEqual(out["observed_bars"],727)
        self.assertEqual(out["signals"],2)
        self.assertEqual(out["grades"],{"A":0,"B":0,"C":2,"D":3})
        self.assertFalse(out["real_trades_allowed"])
        self.assertEqual(out["validation_status"],"NOT_VALIDATED")
        by={x["symbol"]:x for x in out["rows"]}
        self.assertEqual(by["GPUS"]["15m_historical_change_pct"],-4.789)
        self.assertEqual(by["LAES"]["15m_historical_change_pct"],-0.327)
        self.assertEqual(by["NIKI"]["reason"],"자료 부족")
        self.assertTrue(all(not x["buy_allowed"] for x in out["rows"]))
        self.assertIn("과거 자료",to_markdown(out))

    def test_rules_immutable(self):
        r=copy.deepcopy(self.replay);r["frozen_protocol_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"RULE_HASH_MISMATCH"):
            build_report(r,self.sec)

    def test_hypotheses_immutable(self):
        r=copy.deepcopy(self.replay);r["frozen_hypotheses_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"HYPOTHESIS_HASH_MISMATCH"):
            build_report(r,self.sec)

    def test_future_sec_snapshot_refused(self):
        s=copy.deepcopy(self.sec);s["asof_market_day"]="2026-10-27"
        with self.assertRaisesRegex(ValueError,"SEC_REPLAY_DATE_MISMATCH"):
            build_report(self.replay,s)

    def test_future_filing_refused(self):
        s=copy.deepcopy(self.sec);s["symbols"]["LAES"]["filings"][0]["filing_date"]="2026-10-27"
        with self.assertRaisesRegex(ValueError,"FUTURE_SEC_FILING_LEAKAGE"):
            build_report(self.replay,s)

    def test_missing_sec_data_fails_closed(self):
        s=copy.deepcopy(self.sec);del s["symbols"]["PFSA"]
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_SEC_UNIVERSE"):
            build_report(self.replay,s)

    def test_no_order_flag_override(self):
        r=copy.deepcopy(self.replay);r["real_trades_allowed"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_REPLAY_FLAGS"):
            build_report(r,self.sec)

    def test_no_pretend_live(self):
        r=copy.deepcopy(self.replay);r["source"]="LIVE"
        with self.assertRaisesRegex(ValueError,"SOURCE_MISMATCH"):
            build_report(r,self.sec)

    def test_no_duplicate_first_signal(self):
        r=copy.deepcopy(self.replay);r["cases"].append(copy.deepcopy(r["cases"][0]))
        r["summary"]["total_first_signals"]=3
        with self.assertRaisesRegex(ValueError,"DUPLICATE_FIRST_SIGNAL"):
            build_report(r,self.sec)

    def test_lookahead_time_rejected(self):
        r=copy.deepcopy(self.replay);r["cases"][0]["known_at_utc"]=r["cases"][0]["signal_bar_start_utc"]
        with self.assertRaisesRegex(ValueError,"LOOKAHEAD_OR_TIME_ERROR"):
            build_report(r,self.sec)

    def test_missing_bar_coverage_rejected(self):
        r=copy.deepcopy(self.replay);r["coverage"][2]["missing_minutes"]=0
        with self.assertRaisesRegex(ValueError,"INVALID_BAR_COVERAGE"):
            build_report(r,self.sec)

    def test_unknown_sec_remains_blocked(self):
        r=copy.deepcopy(self.replay)
        r["cases"]=[{"day":"2026-10-26","symbol":"NIKI",
                     "signal_bar_start_utc":"2026-10-26T14:12:00+00:00",
                     "known_at_utc":"2026-10-26T14:13:00+00:00",
                     "real_trades_allowed":False,"15m":{"complete":False}}]
        r["summary"]["total_first_signals"]=1
        out=build_report(r,self.sec)
        n=next(x for x in out["rows"] if x["symbol"]=="NIKI")
        self.assertEqual(n["grade"],"C")
        self.assertFalse(n["buy_allowed"])


if __name__=="__main__":
    unittest.main()
