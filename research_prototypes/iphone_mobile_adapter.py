"""Fail-closed adapter from partial EOD collector to mobile research JSON.

This is NOT a market-wide scanner or trading signal generator.
"""
import datetime as dt
import json
from pathlib import Path
from microcap_candidate_triage import rank

def main():
    feed = json.loads(Path("site_data/latest.json").read_text(encoding="utf-8"))
    if (feed.get("status") != "PARTIAL_EOD_RESEARCH"
            or feed.get("validated") is not False
            or feed.get("orders_enabled") is not False
            or not isinstance(feed.get("rows"), list)
            or not feed["rows"]):
        raise ValueError("EOD feed unavailable or unsafe")
    ts = dt.datetime.fromisoformat(feed["generated_at"].replace("Z", "+00:00"))
    if ts.tzinfo is None or not (
        -dt.timedelta(hours=1) <= dt.datetime.now(dt.timezone.utc) - ts <= dt.timedelta(days=4)
    ):
        raise ValueError("stale feed")
    tickers = [r.get("ticker") for r in feed["rows"] if isinstance(r, dict)]
    if len(tickers) != len(feed["rows"]) or len(set(tickers)) != len(tickers):
        raise ValueError("duplicate or malformed ticker rows")
    if any(not isinstance(r.get("date"), str) or r["date"] != feed.get("asof")
           for r in feed["rows"]):
        raise ValueError("bar date does not match asof")
    result = rank(feed["rows"])
    # Fail closed: do not publish incomplete or malformed batches.
    if result["errors"] or len(result["candidates"]) != len(feed["rows"]):
        raise ValueError("candidate scoring rejected rows")
    by_ticker = {r["ticker"]: r for r in feed["rows"]}
    output = []
    for candidate in result["candidates"]:
        raw = by_ticker[candidate["ticker"]]
        output.append({
            **candidate,
            "date": raw["date"],
            "volume": raw["volume"],
            "active_risks": [],
            "reasons": [candidate["reason"], "SEC and float unverified"],
        })
    payload = {
        "version": 3,
        "generated_at": feed["generated_at"],
        "asof": feed.get("asof"),
        "status": "PARTIAL_RESEARCH",
        "universe": "FIXED_WATCHLIST_NOT_MARKET_WIDE",
        "realtime": False,
        "validated": False,
        "sec_contracts_verified": False,
        "orders_enabled": False,
        "rows": output,
        "errors": [],
        "count": len(output),
    }
    target = Path("site_data/latest_mobile.json")
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

if __name__ == "__main__":
    main()
