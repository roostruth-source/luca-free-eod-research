import json
from pathlib import Path
import tempfile
import unittest

from validate_frozen_signals import validate

HERE = Path(__file__).parent


class ValidationReadinessTests(unittest.TestCase):
    def test_real_two_provider_case_is_sample_insufficient(self):
        result = validate(json.loads((HERE / "validation_manifest.json").read_text()), HERE)
        self.assertEqual(result["verified_signals"], 1)
        self.assertEqual(result["matured_horizons"]["1"], 1)
        self.assertEqual(result["matured_horizons"]["5"], 0)
        self.assertEqual(result["coverage_status"], "INSUFFICIENT_VERIFIED_SAMPLE")
        self.assertFalse(result["trade_accuracy_validated"])

    def test_tampered_followup_close_is_excluded(self):
        names = ("inlf_2026-11-13T0008+09.json", "inlf_2026-11-12_followup.json",
                 "inlf_2026-11-12_verified.json")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in names:
                (root / name).write_bytes((HERE / name).read_bytes())
            followup = root / names[1]
            data = json.loads(followup.read_text())
            data["signals"][0]["bars"][0]["close"] = 0.5
            followup.write_text(json.dumps(data))
            manifest = json.loads((HERE / "validation_manifest.json").read_text())
            result = validate(manifest, root)
        self.assertEqual(result["verified_signals"], 0)
        self.assertEqual(result["rejected_cases"][0]["reason"], "canonical_bar_followup_mismatch")

    def test_manifest_cannot_read_outside_input_folder(self):
        manifest = json.loads((HERE / "validation_manifest.json").read_text())
        manifest["cases"][0]["snapshot"] = "../v03_stage24/sec_snapshot_2026-10-26.json"
        result = validate(manifest, HERE)
        self.assertEqual(result["rejected_cases"][0]["reason"], "input_path_outside_base")


if __name__ == "__main__":
    unittest.main()
