from datetime import datetime, timedelta, timezone
import json
import unittest

from volume_first_live import collect, collection_window, evaluate, fetch_iex_minutes

ASOF = datetime(2026, 11, 19, 15, 40, tzinfo=timezone.utc)
BEGIN = datetime(2026, 11, 19, 15, 10, tzinfo=timezone.utc)


def bar(minute, *, low=1.0, volume=10, close=1.5):
    return {"t": (BEGIN + timedelta(minutes=minute)).isoformat(),
            "o": close, "h": max(close, low) + .1, "l": low, "c": close, "v": volume}


def raw_bar(minute, **kwargs):
    item = bar(minute, **kwargs)
    item["t"] = item["t"].replace("+00:00", "Z")
    return item


class Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size=-1):
        return self.payload[:size]


class VolumeFirstLiveTests(unittest.TestCase):
    def test_window_uses_only_completed_minutes(self):
        begin, end = collection_window(ASOF)
        self.assertEqual(end, datetime(2026, 11, 19, 15, 39, tzinfo=timezone.utc))
        self.assertEqual((end - begin).total_seconds(), 29 * 60)

    def test_outside_regular_session_does_not_fetch(self):
        called = False
        def opener(*args, **kwargs):
            nonlocal called
            called = True
        result = collect(["ABC"], "key", "secret",
                         datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc), opener)
        self.assertEqual(result["status"], "OUTSIDE_US_REGULAR_CONTEXT_WINDOW")
        self.assertFalse(called)

    def test_recent_pattern_is_asof_only_and_not_buy_signal(self):
        rows = [bar(i, low=1 + i * .01, volume=300 if i == 29 else 10)
                for i in range(30)]
        result = evaluate(["ABC"], {"ABC": rows}, ASOF, BEGIN,
                          BEGIN + timedelta(minutes=29))
        item = result["rows"][0]
        self.assertTrue(item["volume_first_recent"])
        self.assertEqual(item["latest_pattern"]["iex_volume_ratio"], 30.0)
        self.assertEqual(len(item["evidence_bars"]), 6)
        self.assertTrue(item["NO_ORDERS"])
        self.assertFalse(result["prediction_accuracy_verified"])

    def test_future_knowable_pattern_is_excluded(self):
        rows = [bar(i, low=1 + i * .01, volume=300 if i == 29 else 10)
                for i in range(30)]
        too_early = BEGIN + timedelta(minutes=29, seconds=30)
        result = evaluate(["ABC"], {"ABC": rows}, too_early, BEGIN,
                          BEGIN + timedelta(minutes=29))
        self.assertFalse(result["rows"][0]["volume_first_recent"])

    def test_fetch_is_get_iex_and_rejects_future_symbol(self):
        begin, end = collection_window(ASOF)
        def opener(request, timeout):
            self.assertEqual(request.get_method(), "GET")
            self.assertIn("feed=iex", request.full_url)
            self.assertNotIn("orders", request.full_url)
            return Response({"bars": {"ABC": [raw_bar(29)]}, "next_page_token": None})
        result = fetch_iex_minutes(["ABC"], begin, end, "key", "secret", opener)
        self.assertEqual(len(result["ABC"]), 1)

        def bad(request, timeout):
            return Response({"bars": {"XYZ": []}, "next_page_token": None})
        with self.assertRaisesRegex(ValueError, "unexpected_minute_symbol"):
            fetch_iex_minutes(["ABC"], begin, end, "key", "secret", bad)


if __name__ == "__main__":
    unittest.main()
