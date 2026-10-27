"""LUCA V0.3 prospectively time-locked IEX observation (research only).

Two phases in ONE manually dispatched job:
(1) collect screener/IEX snapshot and write immutable selection at observation t0;
(2) only after the clock advances, fetch completed IEX 1m bars STARTING AFTER t0.
Never include bars preceding ticker selection. No scheduling, orders, deployment,
SEC safety approval, performance claim or A/B trading grade.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from auto_enrich_iex import run as enrich_run
from iex_1min_research import valid_bar, find_patterns

UTC=dt.timezone.utc
NY=ZoneInfo("America/New_York")
BARS_URL="https://data.alpaca.markets/v2/stocks/bars"
MAX_NAMES=12
MIN_ELAPSED=dt.timedelta(minutes=13)
MAX_ELAPSED=dt.timedelta(minutes=35)
LAG=dt.timedelta(minutes=2)  # Never use a bar until >=2 min after its start
MAX_PAGES=6


def as_utc(value):
    if not isinstance(value,dt.datetime) or value.tzinfo is None:
        raise ValueError("AWARE_DATETIME_REQUIRED")
    return value.astimezone(UTC)


def ny_window(now):
    """Conservative trial window 09:40-11:45 ET, not NYSE holiday verified."""
    x=as_utc(now).astimezone(NY)
    return x.weekday()<5 and (9,40)<=(x.hour,x.minute)<(11,45)


def next_bar_start(t):
    # Strictly later than t0, even when t0 happens to be xx:xx:00 exactly.
    x=as_utc(t)
    return x.replace(second=0,microsecond=0)+dt.timedelta(minutes=1)


def digest_frozen(doc):
    data={k:v for k,v in doc.items() if k!="sha256"}
    return hashlib.sha256(json.dumps(data,sort_keys=True,
                                      ensure_ascii=False,separators=(",",":")).encode()).hexdigest()


def freeze(enrichment,t0):
    t0=as_utc(t0)
    if not ny_window(t0):
        raise ValueError("OUTSIDE_RESEARCH_SESSION")
    if not isinstance(enrichment,dict) or enrichment.get("schema")!="LUCA_V03_IEX_CANDIDATE_ENRICHMENT_V1":
        raise ValueError("INVALID_ENRICHMENT")
    if enrichment.get("status")!="COLLECTED_UNVERIFIED" or enrichment.get("validation_status")!="NOT_VALIDATED" or enrichment.get("real_trades_allowed") is not False:
        raise ValueError("UNSAFE_ENRICHMENT")
    collected_at=dt.datetime.fromisoformat(enrichment.get("collected_at_utc"))
    if not collected_at.tzinfo or as_utc(collected_at)>t0:
        raise ValueError("FUTURE_SELECTION_TIMESTAMP")
    # Snapshot collection should be bounded and recent, else no t0 universe.
    if t0-as_utc(collected_at)>dt.timedelta(minutes=5):
        raise ValueError("STALE_DISCOVERY")
    selected=[]
    seen=set()
    for row in enrichment.get("rows",[]):
        if type(row) is not dict:
            raise ValueError("INVALID_CANDIDATE")
        symbol=row.get("symbol")
        if type(symbol) is not str or not symbol.isascii() or not symbol.replace(".","").replace("-","").isalnum() or not (1<=len(symbol)<=13) or symbol in seen:
            raise ValueError("INVALID_OR_DUPLICATE_SYMBOL")
        seen.add(symbol)
        if (row.get("price_band_0_20_to_20") is True and
            row.get("research_status")=="WATCH_ONLY_FRESH_IEX" and
            row.get("buy_allowed") is False):
            selected.append(symbol)
    result={
        "schema":"LUCA_V03_PROSPECTIVE_FREEZE_V1",
        "selected_at_utc":t0.isoformat(),
        "session_day_ny":t0.astimezone(NY).date().isoformat(),
        "universe_source":"ALPACA_SCREENER_PLUS_IEX_SNAPSHOTS_AT_T0",
        "candidates":selected[:MAX_NAMES],
        "candidate_count":len(selected[:MAX_NAMES]),
        "selection_cap":MAX_NAMES,
        "not_nyse_holiday_verified":True,
        "sec_status":"SEC_UNVERIFIED",
        "float_verified":False,
        "market_cap_verified":False,
        "historical_performance_verified":False,
        "validation_status":"NOT_VALIDATED",
        "real_trades_allowed":False,
    }
    result["sha256"]=digest_frozen(result)
    return result


def check_frozen(frozen,now):
    now=as_utc(now)
    if not isinstance(frozen,dict) or frozen.get("schema")!="LUCA_V03_PROSPECTIVE_FREEZE_V1":
        raise ValueError("BAD_FREEZE_SCHEMA")
    if frozen.get("sha256")!=digest_frozen(frozen):
        raise ValueError("FROZEN_HASH_MISMATCH")
    if frozen.get("validation_status")!="NOT_VALIDATED" or frozen.get("real_trades_allowed") is not False:
        raise ValueError("UNSAFE_FREEZE")
    t0=dt.datetime.fromisoformat(frozen["selected_at_utc"])
    t0=as_utc(t0)
    elapsed=now-t0
    if elapsed<MIN_ELAPSED or elapsed>MAX_ELAPSED:
        raise ValueError("WRONG_FORWARD_OBSERVATION_INTERVAL")
    if t0.astimezone(NY).date()!=now.astimezone(NY).date() or not ny_window(t0):
        raise ValueError("SESSION_DAY_MISMATCH")
    names=frozen.get("candidates")
    if type(names) is not list or len(names)>MAX_NAMES or len(names)!=len(set(names)) or len(names)!=frozen.get("candidate_count"):
        raise ValueError("INVALID_FROZEN_CANDIDATES")
    if any(type(x) is not str or not x.isascii() or not x.replace(".","").replace("-","").isalnum() or not 1<=len(x)<=13 for x in names):
        raise ValueError("INVALID_FROZEN_SYMBOL")
    start=next_bar_start(t0)
    # Strictly completed bar AND processing cushion.
    end=as_utc(now-LAG).replace(second=0,microsecond=0)
    if end<start:
        raise ValueError("NO_COMPLETED_BARS")
    if end.date()!=start.date():
        raise ValueError("CROSS_UTC_DAY_UNSUPPORTED")
    return names,start,end


def fetch_after_freeze(frozen,now,key,secret,opener=None):
    symbols,start,end=check_frozen(frozen,now)
    if not symbols:
        return {}
    if not key or not secret:
        raise ValueError("NO_API_KEYS")
    opened=opener or urllib.request.urlopen
    bars={s:[] for s in symbols}
    seen={s:set() for s in symbols}
    token=None
    tokens=set()
    for _ in range(MAX_PAGES):
        query={"symbols":",".join(symbols),"timeframe":"1Min",
               "start":start.isoformat().replace("+00:00","Z"),
               "end":end.isoformat().replace("+00:00","Z"),
               "feed":"iex","adjustment":"raw","sort":"asc","limit":10000}
        if token:
            query["page_token"]=token
        req=urllib.request.Request(BARS_URL+"?"+urllib.parse.urlencode(query),
            headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
                     "Accept":"application/json","User-Agent":"LUCA-V03-RESEARCH-READONLY/0.3"},
            method="GET")
        with opened(req,timeout=30) as response:
            data=response.read(2_000_001)
        if len(data)>2_000_000:
            raise ValueError("BAR_RESPONSE_TOO_BIG")
        raw=json.loads(data)
        if type(raw) is not dict or type(raw.get("bars")) is not dict or not set(raw["bars"]).issubset(set(symbols)):
            raise ValueError("BAD_BARS_RESPONSE")
        for sym,items in raw["bars"].items():
            if type(items) is not list:
                raise ValueError("INVALID_BAR_LIST")
            for x in items:
                item=valid_bar(x,start,end)
                if item["t"] in seen[sym]:
                    raise ValueError("DUPLICATE_BAR")
                seen[sym].add(item["t"])
                bars[sym].append(item)
        nxt=raw.get("next_page_token")
        if nxt is None:
            return {s:sorted(items,key=lambda x:x["t"]) for s,items in bars.items()}
        if type(nxt) is not str or not nxt or nxt in tokens:
            raise ValueError("BAD_PAGINATION")
        tokens.add(nxt)
        token=nxt
    raise ValueError("PAGE_CAP_EXCEEDED")


def review(frozen,bars,now):
    names,start,end=check_frozen(frozen,now)
    if set(bars)!=set(names):
        raise ValueError("FROZEN_UNIVERSE_DRIFT")
    results=[]
    for sym in names:
        items=bars[sym]
        # Re-validate every bar when the data comes from an external file.
        clean=[valid_bar(x,start,end) for x in items]
        if len({x["t"] for x in clean})!=len(clean):
            raise ValueError("DUPLICATE_BAR")
        clean.sort(key=lambda x:x["t"])
        flags=find_patterns(clean)
        results.append({"symbol":sym,"observed_iex_bars":len(clean),
                        "pattern_count":len(flags),
                        "first_pattern":flags[0] if flags else None,
                        "grade":"D","buy_allowed":False,
                        "sec_status":"SEC_UNVERIFIED",
                        "market_cap_verified":False,"float_verified":False})
    return {
        "schema":"LUCA_V03_PROSPECTIVE_IEX_REVIEW_V1",
        "selected_at_utc":frozen["selected_at_utc"],
        "first_allowed_bar_start_utc":start.isoformat(),
        "last_allowed_bar_start_utc":end.isoformat(),
        "reviewed_at_utc":as_utc(now).isoformat(),
        "symbols":len(results),
        "observed_iex_bars":sum(x["observed_iex_bars"] for x in results),
        "forward_pattern_symbols":sum(x["pattern_count"]>0 for x in results),
        "results":results,
        "candidate_selection_before_bars":True,
        "no_frozen_universe_leakage":True,
        "feed":"IEX_SINGLE_EXCHANGE_NOT_SIP",
        "not_nyse_holiday_verified":True,
        "sec_status":"SEC_UNVERIFIED",
        "prediction_accuracy_verified":False,
        "future_5_15_30_60_outcomes_measured":False,
        "live_profit_claim_allowed":False,
        "validation_status":"NOT_VALIDATED","real_trades_allowed":False,
        "warning":"Forward IEX research observation only, not prediction hit rate, full US stock market, or buy signal.",
    }


def write_json_new(dest,obj):
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open("x",encoding="utf8") as output:
        json.dump(obj,output,ensure_ascii=False,indent=2)
        output.write("\n")


def run_freeze_phase():
    dest=Path(os.environ.get("LUCA_FREEZE_DIR","luca_v03_forward"))
    now=dt.datetime.now(UTC)
    if not ny_window(now):
        result={"status":"OUTSIDE_RESEARCH_SESSION","checked_at_utc":now.isoformat(),
                "validation_status":"NOT_VALIDATED","real_trades_allowed":False}
        write_json_new(dest/"session_status.json",result)
        print("PROSPECTIVE_GATE: OUTSIDE_US_MORNING_SESSION; NO_DISCOVERY; NO_ORDERS")
        raise SystemExit(4)
    key,secret=os.getenv("ALPACA_KEY",""),os.getenv("ALPACA_SECRET","")
    if not key or not secret:
        raise SystemExit("NO_KEYS")
    enrich=enrich_run(key,secret)
    if enrich.get("status")!="COLLECTED_UNVERIFIED":
        write_json_new(dest/"session_status.json",{
            "status":"ENRICHMENT_UNAVAILABLE","validation_status":"NOT_VALIDATED",
            "real_trades_allowed":False})
        raise SystemExit(5)
    # IMPORTANT: t0 is AFTER all screener and snapshot calls have completed.
    t0=dt.datetime.now(UTC)
    if not ny_window(t0):
        raise SystemExit("SESSION_EXPIRED_DURING_SELECTION")
    frozen=freeze(enrich,t0)
    write_json_new(dest/"frozen_t0.json",frozen)
    print(f"PROSPECTIVE_FREEZE: CANDIDATES={frozen['candidate_count']}; "
          f"T0_UTC={frozen['selected_at_utc']}; "
          "NOT_VALIDATED; NO_ORDERS")


def run_review_phase():
    dest=Path(os.environ.get("LUCA_FREEZE_DIR","luca_v03_forward"))
    frozen=json.loads((dest/"frozen_t0.json").read_text(encoding="utf8"))
    now=dt.datetime.now(UTC)
    names,start,end=check_frozen(frozen,now)
    if not names:
        result=review(frozen,{},now)
    else:
        key,secret=os.getenv("ALPACA_KEY",""),os.getenv("ALPACA_SECRET","")
        if not key or not secret:
            raise SystemExit("NO_KEYS")
        bars=fetch_after_freeze(frozen,now,key,secret)
        result=review(frozen,bars,now)
    write_json_new(dest/"forward_review.json",result)
    print(f"PROSPECTIVE_REVIEW: SYMBOLS={result['symbols']}; "
          f"BARS={result['observed_iex_bars']}; "
          f"PATTERN_SYMBOLS={result['forward_pattern_symbols']}; "
          "SEC_UNVERIFIED; NOT_VALIDATED; NO_ORDERS")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--phase",choices=("freeze","review"),required=True)
    args=p.parse_args()
    if args.phase=="freeze":
        run_freeze_phase()
    else:
        run_review_phase()


if __name__=="__main__":
    main()
