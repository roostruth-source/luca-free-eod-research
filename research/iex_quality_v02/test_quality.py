"""Offline tests: no Alpaca keys, internet, trading, or market claims."""
import unittest
from datetime import datetime, timedelta, timezone

from quality import QualityBook, parse_completed_bar, parse_utc

UTC = timezone.utc
START = datetime(2026, 10, 26, 14, 0, tzinfo=UTC)


def event(index, *, volume=100, low=None, close=None, kind="b"):
    minute = START + timedelta(minutes=index)
    low = (9.8 + index * 0.1) if low is None else low
    close = (10 + index * 0.1) if close is None else close
    op = close
    return {
        "T": kind, "S": "TEST", "t": minute.isoformat(),
        "o": op, "h": max(op, close, low) + 0.05,
        "l": low, "c": close, "v": volume,
    }


def received(index, seconds=5):
    return START + timedelta(minutes=index + 1, seconds=seconds)


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.book = QualityBook(["TEST"])

    def add_four(self, last_volume=400):
        for i in range(4):
            self.assertEqual(
                self.book.ingest(event(i, volume=last_volume if i == 3 else 100), received(i)),
                "NEW",
            )

    def test_rejects_unfinished_minute(self):
        self.assertEqual(self.book.ingest(event(0), START + timedelta(seconds=45)), "REJECTED")
        self.assertEqual(self.book.summary("TEST", received(0))["unique_completed_minutes"], 0)

    def test_rejects_bad_ohlc(self):
        bad = event(0)
        bad["h"] = bad["l"] - 0.01
        self.assertIsNone(parse_completed_bar(bad, received(0)))
        self.assertEqual(self.book.ingest(bad, received(0)), "REJECTED")

    def test_rejects_invalid_timestamp(self):
        self.assertIsNone(parse_utc("2026-10-26T14:00:00"))
        self.assertIsNone(parse_utc("nonsense"))

    def test_duplicates_do_not_increase_unique_minutes(self):
        self.assertEqual(self.book.ingest(event(0), received(0)), "NEW")
        self.assertEqual(self.book.ingest(event(0), received(0, 8)), "DUPLICATE")
        row = self.book.summary("TEST", received(0, 10))
        self.assertEqual(row["unique_completed_minutes"], 1)
        self.assertEqual(row["duplicate_bar_messages"], 1)

    def test_revision_is_not_visible_before_it_arrives(self):
        self.add_four(last_volume=40)
        before = received(3, 10)
        revision_time = received(3, 20)
        revised = event(3, volume=400, kind="u")
        self.assertEqual(self.book.ingest(revised, revision_time), "REVISION")
        self.assertFalse(self.book.evaluate("TEST", before)["research_pattern"])
        self.assertTrue(self.book.evaluate("TEST", received(3, 21))["research_pattern"])

    def test_four_consecutive_bars_can_form_unverified_pattern(self):
        self.add_four()
        report = self.book.evaluate("TEST", received(3))
        self.assertEqual(report["state"], "OBSERVED_IEX_ONLY")
        self.assertEqual(report["continuous_tail_bars"], 4)
        self.assertTrue(report["rising_3_lows"])
        self.assertEqual(report["volume_ratio"], 4)
        self.assertTrue(report["research_pattern"])

    def test_gap_blocks_pattern(self):
        for i in (0, 1, 3, 4):
            self.book.ingest(event(i, volume=400 if i == 4 else 100), received(i))
        report = self.book.summary("TEST", received(4))
        self.assertEqual(report["missing_minutes_between_first_and_last"], 1)
        self.assertEqual(report["quality_state"], "SPARSE_IEX_BARS")
        self.assertFalse(report["asof_analysis"]["research_pattern"])

    def test_stale_bars_do_not_trigger(self):
        self.add_four()
        report = self.book.evaluate("TEST", received(3) + timedelta(minutes=4))
        self.assertEqual(report["state"], "STALE_IEX_BARS")
        self.assertFalse(report["research_pattern"])

    def test_zero_baseline_volume_does_not_divide_by_zero(self):
        for i in range(4):
            self.book.ingest(event(i, volume=400 if i == 3 else 0), received(i))
        report = self.book.evaluate("TEST", received(3))
        self.assertIsNone(report["volume_ratio"])
        self.assertFalse(report["research_pattern"])

    def test_later_revision_does_not_change_past_evaluation(self):
        self.add_four()
        old_time = received(3, 8)
        old = self.book.evaluate("TEST", old_time)
        revised = event(3, volume=10, kind="u")
        self.book.ingest(revised, received(3, 20))
        self.assertEqual(self.book.evaluate("TEST", old_time), old)
        self.assertFalse(self.book.evaluate("TEST", received(3, 21))["research_pattern"])

    def test_out_of_order_revision_is_rejected(self):
        self.book.ingest(event(0), received(0, 20))
        self.assertEqual(self.book.ingest(event(0, volume=999, kind="u"), received(0, 10)), "OUT_OF_ORDER")
        self.assertEqual(self.book.summary("TEST", received(0, 25))["rejected_bar_messages"], 1)

    def test_trade_only_is_not_zero_market_volume(self):
        self.book.record_trade("TEST")
        row = self.book.summary("TEST", received(0))
        self.assertEqual(row["quality_state"], "IEX_TRADES_WITHOUT_BARS")
        self.assertEqual(row["iex_trade_messages"], 1)

    def test_future_revision_not_used(self):
        self.add_four()
        revision = event(3, volume=0, kind="u")
        self.book.ingest(revision, received(3, 40))
        self.assertTrue(self.book.evaluate("TEST", received(3, 20))["research_pattern"])

    def test_invalid_symbol_fails_closed(self):
        with self.assertRaises(ValueError):
            QualityBook(["bad symbol"])


if __name__ == "__main__":
    unittest.main()
