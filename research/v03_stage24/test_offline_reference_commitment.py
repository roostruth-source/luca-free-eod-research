"""Synthetic checks: commitment tampering and future data cannot silently change cohort."""
import unittest
from offline_reference_commitment import create_commitment, verify_commitment, compare_committed
from test_offline_fixed_time_comparison import fixture, START
import datetime as dt

class CommitmentTests(unittest.TestCase):
    def setUp(self):
        self.raw = fixture()
        self.anchor = (START + dt.timedelta(minutes=5)).isoformat()
        self.manifest = create_commitment(self.anchor, ["NO_SIGNAL", "TESTA"], "synthetic-demo")
    def test_valid_manifest_and_comparison(self):
        self.assertTrue(verify_commitment(self.manifest, self.raw, self.anchor))
        result = compare_committed(self.raw, self.manifest)
        self.assertEqual(result["commitment_sha256"], self.manifest["sha256"])
        self.assertFalse(result["commitment_timestamp_externally_verified"])
    def test_modified_time_rejected(self):
        other = (START + dt.timedelta(minutes=6)).isoformat()
        with self.assertRaisesRegex(ValueError, "REFERENCE_TIME_CHANGED"):
            verify_commitment(self.manifest, self.raw, other)
    def test_changed_manifest_rejected(self):
        self.manifest["payload"]["reference_time_utc"] = self.anchor.replace("14:05", "14:06")
        with self.assertRaisesRegex(ValueError, "HASH_MISMATCH"):
            verify_commitment(self.manifest, self.raw, self.anchor)
    def test_candidate_removed_rejected(self):
        self.raw["rows"].pop()
        with self.assertRaisesRegex(ValueError, "CANDIDATE_UNIVERSE_CHANGED"):
            compare_committed(self.raw, self.manifest)
    def test_candidate_added_rejected(self):
        self.raw["rows"].append({"symbol": "LATE", "signals": [], "ohlcv": []})
        with self.assertRaisesRegex(ValueError, "CANDIDATE_UNIVERSE_CHANGED"):
            compare_committed(self.raw, self.manifest)
    def test_duplicate_symbol_commitment_rejected(self):
        with self.assertRaisesRegex(ValueError, "DUPLICATE_SYMBOL"):
            create_commitment(self.anchor, ["A", "A"], "demo")
    def test_empty_observation_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "INVALID_OBSERVATION_ID"):
            create_commitment(self.anchor, ["A"], "")
    def test_timezone_equivalent_reference(self):
        kst = (START + dt.timedelta(hours=9, minutes=5)).replace(
            tzinfo=dt.timezone(dt.timedelta(hours=9))).isoformat()
        self.assertTrue(verify_commitment(self.manifest, self.raw, kst))

if __name__ == "__main__":
    unittest.main()
