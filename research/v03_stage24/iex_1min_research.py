"""LUCA research: automatically discovered symbols -> historical IEX one-minute bars.

DO NOT interpret retrospective flags as live-predicted early spikes:
the screener selected the symbols AFTER the historical bars. This is
universe lookahead (post-selection bias), irrespective of bar-level causality.
V0.2-style >=3x volume and 3 rising lows is an UNVALIDATED hypothesis.
Read-only GET, no orders, no scheduled live alerts or production writes.
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
from auto_enrich_iex import run as enrich_run
from auto_discover import valid_symbol

ET = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
BAR_URL = "https://data.alpaca.markets/v2/stocks/bars"
MAX_SYMBOLS = 12
MIN_CONTEXT = 6
MAX_PAGES = 5
MAX_BYTES = 2_000_000


def latest_completed_session_date(now):
    """Conservative previous regular session if today has not closed + one hour.

    US stock holidays are NOT verified; return the last *weekday* only, flag this
    limitation and reject an empty data session rather than fabricating bars.
    """
    if not isinstance(now, dt.datetime) or now.tzinfo is None:
        raise ValueError("AWARE_TIMESTAMP_REQUIRED")
    local=now.astimezone(ET)
    day=local.date() if (local.hour,local.minute)>=(17,0) else local.date()-dt.timedelta(days=1)
    while day.weekday()>=5:
        day-=dt.timedelta(days=1)
    return day


def session_window(day):
    if not isinstance(day, dt.date) or day.weekday()>=5:
        raise ValueError("INVALID_SESSION_DAY")
    # 180m regular session morning. No premarket mixing.
    begin=dt.datetime.combine(day,dt.time(9,30),tzinfo=ET).astimezone(UTC)
    end=dt.datetime.combine(day,dt.time(12,29),tzinfo=ET).astimezone(UTC)
    return begin,end


def valid_bar(raw,begin,end):
    if not isinstance(raw,dict):
        raise ValueError("BAD_BAR_OBJECT")
    stamp=raw.get("t")
    if not isinstance(stamp,str):
        raise ValueError("BAD_TIMESTAMP")
    try:
        t=dt.datetime.fromisoformat(stamp.replace("Z","+00:00"))
    except ValueError as e:
        raise ValueError("BAD_TIMESTAMP") from e
    if t.tzinfo is None:
        raise ValueError("NAIVE_BAR_TIMESTAMP")
    t=t.astimezone(UTC)
    if not begin<=t<=end or t.second!=0 or t.microsecond!=0:
        raise ValueError("BAR_OUTSIDE_WINDOW")
    v=[raw.get(x) for x in ("o","h","l","c")]
    volume=raw.get("v")
    if any(type(x) not in (int,float) or not math.isfinite(x) or x<=0 for x in v):
        raise ValueError("INVALID_OHLC")
    o,h,l,c=v
    if not (l<=min(o,c)<=max(o,c)<=h):
        raise ValueError("INVALID_OHLC_RANGE")
    if type(volume) is not int or volume<0:
        raise ValueError("INVALID_IEX_VOLUME")
    return {"t":t.isoformat(),"o":o,"h":h,"l":l,"c":c,"v":volume}


def fetch_iex_morning(symbols,day,key,secret,opener=None):
    if not (1<=len(symbols)<=MAX_SYMBOLS) or len(set(symbols))!=len(symbols) or not all(
            valid_symbol(s) for s in symbols):
        raise ValueError("INVALID_SYMBOL_BATCH")
    if not key or not secret:
        raise ValueError("MISSING_CREDENTIALS")
    begin,end=session_window(day)
    opener=opener or urllib.request.urlopen
    bars={s:[] for s in symbols}
    seen={s:set() for s in symbols}
    token=None
    tokens=set()
    for _ in range(MAX_PAGES):
        args={"symbols":",".join(symbols),"timeframe":"1Min",
              "start":begin.isoformat().replace("+00:00","Z"),
              "end":end.isoformat().replace("+00:00","Z"),
              "feed":"iex","adjustment":"raw","sort":"asc","limit":10000}
        if token is not None:
            args["page_token"]=token
        req=urllib.request.Request(BAR_URL+"?"+urllib.parse.urlencode(args),headers={
            "APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
            "Accept":"application/json","User-Agent":"LUCA-RESEARCH-GET-ONLY/0.3",
        },method="GET")
        with opener(req,timeout=30) as resp:
            raw=resp.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise ValueError("BAR_RESPONSE_TOO_LARGE")
        doc=json.loads(raw)
        if not isinstance(doc,dict) or not isinstance(doc.get("bars"),dict):
            raise ValueError("INVALID_RESPONSE")
        if not set(doc["bars"]).issubset(set(symbols)):
            raise ValueError("UNEXPECTED_SYMBOLS")
        for symbol,rows in doc["bars"].items():
            if not isinstance(rows,list):
                raise ValueError("INVALID_BAR_ARRAY")
            for rawbar in rows:
                bar=valid_bar(rawbar,begin,end)
                if bar["t"] in seen[symbol]:
                    raise ValueError("DUPLICATE_MINUTE")
                seen[symbol].add(bar["t"])
                bars[symbol].append(bar)
        nxt=doc.get("next_page_token")
        if nxt is None:
            return {symbol:sorted(rows,key=lambda x:x["t"]) for symbol,rows in bars.items()}
        if not isinstance(nxt,str) or not nxt or nxt in tokens:
            raise ValueError("INVALID_PAGINATION")
        tokens.add(nxt)
        token=nxt
    raise ValueError("PAGE_LIMIT_REACHED")


def find_patterns(rows):
    """Bar-by-bar as-if calculation, NOT a prospective prediction test.

    Observed close at t, knowable only at >= t+1 minute. Require 6 contiguous
    minutes; missing IEX minutes are NOT zero-filled or interpolated.
    """
    if not isinstance(rows,list):
        raise ValueError("INVALID_BAR_SERIES")
    signals=[]
    for i in range(MIN_CONTEXT-1,len(rows)):
        w=rows[i-MIN_CONTEXT+1:i+1]
        ts=[dt.datetime.fromisoformat(x["t"]) for x in w]
        if any((b-a)!=dt.timedelta(minutes=1) for a,b in zip(ts,ts[1:])):
            continue
        base=sum(x["v"] for x in w[:-1])/5
        if base<=0:
            continue
        ratio=w[-1]["v"]/base
        rising=w[-3]["l"]<w[-2]["l"]<w[-1]["l"]
        change=100*(w[-1]["c"]/w[0]["c"]-1)
        if ratio>=3 and w[-1]["v"]>=100 and rising and 0<=change<=15:
            known=ts[-1]+dt.timedelta(minutes=1)
            signals.append({
                "signal_bar_start_utc":ts[-1].isoformat(),
                "bar_knowable_after_utc":known.isoformat(),
                "prior_five_bar_mean_iex_volume":round(base,1),
                "last_bar_iex_volume":w[-1]["v"],
                "iex_volume_ratio":round(ratio,3),
                "three_rising_lows":True,
                "six_bar_price_change_pct":round(change,3),
                "research_pattern_only":True,
                "buy_allowed":False,
            })
    return signals


def report(enrichment,bars,day,now):
    if enrichment.get("schema")!="LUCA_V03_IEX_CANDIDATE_ENRICHMENT_V1" or (
        enrichment.get("validation_status")!="NOT_VALIDATED" or
        enrichment.get("real_trades_allowed") is not False):
        raise ValueError("UNSAFE_ENRICHMENT")
    session_start,session_end=session_window(day)
    if now.tzinfo is None or now.astimezone(UTC)<session_end+dt.timedelta(hours=1):
        raise ValueError("HISTORICAL_WINDOW_NOT_COMPLETED")
    candidates=[x["symbol"] for x in enrichment["rows"] if x["price_band_0_20_to_20"]][:MAX_SYMBOLS]
    if not candidates or set(bars)!=set(candidates):
        raise ValueError("BAR_UNIVERSE_MISMATCH")
    out=[]
    for symbol in candidates:
        rows=bars[symbol]
        patterns=find_patterns(rows)
        out.append({"symbol":symbol,"bar_count":len(rows),"missing_of_180":180-len(rows),
                    "pattern_count":len(patterns),"first_pattern":patterns[0] if patterns else None,
                    "data_quality":"SPARSE_IEX_NO_INTERPOLATION" if len(rows)<150 else "OBSERVED_IEX",
                    "grade":"D","buy_allowed":False,"sec_status":"SEC_UNVERIFIED",
                    "market_cap_verified":False,"float_verified":False})
    return {
        "schema":"LUCA_V03_RETROSPECTIVE_IEX_PATTERN_REPORT_V1",
        "research_day":day.isoformat(),
        "screened_at_utc":enrichment.get("collected_at_utc"),
        "requested_bar_window_utc":{"start":session_start.isoformat(),"end":session_end.isoformat()},
        "discovered_price_band":enrichment["price_band_count"],
        "studied_symbols":len(candidates),
        "observed_bars":sum(x["bar_count"] for x in out),
        "retrospective_pattern_symbols":sum(x["pattern_count"]>0 for x in out),
        "rows":out,
        "data_feed":"IEX_SINGLE_EXCHANGE_ONLY",
        "candidate_selection_after_bars":True,
        "lookahead_selection_bias":True,
        "not_valid_prospective_backtest":True,
        "not_live_scanning":True,"prediction_accuracy_verified":False,
        "sec_status":"SEC_UNVERIFIED","real_trades_allowed":False,
        "validation_status":"NOT_VALIDATED",
        "warning":"Candidates selected after historical bars. No predictive hit rate, returns or A/B grades may be inferred.",
    }


def run(key,secret,opener=None,now=None):
    now=now or dt.datetime.now(UTC)
    info=enrich_run(key,secret,opener=opener,now=now)
    if info.get("status")!="COLLECTED_UNVERIFIED":
        return {"status":"ENRICHMENT_UNAVAILABLE","details":info,
                "validation_status":"NOT_VALIDATED","real_trades_allowed":False}
    candidates=[x["symbol"] for x in info["rows"] if x["price_band_0_20_to_20"]][:MAX_SYMBOLS]
    if not candidates:
        return {"status":"NO_PRICE_BAND_CANDIDATES","validation_status":"NOT_VALIDATED",
                "real_trades_allowed":False}
    day=latest_completed_session_date(now)
    try:
        bars=fetch_iex_morning(candidates,day,key,secret,opener)
        result=report(info,bars,day,now)
        result["status"]="RETROSPECTIVE_RESEARCH_ONLY"
        return result
    except urllib.error.HTTPError as e:
        return {"status":"BAR_HTTP_"+str(e.code),"observed_bars":0,
                "studied_symbols":len(candidates),"validation_status":"NOT_VALIDATED",
                "real_trades_allowed":False}
    except Exception as e:
        return {"status":"BAR_ERROR_"+type(e).__name__,"observed_bars":0,
                "studied_symbols":len(candidates),"validation_status":"NOT_VALIDATED",
                "real_trades_allowed":False}


def main():
    key,secret=os.getenv("ALPACA_KEY",""),os.getenv("ALPACA_SECRET","")
    if not key or not secret:
        raise SystemExit("NO_KEYS; NOT_VALIDATED")
    result=run(key,secret)
    output=Path("luca_v03_iex_1min")
    output.mkdir(parents=True,exist_ok=True)
    file=output/"retrospective_iex_1min.json"
    if file.exists():
        raise FileExistsError("NO_OVERWRITE")
    file.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print("IEX_1MIN; STATUS="+result["status"]+
          "; STUDIED="+str(result.get("studied_symbols",0))+
          "; BARS="+str(result.get("observed_bars",0))+
          "; PATTERN_SYMBOLS="+str(result.get("retrospective_pattern_symbols",0))+
          "; NOT_VALIDATED; NO_ORDERS; NEVER_LIVE_PREDICTION")
    if result["status"]!="RETROSPECTIVE_RESEARCH_ONLY":
        raise SystemExit(3)


if __name__=="__main__":
    main()
