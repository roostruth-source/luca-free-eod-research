#!/usr/bin/env python3
"""LUCA public EOD watchlist collector. Research only; NO_ORDERS.
Only published closed daily bars, no SEC contract verification, no trading signals.
"""
import csv, datetime as dt, io, json, os, sys, urllib.request
from pathlib import Path
WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMD", "PLTR", "SOFI", "INTC", "F", "LCID", "RIVN"]
# Optional, explicitly curated symbols. Never claim complete Nasdaq coverage.
SYMBOLS_FILE = Path("research_prototypes/watchlist_symbols.txt")
MAX_SYMBOLS_PER_RUN = 40

def load_symbols(path=SYMBOLS_FILE):
    if not path.exists():
        return list(WATCHLIST), "FIXED_10_SYMBOL_WATCHLIST_NOT_MARKET_WIDE"
    raw = path.read_text(encoding="utf-8").splitlines()
    symbols = []
    for line in raw:
        line = line.strip().upper()
        if not line or line.startswith("#"):
            continue
        if not line.isascii() or not line.isalnum() or len(line) > 6:
            raise ValueError("invalid watchlist symbol")
        if line not in symbols:
            symbols.append(line)
    if not 3 <= len(symbols) <= 2000:
        raise ValueError("watchlist must contain 3 to 2000 unique symbols")
    return symbols, "CURATED_WATCHLIST_NOT_MARKET_WIDE"

def select_batch(symbols, today, limit=MAX_SYMBOLS_PER_RUN):
    """Deterministic rotation; no claim that a batch represents the whole market."""
    if len(symbols) <= limit:
        return symbols
    # Each calendar day scans the next slice; roughly full rotation over ceil(N/limit) days.
    # Count weekdays since a fixed Monday to advance one batch per business day.\n    anchor = dt.date(2020, 1, 6)\n    days = max(0, (today - anchor).days)\n    weeks, remainder = divmod(days, 7)\n    trading_days = weeks * 5 + min(remainder, 5)\n    offset = (trading_days * limit) % len(symbols)
    return [symbols[(offset + i) % len(symbols)] for i in range(limit)]

UA = "LUCAResearch/1.0 research-contact research@example.invalid"
def fetch(symbol):
    url = "https://stooq.com/q/d/l/?s=" + symbol.lower() + ".us&i=d"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/csv"})
    with urllib.request.urlopen(req, timeout=18) as r:
        raw = r.read(2_000_001)
    if len(raw) > 2_000_000: raise ValueError("file too large")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    if len(rows) < 23: raise ValueError("insufficient history")
    rows.sort(key=lambda r: r["Date"])
    last, prev = rows[-1], rows[-2]
    dates = [dt.date.fromisoformat(x["Date"]) for x in (prev, last)]
    if dates[0] >= dates[1] or dates[1] > dt.datetime.now(dt.timezone.utc).date():
        raise ValueError("invalid dates")
    vols = [int(float(r["Volume"])) for r in rows[-21:-1]]
    if min(vols) < 0 or not any(vols): raise ValueError("invalid volumes")
    c = float(last["Close"]); pc = float(prev["Close"])
    if c <= 0 or pc <= 0: raise ValueError("invalid price")
    return {"ticker": symbol, "date": str(dates[1]), "close": c,
        "prev_close": pc, "volume": int(float(last["Volume"])),
        "avg_volume_20d": sum(vols)/len(vols), "float_shares": None,
        "high_20d": max(float(x["High"]) for x in rows[-20:]),
        "low_20d": min(float(x["Low"]) for x in rows[-20:]),
        "sec_verified": False, "source": "Stooq EOD", "source_url": url,
        "point_in_time_float_verified": False, "contract_terms_verified": False}
def run():
    now = dt.datetime.now(dt.timezone.utc)
    output = Path("site_data"); output.mkdir(exist_ok=True)
    symbols, universe = load_symbols()
    batch = select_batch(symbols, now.date())
    rows, errors = [], {}
    for sym in batch:
        try: rows.append(fetch(sym))
        except Exception as e: errors[sym] = type(e).__name__ + ": " + str(e)[:140]
    # Always mark incomplete coverage. No stale bar is presented as current.
    last = max((r["date"] for r in rows), default=None)
    rows = [r for r in rows if r["date"] == last]
    valid = bool(rows) and len(rows) >= 3
    result = {"generated_at": now.isoformat(), "asof": last,
      "status": "PARTIAL_EOD_RESEARCH" if valid else "DATA_UNAVAILABLE",
      "validated": False, "realtime": False, "orders_enabled": False,
      "universe": universe,
      "watchlist_size": len(symbols), "scanned_count": len(batch),
      "sec_contracts_verified": False, "float_verified": False,
      "rows": rows if valid else [], "errors": errors}
    (output/"latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    print("LUCA",result["status"],"rows",len(result["rows"]),"errors",len(errors))
    return 0 if valid else 2
if __name__ == "__main__": sys.exit(run())
