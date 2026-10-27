"""Research-only candidate enrichment: Alpaca screeners -> explicit IEX snapshots.

A price filter is NOT a market-cap/float filter. Outside US regular hours or with
stale IEX prints, candidates remain PENDING, not approved. GET only, no orders.
"""
from __future__ import annotations
import datetime as dt
import json
import math
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo
from auto_discover import collect, valid_symbol

UTC = dt.timezone.utc
ET = ZoneInfo("America/New_York")
URL = "https://data.alpaca.markets/v2/stocks/snapshots"
BATCH_SIZE = 35
MAX_UNIVERSE = 140
MIN_PRICE, MAX_PRICE = 0.20, 20.00
MAX_AGE_SECONDS = 600


def parse_time(s):
    if not isinstance(s, str):
        return None
    try:
        t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
        return t.astimezone(UTC) if t.tzinfo else None
    except (TypeError, ValueError):
        return None


def valid_price(v):
    return type(v) in (int, float) and math.isfinite(v) and v > 0


def regular_session(now):
    t = now.astimezone(ET)
    return t.weekday() < 5 and (9, 30) <= (t.hour, t.minute) < (16, 0)


def fetch_iex_snapshots(symbols, key, secret, opener=None):
    if not symbols or len(symbols) > BATCH_SIZE or len(set(symbols)) != len(symbols):
        raise ValueError("INVALID_BATCH")
    if any(not valid_symbol(s) for s in symbols):
        raise ValueError("INVALID_SYMBOL")
    if not key or not secret:
        raise ValueError("MISSING_KEYS")
    query = urllib.parse.urlencode({"symbols": ",".join(symbols), "feed": "iex"})
    req = urllib.request.Request(URL+"?"+query, method="GET", headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json", "User-Agent": "LUCA-RESEARCH-GET-ONLY/0.3",
    })
    with (opener or urllib.request.urlopen)(req, timeout=30) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("SNAPSHOT_TOO_LARGE")
    result = json.loads(raw)
    if not isinstance(result, dict) or not set(result).issubset(set(symbols)):
        raise ValueError("INVALID_SNAPSHOT_RESPONSE")
    if any(v is not None and not isinstance(v, dict) for v in result.values()):
        raise ValueError("INVALID_SNAPSHOT_RECORD")
    return result


def annotate(discovery, snapshots, now):
    if not isinstance(discovery, dict) or discovery.get("schema") != "LUCA_V03_AUTODISCOVERY_RESEARCH_V1":
        raise ValueError("INVALID_DISCOVERY")
    if discovery.get("discovery_status") != "COLLECTED_UNVERIFIED":
        raise ValueError("DISCOVERY_NOT_READY")
    if discovery.get("validation_status") != "NOT_VALIDATED" or discovery.get("real_trades_allowed") is not False:
        raise ValueError("UNSAFE_DISCOVERY")
    candidates = discovery.get("candidates")
    if not isinstance(candidates, list) or not 0 < len(candidates) <= MAX_UNIVERSE:
        raise ValueError("INVALID_CANDIDATES")
    if not isinstance(snapshots, dict) or not isinstance(now, dt.datetime) or now.tzinfo is None:
        raise ValueError("INVALID_SNAPSHOT_INPUT")
    symbols = [x.get("symbol") for x in candidates if isinstance(x, dict)]
    if len(symbols) != len(candidates) or len(set(symbols)) != len(symbols) or any(not valid_symbol(s) for s in symbols):
        raise ValueError("INVALID_CANDIDATE_SYMBOLS")
    if not set(snapshots).issubset(set(symbols)):
        raise ValueError("SNAPSHOT_SYMBOL_NOT_IN_UNIVERSE")
    rows = []
    for c in candidates:
        sym = c["symbol"]
        snap = snapshots.get(sym) or {}
        trade = snap.get("latestTrade") or {}
        quote = snap.get("latestQuote") or {}
        price = trade.get("p")
        ts = parse_time(trade.get("t"))
        age = (now.astimezone(UTC)-ts).total_seconds() if ts else None
        fresh = age is not None and 0 <= age <= MAX_AGE_SECONDS
        # IEX quote is not the full-market NBBO. Keep quote data separate.
        bid, ask = quote.get("bp"), quote.get("ap")
        quote_ts = parse_time(quote.get("t"))
        quote_age = (now.astimezone(UTC)-quote_ts).total_seconds() if quote_ts else None
        quote_fresh = quote_age is not None and 0 <= quote_age <= MAX_AGE_SECONDS
        spread = None
        if (quote_fresh and valid_price(bid) and valid_price(ask) and ask >= bid):
            spread = round(100*(ask-bid)/((ask+bid)/2), 3)
        band = valid_price(price) and MIN_PRICE <= price <= MAX_PRICE
        live = regular_session(now) and fresh and quote_fresh and band
        rows.append({
            "symbol": sym, "screener_groups": c.get("source_groups", {}),
            "iex_last_trade_price": price if valid_price(price) else None,
            "iex_last_trade_utc": ts.isoformat() if ts else None,
            "iex_last_trade_age_seconds": round(age) if age is not None else None,
            "iex_quote_spread_pct": spread,
            "price_band_0_20_to_20": bool(band),
            "research_status": "WATCH_ONLY_FRESH_IEX" if live else "PENDING_STALE_OR_MISSING",
            "market_cap": None, "float_shares": None, "full_market_quote_verified": False,
            "sec_verified": False, "buy_allowed": False,
        })
    return {
        "schema": "LUCA_V03_IEX_CANDIDATE_ENRICHMENT_V1",
        "collected_at_utc": now.astimezone(UTC).isoformat(),
        "discovered_count": len(candidates),
        "snapshots_present": sum(bool(snapshots.get(x)) for x in symbols),
        "priced_count": sum(x["iex_last_trade_price"] is not None for x in rows),
        "price_band_count": sum(x["price_band_0_20_to_20"] for x in rows),
        "fresh_iex_watch_count": sum(x["research_status"]=="WATCH_ONLY_FRESH_IEX" for x in rows),
        "source": "ALPACA_IEX_SINGLE_EXCHANGE_NOT_SIP",
        "early_spike_predicted": False, "market_cap_verified": False, "float_verified": False,
        "no_manual_tickers": True, "sec_status": "SEC_UNVERIFIED",
        "validation_status": "NOT_VALIDATED", "real_trades_allowed": False,
        "rows": rows,
        "warning": "Price is not market cap; IEX is not all-market; stale prints not live signals.",
    }


