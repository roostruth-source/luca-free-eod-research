"""Offline tests of verified first REAL coverage archive and tamper detection."""
import copy
import json
import unittest
from pathlib import Path
from first_iex_baseline_integrity import load_verified,verify_first_normalized

ROOT=Path(__file__).resolve().parent
def originals():
    return (json.loads((ROOT/"first_real_iex_audit_normalized_40532482508.json").read_text()),
            json.loads((ROOT/"first_real_iex_audit_manifest_40532482508.json").read_text()))

class FirstArchiveTests(unittest.TestCase):
    def setUp(self):
        self.first,self.manifest=originals()

    def check(self):
        return verify_first_normalized(self.first,self.manifest)

    def test_real_normalized_archive_passes(self):
        r=self.check()
        self.assertEqual(r["rows_verified"],12)
        self.assertFalse(r["real_trades_allowed"])
        self.assertFalse(r["original_raw_file_archived"])

    def test_load_verified_file(self):
        self.assertEqual(load_verified()["source_run_id"],40517830351)

    def test_manifest_sha_change_blocks(self):
        self.manifest["artifact_uncompressed_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"MANIFEST_DRIFT"):
            self.check()

    def test_manifest_source_run_change_blocks(self):
        self.manifest["source_run_id"]=999
        with self.assertRaisesRegex(ValueError,"MANIFEST_DRIFT"):
            self.check()

    def test_frozen_t0_hash_change_blocks(self):
        self.first["frozen_t0_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"IDENTITY_DRIFT"):
            self.check()

    def test_symbol_order_change_blocks(self):
        self.first["rows"][0]["symbol"]="GPUS"
        with self.assertRaisesRegex(ValueError,"SYMBOL_ORDER_DRIFT"):
            self.check()

    def test_bar_count_change_blocks(self):
        self.first["rows"][0]["initial_iex_minutes"]=12
        with self.assertRaisesRegex(ValueError,"INITIAL_ROWS_DRIFT"):
            self.check()

    def test_reference_bar_change_blocks(self):
        self.first["rows"][0]["reference"][0]["iex_bars"]=5
        self.first["rows"][0]["reference"][0]["complete"]=True
        with self.assertRaisesRegex(ValueError,"REFERENCE_ROWS_DRIFT"):
            self.check()

    def test_reference_complete_false_claim_blocks(self):
        self.first["rows"][6]["reference"][3]["complete"]=False
        with self.assertRaisesRegex(ValueError,"REFERENCE_ROWS_DRIFT"):
            self.check()

    def test_summary_change_blocks(self):
        self.first["fixed_clock_reference"][0]["observed_iex_bars"]=36
        with self.assertRaisesRegex(ValueError,"REFERENCE_SUMMARY_DRIFT"):
            self.check()

    def test_trading_approval_blocks(self):
        self.first["real_trades_allowed"]=True
        with self.assertRaisesRegex(ValueError,"UNSAFE_FIRST_ARCHIVE"):
            self.check()

    def test_missing_bar_cause_cannot_be_claimed_known(self):
        self.first["missing_bar_cause_unknown"]=False
        with self.assertRaisesRegex(ValueError,"UNSAFE_FIRST_ARCHIVE"):
            self.check()

if __name__=="__main__":
    unittest.main()
