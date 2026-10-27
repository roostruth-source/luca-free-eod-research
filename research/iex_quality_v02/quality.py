"""LUCA IEX V0.2: as-of data-quality checks. Research only; no order APIs.

All market data here is IEX-only, NOT consolidated US equity data.
A preliminary pattern is not a buy signal or a calibrated probability.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re
from statistics import mean

UTC = timezone.utc
ONE_MINUTE = timedelta(minutes=1)
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,12}$")


def parse_utc(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(UTC) if result.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def finite_number(value, *, positive=False):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    if not math.isfinite(result) or result > 1e14:
        return None
    if positive and result <= 0:
        return None
    if not positive and result < 0:
        return None
    return result


@dataclass(frozen=True)
class MinuteBar:
    symbol: str
    minute: datetime
    received_at: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    kind: str

    def fingerprint(self):
        return (self.open, self.high, self.low, self.close, self.volume)


def parse_completed_bar(event, received_at):
    """Only accept complete IEX b/u bars with internally consistent OHLC.

    received_at is our local observation time, not an exchange timestamp.
    A late updated bar is retained as a new version, never rewritten into
    an earlier as-of view.
    """
    if received_at.tzinfo is None:
        raise ValueError("received_at must be timezone-aware")
    received_at = received_at.astimezone(UTC)
    if not isinstance(event, dict) or event.get("T") not in ("b", "u"):
        return None
    symbol = event.get("S")
    if not isinstance(symbol, str) or not SYMBOL_RE.fullmatch(symbol):
        return None
    minute = parse_utc(event.get("t"))
    if minute is None or minute.second != 0 or minute.microsecond != 0:
        return None
    if minute + ONE_MINUTE > received_at:
        return None  # minute not finished at the time we received the event
    if received_at - minute > timedelta(hours=24):
        return None  # reject very stale/replayed events
    values = [finite_number(event.get(key), positive=True) for key in ("o", "h", "l", "c")]
    volume = finite_number(event.get("v"))
    if any(value is None for value in values) or volume is None:
        return None
    op, high, low, close = values
    if high < max(op, low, close) or low > min(op, high, close):
        return None
    if not volume.is_integer() or volume > 1e12:
        return None
    return MinuteBar(symbol, minute, received_at, op, high, low, close, int(volume), event["T"])


class QualityBook:
    """Append-only versions: historical evaluations cannot see later corrections."""

    def __init__(self, symbols):
        self.symbols = tuple(symbols)
        if not self.symbols or len(self.symbols) > 20 or len(set(self.symbols)) != len(self.symbols):
            raise ValueError("invalid symbols")
        if any(not isinstance(s, str) or not SYMBOL_RE.fullmatch(s) for s in self.symbols):
            raise ValueError("invalid symbols")
        self.versions = {s: {} for s in self.symbols}
        self.trades = {s: 0 for s in self.symbols}
        self.bar_events = {s: 0 for s in self.symbols}
        self.duplicates = {s: 0 for s in self.symbols}
        self.revisions = {s: 0 for s in self.symbols}
        self.rejected = {s: 0 for s in self.symbols}

    def record_trade(self, symbol):
        if symbol in self.trades:
            self.trades[symbol] += 1

    def ingest(self, event, received_at):
        symbol = event.get("S") if isinstance(event, dict) else None
        if symbol not in self.versions:
            return "IGNORED"
        bar = parse_completed_bar(event, received_at)
        if bar is None:
            self.rejected[symbol] += 1
            return "REJECTED"
        self.bar_events[symbol] += 1
        history = self.versions[symbol].setdefault(bar.minute, [])
        if history:
            latest = history[-1]
            if bar.received_at < latest.received_at:
                self.rejected[symbol] += 1
                return "OUT_OF_ORDER"
            if bar.fingerprint() == latest.fingerprint():
                self.duplicates[symbol] += 1
                return "DUPLICATE"
            self.revisions[symbol] += 1
        history.append(bar)
        return "REVISION" if len(history) > 1 else "NEW"

    def bars_asof(self, symbol, known_at):
        if known_at.tzinfo is None:
            raise ValueError("known_at must be timezone-aware")
        known_at = known_at.astimezone(UTC)
        output = []
        for versions in self.versions[symbol].values():
            eligible = [bar for bar in versions if bar.received_at <= known_at]
            if eligible:
                output.append(eligible[-1])
        return sorted(output, key=lambda bar: bar.minute)

    def evaluate(self, symbol, known_at):
        """Evaluate strictly as-of known_at, requiring 4 consecutive minutes."""
        bars = self.bars_asof(symbol, known_at)
        result = {
            "state": "INSUFFICIENT_IEX_BARS",
            "research_pattern": False,
            "last_minute_utc": bars[-1].minute.isoformat() if bars else None,
            "known_at_utc": known_at.astimezone(UTC).isoformat(),
            "continuous_tail_bars": 0,
            "volume_ratio": None,
            "rising_3_lows": None,
            "price_change_pct": None,
        }
        if not bars:
            return result
        tail = [bars[-1]]
        for bar in reversed(bars[:-1]):
            if tail[0].minute - bar.minute != ONE_MINUTE:
                break
            tail.insert(0, bar)
        result["continuous_tail_bars"] = len(tail)
        if known_at.astimezone(UTC) - (tail[-1].minute + ONE_MINUTE) > timedelta(minutes=2):
            result["state"] = "STALE_IEX_BARS"
            return result
        if len(tail) < 4:
            return result
        recent = tail[-4:]
        baseline = mean(b.volume for b in recent[:3])
        ratio = recent[-1].volume / baseline if baseline > 0 else None
        rising = recent[-3].low < recent[-2].low < recent[-1].low
        change = 100 * (recent[-1].close / recent[0].close - 1)
        result.update({
            "state": "OBSERVED_IEX_ONLY",
            "volume_ratio": round(ratio, 3) if ratio is not None else None,
            "rising_3_lows": rising,
            "price_change_pct": round(change, 3),
        })
        result["research_pattern"] = bool(
            ratio is not None and ratio >= 3 and recent[-1].volume >= 100
            and rising and change >= 0.5
        )
        return result

    def summary(self, symbol, known_at):
        bars = self.bars_asof(symbol, known_at)
        missing = 0
        for before, after in zip(bars, bars[1:]):
            gap = int((after.minute - before.minute).total_seconds() // 60)
            missing += max(0, gap - 1)
        analysis = self.evaluate(symbol, known_at)
        state = analysis["state"]
        if not bars and self.trades[symbol] == 0:
            state = "NO_IEX_EVENTS"
        elif not bars:
            state = "IEX_TRADES_WITHOUT_BARS"
        elif missing > 0 and state != "STALE_IEX_BARS":
            state = "SPARSE_IEX_BARS"
        return {
            "symbol": symbol,
            "iex_trade_messages": self.trades[symbol],
            "iex_bar_messages": self.bar_events[symbol],
            "unique_completed_minutes": len(bars),
            "missing_minutes_between_first_and_last": missing,
            "duplicate_bar_messages": self.duplicates[symbol],
            "revised_bar_messages": self.revisions[symbol],
            "rejected_bar_messages": self.rejected[symbol],
            "quality_state": state,
            "asof_analysis": analysis,
        }
