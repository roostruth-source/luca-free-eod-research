"""One-off read-only market data preflight for the scheduled prospective study.

This is NOT the live T0 trial. It verifies API key availability, screener access,
IEX snapshot access, and 1m IEX bar read entitlement using an automatically
discovered ticker. No stock purchase, no candidate approval, no deployment.
"""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from auto_discover import collect
from auto_enrich_iex import fetch_iex_snapshots
from prospective_iex_research import ny_window

UTC=dt.timezone.utc
BARS_URL="https://data.alpaca.markets/v2/stocks/bars"


def bars_access(symbol,key,secret,now,opener=None):
    # An entitlement/schema probe using past, completed bars, NOT forward data.
    if not isinstance(symbol,str) or not symbol.isascii() or not symbol.replace(".","").replace("-","").isalnum():
        raise ValueError("BAD_SYMBOL")
    if not key or not secret:
        raise ValueError("NO_KEYS")
    day=now.astimezone(UTC).date()-dt.timedelta(days=1)
    start=dt.datetime.combine(day,dt.time(13,30),UTC)
    end=start+dt.timedelta(minutes=4)
    params={"symbols":symbol,"timeframe":"1Min","start":start.isoformat().replace("+00:00","Z"),
            "end":end.isoformat().replace("+00:00","Z"),"feed":"iex","adjustment":"raw","limit":10}
    req=urllib.request.Request(BARS_URL+"?"+urllib.parse.urlencode(params),method="GET",
        headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
                 "Accept":"application/json","User-Agent":"LUCA-V03-RESEARCH-PREFLIGHT-GET-ONLY"})
    with (opener or urllib.request.urlopen)(req,timeout=25) as response:
        raw=response.read(200_001)
    if len(raw)>200_000:
        raise ValueError("BAR_RESPONSE_TOO_LARGE")
    payload=json.loads(raw)
    if type(payload) is not dict or type(payload.get("bars")) is not dict:
        raise ValueError("BAD_BAR_SCHEMA")
    if not set(payload["bars"]).issubset({symbol}):
        raise ValueError("UNEXPECTED_SYMBOL")
    return {"status":"GET_OK_SCHEMA_ONLY","bars_returned":len(payload["bars"].get(symbol,[])),
            "historical_bars_not_prospective":True}


def audit(key,secret,now,discover_fn=collect,snapshot_fn=fetch_iex_snapshots,bars_fn=bars_access):
    if not isinstance(now,dt.datetime) or now.tzinfo is None:
        raise ValueError("AWARE_TIME_REQUIRED")
    report={
        "schema":"LUCA_V03_DATA_ACCESS_PREFLIGHT_V1",
        "checked_at_utc":now.astimezone(UTC).isoformat(),
        "us_morning_research_window_now":ny_window(now),
        "api_keys_present":bool(key and secret),
        "screener_status":"NOT_TESTED",
        "iex_snapshot_status":"NOT_TESTED",
        "iex_1min_bars_status":"NOT_TESTED",
        "ready_for_later_t0":"UNCONFIRMED",
        "live_t0_test_executed":False,
        "actual_forward_results":0,
        "sec_status":"SEC_UNVERIFIED",
        "market_cap_verified":False,"float_verified":False,
        "validation_status":"NOT_VALIDATED","real_trades_allowed":False,
    }
    if not key or not secret:
        report["screener_status"]="NO_KEYS"
        return report
    try:
        discovered=discover_fn(key,secret,now=now)
        if discovered.get("discovery_status")!="COLLECTED_UNVERIFIED":
            report["screener_status"]="UNAVAILABLE"
            report["screener_sources"]=discovered.get("source_status",{})
            return report
        report["screener_status"]="GET_OK"
        report["screener_candidates"]=discovered["candidate_count"]
        # Symbol comes from the screener; not manually entered or cherry-picked.
        symbol=discovered["candidates"][0]["symbol"]
    except Exception as exc:
        report["screener_status"]="ERROR_"+type(exc).__name__
        return report
    try:
        snapshots=snapshot_fn([symbol],key,secret)
        if type(snapshots) is not dict or symbol not in snapshots:
            raise ValueError("MISSING_IEX_SNAPSHOT")
        report["iex_snapshot_status"]="GET_OK_SCHEMA_ONLY"
    except urllib.error.HTTPError as exc:
        report["iex_snapshot_status"]="HTTP_"+str(exc.code)
    except Exception as exc:
        report["iex_snapshot_status"]="ERROR_"+type(exc).__name__
    try:
        bars=bars_fn(symbol,key,secret,now)
        if bars.get("status")!="GET_OK_SCHEMA_ONLY":
            raise ValueError("BAD_BARS_PROBE")
        report["iex_1min_bars_status"]="GET_OK_SCHEMA_ONLY"
        report["historical_bars_returned"]=bars["bars_returned"]
    except urllib.error.HTTPError as exc:
        report["iex_1min_bars_status"]="HTTP_"+str(exc.code)
    except Exception as exc:
        report["iex_1min_bars_status"]="ERROR_"+type(exc).__name__
    if (report["screener_status"]=="GET_OK" and
        report["iex_snapshot_status"]=="GET_OK_SCHEMA_ONLY" and
        report["iex_1min_bars_status"]=="GET_OK_SCHEMA_ONLY"):
        report["ready_for_later_t0"]="DATA_ENDPOINTS_ACCESSIBLE_ONLY"
    return report


def main():
    now=dt.datetime.now(UTC)
    report=audit(os.environ.get("ALPACA_KEY",""),os.environ.get("ALPACA_SECRET",""),now)
    out=Path(os.environ.get("LUCA_PREFLIGHT_OUTPUT","luca_v03_preflight"))/"preflight.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print("PREFLIGHT; SCREENER="+report["screener_status"]+
          "; IEX_SNAPSHOT="+report["iex_snapshot_status"]+
          "; IEX_1MIN="+report["iex_1min_bars_status"]+
          "; READY="+report["ready_for_later_t0"]+
          "; NO_LIVE_T0; NOT_VALIDATED; NO_ORDERS")
    if report["ready_for_later_t0"]!="DATA_ENDPOINTS_ACCESSIBLE_ONLY":
        raise SystemExit(3)


if __name__=="__main__":
    main()
