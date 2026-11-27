import hashlib
import json
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
import warnings
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from archive_bundle import (FIXED_ZIP_TIME, REQUIRED_FILES, build_bundle,
                            recover_bundle, verify_bundle)


COMMIT = "8" * 40
CREATED = "2026-11-27T15:00:00Z"


def canonical_hash(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def safe_json(**extra):
    return {"WATCH_ONLY": True, "NO_ORDERS": True,
            "validation_status": "NOT_VALIDATED", **extra}


def write_inputs(root: Path):
    event = {"ticker": "TEST", "NO_ORDERS": True, "predicted_spike": False}
    head = hashlib.sha256((("0" * 64) + canonical_hash(event)).encode()).hexdigest()
    values = {
        "daily_guard.json": safe_json(
            schema_version="LUCA_V10_DAILY_GUARD_1", allowed=True,
            new_york_time="2026-11-27T09:45:00-05:00"),
        "live_watchlist.json": safe_json(rows=[]),
        "prospective_ledger.json": safe_json(
            schema_version="LUCA_V10_PROSPECTIVE_LEDGER_1",
            source_collected_at="2026-11-27T14:45:00+00:00",
            event_count=1, events=[{**event, "chain_hash": head}],
            last_chain_hash=head),
        "prospective_outcomes.json": safe_json(records=[]),
        "restore_status.json": {"restore_status": "RESTORED"},
        "validation_readiness.json": safe_json(coverage_status="INSUFFICIENT"),
    }
    for name in REQUIRED_FILES:
        path = root / name
        if name.endswith(".json"):
            path.write_text(json.dumps(values[name], ensure_ascii=False) + "\n")
        else:
            path.write_text("<p>WATCH_ONLY · NOT_VALIDATED · NO_ORDERS</p>\n")


def build(root: Path, name="bundle.zip") -> Path:
    inputs = root / "inputs"
    inputs.mkdir()
    write_inputs(inputs)
    output = root / name
    build_bundle(inputs, output, COMMIT, "12345", CREATED)
    return output


def rewrite(path: Path, transform):
    with ZipFile(path) as archive:
        members = [(info.filename, archive.read(info)) for info in archive.infolist()]
    path.unlink()
    with ZipFile(path, "w", compression=ZIP_STORED) as archive:
        for name, payload in transform(members):
            info = ZipInfo(name, FIXED_ZIP_TIME)
            info.compress_type = ZIP_STORED
            info.external_attr = (0o100444 << 16)
            archive.writestr(info, payload)


class ArchiveBundleTests(unittest.TestCase):
    def test_recover_reports_from_production_renderers_without_market_access(self):
        from prospective_ledger import append_observations
        from prospective_outcomes import build_outcomes, render_html as outcomes_html
        from run_live_research import assemble, render_html as watchlist_html
        from unified_observer_report import render_html as unified_html
        from validate_frozen_signals import validate

        live = assemble({"status": "SYNTHETIC_EMPTY_TEST", "rows": []},
                        datetime.fromisoformat("2026-11-27T09:45:00-05:00"))
        ledger = append_observations(live, CREATED)
        outcomes = build_outcomes(ledger, {}, CREATED)
        directory = Path(__file__).resolve().parent
        validation = validate(json.loads((directory / "validation_manifest.json").read_text()),
                              directory)
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            write_inputs(root)
            for name, data in (("live_watchlist", live), ("prospective_ledger", ledger),
                               ("prospective_outcomes", outcomes), ("validation_readiness", validation)):
                (root / (name + ".json")).write_text(json.dumps(data))
            for name, html in (("live_watchlist.html", watchlist_html(live)),
                               ("prospective_outcomes.html", outcomes_html(outcomes)),
                               ("luca_v10_observer_report.html", unified_html(live, outcomes, validation))):
                (root / name).write_text(html)
            archive = root / "test.zip"
            build_bundle(root, archive, COMMIT, "1", CREATED)
            recovered = root / "recovered"
            self.assertEqual(recover_bundle(archive, recovered)["event_count"], 0)
            for name in REQUIRED_FILES:
                self.assertEqual((root / name).read_bytes(), (recovered / name).read_bytes())
            page = root / "live_watchlist.html"
            page.write_text(page.read_text().replace("주문 없음", ""))
            with self.assertRaisesRegex(ValueError, "safety_markers_missing:live_watchlist"):
                build_bundle(root, root / "invalid.zip", COMMIT, "1", CREATED)

    def test_build_is_deterministic_and_verifies(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            first = build(root, "first.zip")
            inputs = root / "inputs"
            second = root / "second.zip"
            build_bundle(inputs, second, COMMIT, "12345", CREATED)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            result = verify_bundle(first)
            self.assertTrue(result["verified"])
            self.assertEqual(result["event_count"], 1)
            self.assertEqual(result["validation_status"], "NOT_VALIDATED")

    def test_recovery_preserves_every_source_byte_and_manifest(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archive = build(root)
            recovered = root / "recovered"
            result = recover_bundle(archive, recovered)
            self.assertEqual(result["recovered_to"], str(recovered))
            self.assertTrue((recovered / "manifest.json").is_file())
            for name in REQUIRED_FILES:
                self.assertEqual((recovered / name).read_bytes(),
                                 (root / "inputs" / name).read_bytes())

    def test_build_refuses_to_overwrite_archive(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archive = build(root)
            with self.assertRaisesRegex(FileExistsError, "already_exists"):
                build_bundle(root / "inputs", archive, COMMIT, "1", CREATED)

    def test_recovery_refuses_existing_destination(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archive = build(root)
            destination = root / "existing"
            destination.mkdir()
            with self.assertRaisesRegex(FileExistsError, "must_not_exist"):
                recover_bundle(archive, destination)

    def test_missing_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            inputs = root / "inputs"
            inputs.mkdir()
            write_inputs(inputs)
            (inputs / "live_watchlist.json").unlink()
            with self.assertRaisesRegex(ValueError, "required_regular_file_missing"):
                build_bundle(inputs, root / "out.zip", COMMIT, "1", CREATED)

    def test_unsafe_order_flag_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            inputs = root / "inputs"
            inputs.mkdir()
            write_inputs(inputs)
            value = json.loads((inputs / "live_watchlist.json").read_text())
            value["rows"] = [{"order_allowed": True}]
            (inputs / "live_watchlist.json").write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "unsafe_claim"):
                build_bundle(inputs, root / "out.zip", COMMIT, "1", CREATED)

    def test_broken_ledger_chain_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            inputs = root / "inputs"
            inputs.mkdir()
            write_inputs(inputs)
            value = json.loads((inputs / "prospective_ledger.json").read_text())
            value["events"][0]["ticker"] = "CHANGED"
            (inputs / "prospective_ledger.json").write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, "ledger_chain_invalid"):
                build_bundle(inputs, root / "out.zip", COMMIT, "1", CREATED)

    def test_payload_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as raw:
            archive = build(Path(raw))
            rewrite(archive, lambda members: [
                (name, payload + b"changed" if name == "live_watchlist.html" else payload)
                for name, payload in members
            ])
            with self.assertRaisesRegex(ValueError, "digest_mismatch"):
                verify_bundle(archive)

    def test_unexpected_or_nested_archive_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            archive = build(Path(raw))
            rewrite(archive, lambda members: members + [("nested/extra.txt", b"x")])
            with self.assertRaisesRegex(ValueError, "member_set_invalid"):
                verify_bundle(archive)

    def test_duplicate_archive_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            archive = build(Path(raw))
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                rewrite(archive, lambda members: members + [members[-1]])
            with self.assertRaisesRegex(ValueError, "duplicate_archive_member"):
                verify_bundle(archive)

    def test_invalid_source_and_naive_time_are_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            inputs = root / "inputs"
            inputs.mkdir()
            write_inputs(inputs)
            with self.assertRaisesRegex(ValueError, "commit_invalid"):
                build_bundle(inputs, root / "one.zip", "bad", "1", CREATED)
            with self.assertRaisesRegex(ValueError, "timezone_required"):
                build_bundle(inputs, root / "two.zip", COMMIT, "1", "2026-11-27T15:00:00")

    def test_html_without_safety_banner_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            inputs = root / "inputs"
            inputs.mkdir()
            write_inputs(inputs)
            (inputs / "luca_v10_observer_report.html").write_text("<p>report</p>")
            with self.assertRaisesRegex(ValueError, "safety_markers_missing"):
                build_bundle(inputs, root / "out.zip", COMMIT, "1", CREATED)


if __name__ == "__main__":
    unittest.main()
