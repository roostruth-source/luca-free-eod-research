"""Offline raw OHLCV archive and deterministic replay tests."""
import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from iex_raw_evidence import (
    build_raw_evidence, canonical_sha256, evidence_sha256,
    replay_raw_evidence, signal_formula_source_sha256, write_new,
)
from iex_timestamp_provenance import build_minute_provenance
from prospective_iex_research import digest_frozen, review
from test_live_trial_contract import make_synthetic
from test_prospective_iex_research import T1, make_bar


def fixture():
    frozen, _ = make_synthetic()
    frozen["candidates"] = ["GPUS", "EMPTY", "GAP", "NOSIG"]
    frozen["candidate_count"] = 4
    frozen["sha256"] = digest_frozen(frozen)
    signal = [make_bar(i, low=1 + i * .01,
                       volume=300 if i == 5 else 20) for i in range(12)]
    gap = [make_bar(i, low=1 + i * .01, volume=20) for i in (0, 2, 4, 6, 8)]
    no_signal = [make_bar(i, low=1 + i * .01, volume=20) for i in range(8)]
    bars = {"GPUS": signal, "EMPTY": [], "GAP": gap, "NOSIG": no_signal}
    recorded = review(frozen, bars, T1)
    provenance = build_minute_provenance(
        frozen, recorded, bars, T1 + dt.timedelta(seconds=1),
        {"get_only": True, "http_statuses": [200],
         "final_page_token_absent": True})
    raw = build_raw_evidence(frozen, recorded, bars, provenance)
    return frozen, bars, recorded, provenance, raw


class RawEvidenceTests(unittest.TestCase):
    def test_all_symbols_signal_absence_and_missing_bars_are_archived(self):
        _, bars, _, _, raw = fixture()
        self.assertEqual([row["symbol"] for row in raw["rows"]], list(bars))
        status = {row["symbol"]: row["record_status"] for row in raw["rows"]}
        self.assertEqual(status["GPUS"], "SIGNAL_RECORDED")
        self.assertEqual(status["EMPTY"], "NO_IEX_BARS_RECORDED")
        self.assertEqual(status["GAP"], "NO_EVALUABLE_SIX_MINUTE_WINDOW")
        self.assertEqual(status["NOSIG"], "NO_SIGNAL_IN_EVALUABLE_WINDOWS")
        self.assertEqual(raw["rows"][1]["ohlcv"], [])
        self.assertEqual(raw["rows"][1]["missing_minutes"], 15)
        self.assertFalse(raw["real_trades_allowed"])
        self.assertFalse(raw["orders_allowed"])
        self.assertEqual(raw["all_grades"], "D")
        self.assertEqual(raw["signal_formula_source_sha256"],
                         signal_formula_source_sha256())

    def test_signal_time_and_exact_six_calculation_bars_are_saved(self):
        _, bars, recorded, _, raw = fixture()
        row = raw["rows"][0]
        saved = row["signals"][0]
        self.assertEqual(saved["signal"], recorded["results"][0]["first_pattern"])
        self.assertEqual(saved["calculation_input_ohlcv"], bars["GPUS"][:6])
        self.assertEqual(saved["signal"]["signal_bar_start_utc"], bars["GPUS"][5]["t"])
        self.assertEqual(saved["signal"]["bar_knowable_after_utc"],
                         (dt.datetime.fromisoformat(bars["GPUS"][5]["t"]) +
                          dt.timedelta(minutes=1)).isoformat())

    def test_raw_bars_recalculate_to_exact_recorded_review(self):
        frozen, _, recorded, provenance, raw = fixture()
        replay = replay_raw_evidence(raw, frozen, recorded, provenance)
        self.assertTrue(replay["recorded_review_exact_match"])
        self.assertTrue(replay["recorded_signal_inputs_exact_match"])
        self.assertEqual(replay["bars_replayed"], raw["observed_iex_bars"])
        self.assertEqual(replay["signal_symbols_replayed"], 1)
        self.assertFalse(replay["real_trades_allowed"])

    def test_changed_raw_price_fails_hash_before_replay(self):
        frozen, _, recorded, provenance, raw = fixture()
        changed = copy.deepcopy(raw)
        changed["rows"][0]["ohlcv"][0]["c"] = 1.51
        with self.assertRaisesRegex(ValueError, "RAW_EVIDENCE_HASH_MISMATCH"):
            replay_raw_evidence(changed, frozen, recorded, provenance)

    def test_rehashed_changed_raw_price_still_fails_recalculation(self):
        frozen, _, recorded, provenance, raw = fixture()
        changed = copy.deepcopy(raw)
        changed["rows"][0]["ohlcv"][0]["c"] = 1.51
        changed["sha256"] = evidence_sha256(changed)
        with self.assertRaisesRegex(ValueError, "RECALCULATED_REVIEW_MISMATCH"):
            replay_raw_evidence(changed, frozen, recorded, provenance)

    def test_changed_old_review_cannot_be_silently_accepted(self):
        frozen, _, recorded, provenance, raw = fixture()
        changed = copy.deepcopy(recorded)
        changed["results"][0]["pattern_count"] = 0
        with self.assertRaisesRegex(ValueError, "REVIEW_HASH_MISMATCH"):
            replay_raw_evidence(raw, frozen, changed, provenance)

    def test_provenance_identity_is_bound_to_archive(self):
        frozen, _, recorded, provenance, raw = fixture()
        changed = copy.deepcopy(provenance)
        changed["recorded_at_utc"] = T1.isoformat()
        with self.assertRaisesRegex(ValueError, "TIMESTAMP_PROVENANCE_HASH_MISMATCH"):
            replay_raw_evidence(raw, frozen, recorded, changed)
        self.assertEqual(raw["timestamp_provenance_sha256"], canonical_sha256(provenance))

    def test_forged_missing_minute_grid_blocks_archive(self):
        frozen, bars, recorded, provenance, _ = fixture()
        changed = copy.deepcopy(provenance)
        changed["rows"][0]["missing_iex_bar_start_utc"][0] = T1.isoformat()
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_MINUTE_GRID"):
            build_raw_evidence(frozen, recorded, bars, changed)

    def test_unsafe_flags_are_rejected_even_after_rehash(self):
        frozen, _, recorded, provenance, raw = fixture()
        changed = copy.deepcopy(raw)
        changed["real_trades_allowed"] = True
        changed["sha256"] = evidence_sha256(changed)
        with self.assertRaisesRegex(ValueError, "UNSAFE_RAW_EVIDENCE"):
            replay_raw_evidence(changed, frozen, recorded, provenance)

    def test_changed_signal_formula_identity_blocks_replay(self):
        frozen, _, recorded, provenance, raw = fixture()
        changed = copy.deepcopy(raw)
        changed["signal_formula_source_sha256"] = "0" * 64
        changed["sha256"] = evidence_sha256(changed)
        with self.assertRaisesRegex(ValueError, "SIGNAL_FORMULA_SOURCE_CHANGED"):
            replay_raw_evidence(changed, frozen, recorded, provenance)

    def test_write_is_create_only(self):
        _, _, _, _, raw = fixture()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "raw.json"
            write_new(path, raw)
            self.assertEqual(json.loads(path.read_text()), raw)
            with self.assertRaisesRegex(FileExistsError, "IMMUTABLE_RAW_EVIDENCE_EXISTS"):
                write_new(path, raw)


if __name__ == "__main__":
    unittest.main()
