"""Synthetic end-to-end smoke test. Patches socket: no internet or real API keys."""
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from capture import run
from outcomes import build_report, read_jsonl
from quality import parse_utc

UTC = timezone.utc


class FakeSocket:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def send(self, text):
        self.sent.append(json.loads(text))

    def recv(self, timeout):
        try:
            return next(self.frames)
        except StopIteration:
            raise TimeoutError()


def fake_modules(socket):
    websockets = types.ModuleType("websockets")
    websockets.__path__ = []
    sync = types.ModuleType("websockets.sync")
    sync.__path__ = []
    client = types.ModuleType("websockets.sync.client")
    client.connect = lambda *args, **kwargs: socket
    websockets.sync = sync
    sync.client = client
    return {
        "websockets": websockets,
        "websockets.sync": sync,
        "websockets.sync.client": client,
    }


class PipelineTests(unittest.TestCase):
    def test_full_synthetic_capture_and_outcome_pipeline(self):
        now = datetime.now(UTC)
        minute = now.replace(second=0, microsecond=0) - timedelta(minutes=4)
        frames = [
            json.dumps([{"T": "success", "msg": "authenticated"}]),
            json.dumps([{"T": "subscription", "trades": ["TEST"], "bars": ["TEST"],
                         "updatedBars": ["TEST"]}]),
        ]
        for i in range(4):
            close = round(10 + 0.1 * i, 3)
            frames.append(json.dumps([{
                "T": "b", "S": "TEST",
                "t": (minute + timedelta(minutes=i)).isoformat(),
                "o": close, "h": close + 0.1, "l": close - 0.2,
                "c": close, "v": 400 if i == 3 else 100,
            }]))
        frames.append(json.dumps([{
            "T": "t", "S": "TEST", "t": now.isoformat(), "p": 10.3, "s": 100,
        }]))
        fake_socket = FakeSocket(frames)
        clock = itertools.count(start=100, step=14)
        with tempfile.TemporaryDirectory() as dirname:
            with patch.dict(sys.modules, fake_modules(fake_socket)), \
                 patch.dict(os.environ, {"ALPACA_KEY": "dummy", "ALPACA_SECRET": "dummy"}), \
                 patch("capture.time.monotonic", side_effect=lambda: next(clock)):
                report = run(["TEST"], 3, dirname)

            folder = Path(dirname)
            self.assertEqual(report["raw_event_rows"], 5)
            self.assertEqual(report["unvalidated_pattern_events"], 1)
            self.assertTrue((folder / "summary.json").exists())
            self.assertTrue((folder / "summary.md").exists())
            self.assertEqual(fake_socket.sent[0]["action"], "auth")
            self.assertEqual(fake_socket.sent[1]["action"], "subscribe")
            signals = read_jsonl(folder / "signals.jsonl")
            self.assertEqual(len(signals), 1)
            self.assertFalse(signals[0]["buy_signal"])
            self.assertFalse(signals[0]["sec_checked"])
            raw = read_jsonl(folder / "raw_events.jsonl")
            self.assertEqual(len(raw), 5)
            self.assertFalse(any("dummy" in json.dumps(x) for x in raw))
            outcomes = build_report(
                signals, raw,
                evaluated_at=parse_utc(report["finished_utc"]),
                capture_end=parse_utc(report["finished_utc"]),
            )
            self.assertEqual(len(outcomes["signals"]), 1)
            self.assertEqual(outcomes["signals"][0]["horizons"]["5"]["status"], "PENDING")
            self.assertFalse(outcomes["validated"])


if __name__ == "__main__":
    unittest.main()
