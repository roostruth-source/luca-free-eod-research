"""Bounded as-of IEX minute context for V10 watchlist observations.

The detector reuses the frozen V0.3 research formula, but only bars knowable at
or before the current observation timestamp are eligible.  Concurrent screener
selection can still be late, so a pattern is never called an early prediction.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

V03_DIR = Path(__file__).resolve().parents[1] / "v03_stage24"
sys.path.insert(0, str(V03_DIR))
from auto_discover import valid_symbol  # noqa: E402
from iex_1min_research import find_patterns, valid_bar  # noqa: E402

ET = ZoneInfo("America/New_York")
BAR_URL = "https://data.alpaca.markets/v2/stocks/bars"
MAX_SYMBOLS = 12
LOOKBACK_MINUTES = 30
RECENT_PATTERN_MINUTES = 10
MAX_BYTES = 2_000_000
MAX_PAGES = 5
SAFETY = {"WATCH_ONLY": True, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED"}


def collection_window(asof: datetime) -> tuple[datetime, datetime] | None:
    if not isinstance(asof, datetime) or asof.tzinfo is None:
        raise ValueError("asof_timezone_required")
    local = asof.astimezone(ET)
    if local.weekday() >= 5 or not (time(9, 36) <= local.time() <= time(16, 0)):
        return None
    completed = asof.astimezone(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=1)
    session_open = datetime.combine(local.date(), time(9, 30), tzinfo=ET).astimezone(timezone.utc)
    begin = max(session_open, completed - timedelta(minutes=LOOKBACK_MINUTES - 1))
    return begin, completed


def fetch_iex_minutes(symbols: list[str], begin: datetime, end: datetime,
                      key: str, secret: str, opener=None) -> dict[str, list[dict]]:
    if (not 1 <= len(symbols) <= MAX_SYMBOLS or len(symbols) != len(set(symbols))
            or not all(valid_symbol(symbol) for symbol in symbols)):
        raise ValueError("invalid_symbol_batch")
    if not key or not secret:
        raise ValueError("alpaca_credentials_required")
    opener = opener or urllib.request.urlopen
    rows = {symbol: [] for symbol in symbols}
    seen = {symbol: set() for symbol in symbols}
    token = None
    used_tokens = set()
    for _ in range(MAX_PAGES):
        params = {
            "symbols": ",".join(symbols), "timeframe": "1Min",
            "start": begin.isoformat(), "end": end.isoformat(),
            "feed": "iex", "adjustment": "raw", "sort": "asc", "limit": 10000,
        }
        if token:
            params["page_token"] = token
        request = urllib.request.Request(
            BAR_URL + "?" + urllib.parse.urlencode(params),
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                     "Accept": "application/json",
                     "User-Agent": "LUCA-V10-RESEARCH-READONLY/1.0"},
            method="GET")
        with opener(request, timeout=30) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("minute_response_too_large")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("bars"), dict):
            raise ValueError("invalid_minute_response")
        if not set(payload["bars"]).issubset(rows):
            raise ValueError("unexpected_minute_symbol")
        for symbol, bars in payload["bars"].items():
            if not isinstance(bars, list):
                raise ValueError("invalid_minute_bars")
            for raw_bar in bars:
                bar = valid_bar(raw_bar, begin, end)
                if bar["t"] in seen[symbol]:
                    raise ValueError("duplicate_minute_bar")
                seen[symbol].add(bar["t"])
                rows[symbol].append(bar)
        next_token = payload.get("next_page_token")
        if next_token is None:
            return {symbol: sorted(bars, key=lambda item: item["t"])
                    for symbol, bars in rows.items()}
        if not isinstance(next_token, str) or not next_token or next_token in used_tokens:
            raise ValueError("invalid_minute_pagination")
        used_tokens.add(next_token)
        token = next_token
    raise ValueError("minute_pagination_limit")


def _evidence_window(bars: list[dict], pattern: dict | None) -> list[dict]:
    if pattern is None:
        return bars[-6:]
    stamp = pattern["signal_bar_start_utc"]
    for index, bar in enumerate(bars):
        if bar["t"] == stamp:
            return bars[max(0, index - 5):index + 1]
    raise ValueError("pattern_evidence_bar_missing")


def evaluate(symbols: list[str], bars: dict[str, list[dict]], asof: datetime,
             begin: datetime, end: datetime) -> dict:
    if set(bars) != set(symbols):
        raise ValueError("minute_bar_universe_mismatch")
    now = asof.astimezone(timezone.utc)
    output = []
    for symbol in symbols:
        symbol_bars = bars[symbol]
        patterns = [item for item in find_patterns(symbol_bars)
                    if datetime.fromisoformat(item["bar_knowable_after_utc"]).astimezone(timezone.utc)
                    <= now]
        recent = [item for item in patterns
                  if now - datetime.fromisoformat(item["bar_knowable_after_utc"]).astimezone(timezone.utc)
                  <= timedelta(minutes=RECENT_PATTERN_MINUTES)]
        latest = recent[-1] if recent else None
        status = ("RECENT_VOLUME_FIRST_PATTERN_RESEARCH_ONLY" if latest
                  else "NO_RECENT_VOLUME_FIRST_PATTERN" if len(symbol_bars) >= 6
                  else "INSUFFICIENT_CONTIGUOUS_IEX_CONTEXT")
        output.append({
            "symbol": symbol, "status": status,
            "volume_first_recent": latest is not None,
            "observed_bar_count": len(symbol_bars),
            "latest_pattern": latest,
            "evidence_bars": _evidence_window(symbol_bars, latest),
            "selection_limit": "CONCURRENT_SCREENER_SELECTION_NOT_EARLY_PROOF",
            **SAFETY,
        })
    return {
        "schema_version": "LUCA_V10_VOLUME_FIRST_ASOF_1",
        "status": "IEX_MINUTE_CONTEXT_COLLECTED",
        "collected_at": now.isoformat(),
        "window": {"start": begin.isoformat(), "end": end.isoformat()},
        "studied_symbols": len(symbols), "rows": output,
        "prediction_accuracy_verified": False,
        **SAFETY,
    }


def collect(symbols: list[str], key: str, secret: str, asof: datetime,
            opener=None) -> dict:
    studied = symbols[:MAX_SYMBOLS]
    if not studied:
        return {"schema_version": "LUCA_V10_VOLUME_FIRST_ASOF_1",
                "status": "NO_CANDIDATES", "studied_symbols": 0, "rows": [], **SAFETY}
    window = collection_window(asof)
    if window is None:
        return {"schema_version": "LUCA_V10_VOLUME_FIRST_ASOF_1",
                "status": "OUTSIDE_US_REGULAR_CONTEXT_WINDOW", "studied_symbols": 0,
                "rows": [], **SAFETY}
    begin, end = window
    try:
        bars = fetch_iex_minutes(studied, begin, end, key, secret, opener)
        return evaluate(studied, bars, asof, begin, end)
    except urllib.error.HTTPError as exc:
        reason = f"IEX_MINUTE_HTTP_{exc.code}"
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        reason = "IEX_MINUTE_" + type(exc).__name__.upper()
    return {"schema_version": "LUCA_V10_VOLUME_FIRST_ASOF_1",
            "status": reason, "studied_symbols": len(studied), "rows": [], **SAFETY}
