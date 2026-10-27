"""Synthetic future-outcome checks. No API keys or live trading."""
import unittest
from datetime import datetime, timedelta, timezone

from outcomes import build_report, evaluate_signal, reference_price

UTC = timezone.utc
T0 = datetime(2026, 10, 26, 14, 0, tzinfo=UTC)


def iso(seconds):
    return (T0 + timedelta(seconds=seconds)).isoformat()


def signal():
    return {
        "symbol": "TEST",
        "known_at_utc": iso(70),  # 14:01:10, after the reference minute closes
        "evidence": {"last_minute_utc": iso(0)},
    }


def bar(price=10, received_seconds=65, kind="minute_bar"):
    return {
        "type": kind, "symbol": "TEST",
        "minute_utc": iso(0), "received_at_utc": iso(received_seconds),
        "close": price,
    }


def trade(price=11, exchange_seconds=380, received_seconds=381):
    return {
        "type": "trade", "symbol": "TEST",
        "exchange_at_utc": iso(exchange_seconds),
        "received_at_utc": iso(received_seconds),
        "price": price,
    }


def evaluate(rows, *, seconds=3900, capture_seconds=3900, truncated=False):
    return evaluate_signal(
        signal(), rows, evaluated_at=T0 + timedelta(seconds=seconds),
        capture_end=T0 + timedelta(seconds=capture_seconds), truncated=truncated,
    )


class OutcomeTests(unittest.TestCase):
    def test_five_minute_future_trade_observed(self):
        # Signal at 70s; +5min window begins at 370s; trade at 380s.
        result = evaluate([bar(), trade()])
        five = result["horizons"]["5"]
        self.assertEqual(five["status"], "IEX_OBSERVED_NOT_EXECUTABLE_FILL")
        self.assertEqual(five["change_pct_vs_reference"], 10.0)
        self.assertEqual(result["reference_price"], 10.0)

    def test_future_trade_cannot_be_used_before_received(self):
        # Exchange timestamp is in the target window, but received later.
        result = evaluate([bar(), trade(received_seconds=600)], seconds=440, capture_seconds=3900)
        self.assertEqual(result["horizons"]["5"]["status"], "NO_IEX_TRADE_IN_WINDOW")

    def test_no_asof_reference(self):
        result = evaluate([bar(received_seconds=100), trade()])
        self.assertEqual(result["horizons"]["5"]["status"], "NO_ASOF_REFERENCE_BAR")

    def test_later_bar_revision_does_not_rewrite_signal_reference(self):
        rows = [bar(price=10, received_seconds=65), bar(price=20, received_seconds=200, kind="updated_minute_bar")]
        self.assertEqual(reference_price(signal(), rows), 10.0)

    def test_capture_shorter_than_horizon_is_not_false_failure(self):
        result = evaluate([bar()], seconds=3900, capture_seconds=400)
        self.assertEqual(result["horizons"]["5"]["status"], "CAPTURE_ENDED_BEFORE_TARGET")
        self.assertEqual(result["horizons"]["60"]["status"], "CAPTURE_ENDED_BEFORE_TARGET")

    def test_unmatured_horizon_is_pending(self):
        result = evaluate([bar()], seconds=100, capture_seconds=3900)
        self.assertEqual(result["horizons"]["5"]["status"], "PENDING")

    def test_no_trade_is_not_zero_return(self):
        result = evaluate([bar()])
        five = result["horizons"]["5"]
        self.assertEqual(five["status"], "NO_IEX_TRADE_IN_WINDOW")
        self.assertIsNone(five["change_pct_vs_reference"])

    def test_trade_outside_target_window_not_used(self):
        result = evaluate([bar(), trade(exchange_seconds=435, received_seconds=436)])
        self.assertEqual(result["horizons"]["5"]["status"], "NO_IEX_TRADE_IN_WINDOW")

    def test_truncated_raw_blocks_grading(self):
        result = evaluate([bar(), trade()], truncated=True)
        self.assertEqual(result["horizons"]["5"]["status"], "INCOMPLETE_CAPTURE")

    def test_no_capture_end_is_not_assumed_complete(self):
        result = evaluate_signal(signal(), [bar(), trade()], evaluated_at=T0 + timedelta(seconds=3900))
        self.assertEqual(result["horizons"]["5"]["status"], "CAPTURE_ENDED_BEFORE_TARGET")

    def test_no_signal_means_no_results(self):
        report = build_report([], [], evaluated_at=T0 + timedelta(seconds=3900))
        self.assertEqual(report["signals"], [])
        self.assertFalse(report["validated"])

    def test_all_four_horizons_are_reported(self):
        result = evaluate([bar(), trade()])
        self.assertEqual(set(result["horizons"]), {"5", "15", "30", "60"})


if __name__ == "__main__":
    unittest.main()
