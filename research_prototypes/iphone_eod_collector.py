#!/usr/bin/env python3
"""LUCA public EOD watchlist collector. Research only; NO_ORDERS.
Only published closed daily bars, no SEC contract verification, no trading signals.
"""
import csv, datetime as dt, io, json, os, sys, urllib.request
from pathlib import Path
WATCHLIST = ["AAPL", "MSFT", "NVDA", "AMD", "PLTR", "SOFI", "INTC", "F", "LCID", "RIVN"]
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
    rows, errors = [], {}
    for sym in WATCHLIST:
        try: rows.append(fetch(sym))
        except Exception as e: errors[sym] = type(e).__name__ + ": " + str(e)[:140]
    # Always mark incomplete coverage. No stale bar is presented as current.
    last = max((r["date"] for r in rows), default=None)
    rows = [r for r in rows if r["date"] == last]
    valid = bool(rows) and len(rows) >= 3
    result = {"generated_at": now.isoformat(), "asof": last,
      "status": "PARTIAL_EOD_RESEARCH" if valid else "DATA_UNAVAILABLE",
      "validated": False, "realtime": False, "orders_enabled": False,
      "universe": "FIXED_10_SYMBOL_WATCHLIST_NOT_MARKET_WIDE",
      "sec_contracts_verified": False, "float_verified": False,
      "rows": rows if valid else [], "errors": errors}
    (output/"latest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    print("LUCA",result["status"],"rows",len(result["rows"]),"errors",len(errors))
    return 0 if valid else 2
if __name__ == "__main__": sys.exit(run())
