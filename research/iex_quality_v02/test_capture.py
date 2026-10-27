"""Offline collector-input tests; no API key, no network, no orders."""
import json
import unittest
from datetime import datetime, timedelta, timezone

from capture import parse_symbols, safe_events
from quality import parse_completed_bar

UTC = timezone.utc
T0 = datetime(2026, 10, 27, 14, 0, tzinfo=UTC)


class CaptureInputTests(unittest.TestCase):
    def test_symbol_normalization_and_deduplication(self):
        self.assertEqual(parse_symbols(" aapl, NIKI; aapl "), ["AAPL", "NIKI"])

    def test_rejects_empty_symbols(self):
        with self.assertRaises(ValueError):
            parse_symbols(" , ")

    def test_rejects_invalid_symbol(self):
        with self.assertRaises(ValueError):
            parse_symbols("AAPL,SECRET/KEY")

    def test_rejects_more_than_twenty(self):
        with self.assertRaises(ValueError):
            parse_symbols(",".join("X" + str(i) for i in range(21)))

    def test_bad_json_frame_does_not_raise(self):
        self.assertEqual(safe_events("not-json"), [])

    def test_only_dict_events_are_kept(self):
        frame = json.dumps([{"T": "t", "S": "AAPL"}, None, 4, "hi", []])
        self.assertEqual(safe_events(frame), [{"T": "t", "S": "AAPL"}])

    def test_bar_is_not_complete_before_minute_end(self):
        event = {"T": "b", "S": "AAPL", "t": T0.isoformat(),
                 "o": 10, "h": 11, "l": 9, "c": 10.5, "v": 100}
        self.assertIsNone(parse_completed_bar(event, T0 + timedelta(seconds=59)))
        self.assertIsNotNone(parse_completed_bar(event, T0 + timedelta(seconds=60)))

    def test_bar_rejects_negative_or_nan_prices(self):
        event = {"T": "b", "S": "AAPL", "t": T0.isoformat(),
                 "o": 10, "h": 11, "l": 9, "c": "NaN", "v": 100}
        self.assertIsNone(parse_completed_bar(event, T0 + timedelta(seconds=61)))
        event["c"] = -5
        self.assertIsNone(parse_completed_bar(event, T0 + timedelta(seconds=61)))


if __name__ == "__main__":
    unittest.main()