def run(key, secret, opener=None, now=None):
    now = now or dt.datetime.now(UTC)
    discovery = collect(key, secret, opener=opener, now=now)
    if discovery.get("discovery_status") != "COLLECTED_UNVERIFIED":
        return {"status":"DISCOVERY_UNAVAILABLE","details":discovery,"validation_status":"NOT_VALIDATED",
                "real_trades_allowed":False}
    symbols = [c["symbol"] for c in discovery["candidates"]]
    snapshots = {}
    batches = []
    for i in range(0,len(symbols),BATCH_SIZE):
        batch = symbols[i:i+BATCH_SIZE]
        try:
            result = fetch_iex_snapshots(batch,key,secret,opener)
            snapshots.update(result)
            batches.append({"size":len(batch),"status":"OK","returned":len(result)})
        except urllib.error.HTTPError as e:
            batches.append({"size":len(batch),"status":"HTTP_"+str(e.code),"returned":0})
        except Exception as e:
            batches.append({"size":len(batch),"status":"FAILED_"+type(e).__name__,"returned":0})
    if any(x["status"]!="OK" for x in batches):
        return {"status":"SNAPSHOTS_UNAVAILABLE","discovered_count":len(symbols),
                "batches":batches,"validation_status":"NOT_VALIDATED",
                "real_trades_allowed":False,"rows":[]}
    out=annotate(discovery,snapshots,now)
    out["status"]="COLLECTED_UNVERIFIED"
    out["batches"]=batches
    return out


def main():
    key,secret=os.getenv("ALPACA_KEY",""),os.getenv("ALPACA_SECRET","")
    if not key or not secret:
        print("RESULT: NO_KEYS; NOT_VALIDATED")
        raise SystemExit(2)
    result=run(key,secret)
    folder=Path(os.getenv("LUCA_ENRICH_OUTPUT","luca_v03_enrichment"))
    folder.mkdir(parents=True,exist_ok=True)
    file=folder/"enrichment.json"
    if file.exists():
        raise FileExistsError("NO_OVERWRITE")
    file.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print("RESULT: ENRICHMENT_"+result["status"]+
          "; DISCOVERED="+str(result.get("discovered_count",0))+
          "; IEX_PRICED="+str(result.get("priced_count",0))+
          "; PRICE_BAND="+str(result.get("price_band_count",0))+
          "; FRESH_IEX="+str(result.get("fresh_iex_watch_count",0))+
          "; NOT_VALIDATED; NO_ORDERS")
    if result["status"]!="COLLECTED_UNVERIFIED":
        raise SystemExit(3)


if __name__=="__main__":
    main()
