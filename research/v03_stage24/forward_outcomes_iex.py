"""Research-only post-signal 5/15/30/60 minute IEX evidence.

Operate ONLY on a genuine T0-frozen prospective IEX review. Report theoretical
IEX price changes, never realized returns, fill probability, or predictive
accuracy. No retries, no order endpoint, no interpolated sparse bars.
"""
from __future__ import annotations
import datetime as dt
import json
import math
import os
import pathlib
import urllib.parse
import urllib.request

from prospective_iex_research import as_utc, digest_frozen, next_bar_start
from iex_1min_research import valid_bar
from auto_discover import valid_symbol

UTC=dt.timezone.utc
HORIZONS=(5,15,30,60)
BARS_URL="https://data.alpaca.markets/v2/stocks/bars"
MAX_BYTES=2_000_000
MAX_PAGES=5
MAX_NAMES=12
CUSHION=dt.timedelta(minutes=2)


def parse_utc(value):
    if type(value) is not str:
        raise ValueError("NOT_STRING_TIMESTAMP")
    try:
        t=dt.datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as e:
        raise ValueError("INVALID_TIMESTAMP") from e
    return as_utc(t)


def validate_origins(frozen, review):
    if type(frozen) is not dict or frozen.get("schema")!="LUCA_V03_PROSPECTIVE_FREEZE_V1":
        raise ValueError("INVALID_FREEZE")
    if frozen.get("sha256")!=digest_frozen(frozen):
        raise ValueError("T0_HASH_MISMATCH")
    if frozen.get("real_trades_allowed") is not False or frozen.get("validation_status")!="NOT_VALIDATED":
        raise ValueError("UNSAFE_FREEZE")
    if type(review) is not dict or review.get("schema")!="LUCA_V03_PROSPECTIVE_IEX_REVIEW_V1":
        raise ValueError("NOT_PROSPECTIVE_REVIEW")
    if review.get("real_trades_allowed") is not False or review.get("validation_status")!="NOT_VALIDATED" or review.get("prediction_accuracy_verified") is not False:
        raise ValueError("UNSAFE_REVIEW")
    if review.get("feed")!="IEX_SINGLE_EXCHANGE_NOT_SIP" or review.get("candidate_selection_before_bars") is not True:
        raise ValueError("RETROSPECTIVE_OR_MIXED_FEED")
    if review.get("selected_at_utc")!=frozen.get("selected_at_utc"):
        raise ValueError("T0_REVIEW_MISMATCH")
    names=frozen.get("candidates")
    if type(names) is not list or not 0<len(names)<=MAX_NAMES or len(names)!=len(set(names)) or not all(valid_symbol(x) for x in names):
        raise ValueError("NO_VALID_FROZEN_UNIVERSE")
    rows=review.get("results")
    if type(rows) is not list or len(rows)!=len(names):
        raise ValueError("REVIEW_UNIVERSE_MISMATCH")
    if [x.get("symbol") for x in rows if isinstance(x,dict)]!=names:
        raise ValueError("REVIEW_SYMBOLS_DRIFT")
    t0=parse_utc(frozen["selected_at_utc"])
    reviewed=parse_utc(review["reviewed_at_utc"])
    if reviewed<t0+dt.timedelta(minutes=13) or reviewed>t0+dt.timedelta(minutes=35):
        raise ValueError("INVALID_REVIEW_TIME")
    start=parse_utc(review["first_allowed_bar_start_utc"])
    if start!=next_bar_start(t0):
        raise ValueError("BAR_START_BEFORE_SELECTION")
    last=parse_utc(review["last_allowed_bar_start_utc"])
    if last>reviewed-dt.timedelta(minutes=2) or last<start:
        raise ValueError("UNCLOSED_OR_INVALID_REVIEW_WINDOW")
    known={}
    for row in rows:
        if row.get("buy_allowed") is not False or row.get("grade")!="D":
            raise ValueError("UNSAFE_RESEARCH_GRADE")
        count=row.get("pattern_count")
        if type(count) is not int or count<0:
            raise ValueError("BAD_PATTERN_COUNT")
        first=row.get("first_pattern")
        if count==0:
            if first is not None:
                raise ValueError("PATTERN_COUNT_MISMATCH")
            continue
        if type(first) is not dict or first.get("research_pattern_only") is not True or first.get("buy_allowed") is not False:
            raise ValueError("BAD_RESEARCH_SIGNAL")
        signal=parse_utc(first["signal_bar_start_utc"])
        entry=parse_utc(first["bar_knowable_after_utc"])
        if entry!=signal+dt.timedelta(minutes=1) or signal<start or signal>last or entry>reviewed:
            raise ValueError("FUTURE_OR_PRE_T0_SIGNAL")
        known[row["symbol"]]=entry
    return t0,reviewed,known


def evaluation_window(entries):
    if not entries:
        return None
    return min(entries.values()),max(t+dt.timedelta(minutes=59) for t in entries.values())


def fetch_forward_bars(entries,now,key,secret,opener=None):
    now=as_utc(now)
    if not entries:
        return {}
    if len(entries)>MAX_NAMES or len(set(entries))!=len(entries) or not all(valid_symbol(x) for x in entries):
        raise ValueError("BAD_SIGNAL_SYMBOLS")
    if not key or not secret:
        raise ValueError("MISSING_MARKET_KEYS")
    start,end=evaluation_window(entries)
    # The entire max horizon must have closed plus cushion; never partially fetch
    # and accidentally treat missing FUTURE data as a price failure.
    if now<end+dt.timedelta(minutes=1)+CUSHION:
        raise ValueError("OUTCOMES_NOT_YET_COMPLETED")
    if end.date()!=start.date():
        raise ValueError("CROSS_UTC_DAY_UNSUPPORTED")
    opener=opener or urllib.request.urlopen
    rows={s:[] for s in entries}
    seen={s:set() for s in entries}
    token=None
    used=set()
    for _ in range(MAX_PAGES):
        params={"symbols":",".join(entries),"timeframe":"1Min",
                "start":start.isoformat().replace("+00:00","Z"),
                "end":end.isoformat().replace("+00:00","Z"),
                "feed":"iex","adjustment":"raw","sort":"asc","limit":10000}
        if token:
            params["page_token"]=token
        req=urllib.request.Request(BARS_URL+"?"+urllib.parse.urlencode(params),
            headers={"APCA-API-KEY-ID":key,"APCA-API-SECRET-KEY":secret,
                     "Accept":"application/json","User-Agent":"LUCA-V03-RESEARCH-READONLY/0.3"},
            method="GET")
        with opener(req,timeout=30) as response:
            raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise ValueError("MARKET_RESPONSE_TOO_LARGE")
        obj=json.loads(raw)
        if type(obj) is not dict or type(obj.get("bars")) is not dict or not set(obj["bars"]).issubset(entries):
            raise ValueError("INVALID_MARKET_RESPONSE")
        for sym,items in obj["bars"].items():
            if type(items) is not list:
                raise ValueError("INVALID_MARKET_BARS")
            for rawbar in items:
                bar=valid_bar(rawbar,start,end)
                if bar["t"] in seen[sym]:
                    raise ValueError("DUPLICATE_MARKET_BAR")
                seen[sym].add(bar["t"])
                rows[sym].append(bar)
        nxt=obj.get("next_page_token")
        if nxt is None:
            return {s:sorted(data,key=lambda x:x["t"]) for s,data in rows.items()}
        if type(nxt) is not str or not nxt or nxt in used:
            raise ValueError("INVALID_PAGINATION")
        used.add(nxt)
        token=nxt
    raise ValueError("PAGINATION_LIMIT")


def horizon_result(items,entry,minutes):
    # Exactly N contiguous IEX 1m bars from the first bar knowable at entry.
    # Entry is next-bar OPEN (hypothetical); exit Nth bar CLOSE (hypothetical).
    data={}
    for item in items:
        t=parse_utc(item["t"])
        if t in data:
            raise ValueError("DUPLICATE_TIME")
        data[t]=item
    grid=[entry+dt.timedelta(minutes=k) for k in range(minutes)]
    if not all(t in data for t in grid):
        return {"horizon_minutes":minutes,"status":"MISSING_IEX_MINUTES",
                "theoretical_iex_open_to_close_pct":None,
                "expected_bars":minutes,"observed_bars":sum(t in data for t in grid)}
    open_price=data[grid[0]]["o"]
    close=data[grid[-1]]["c"]
    if not all(type(x) in (int,float) and math.isfinite(x) and x>0 for x in (open_price,close)):
        raise ValueError("BAD_PRICE")
    pct=100*(close/open_price-1)
    return {"horizon_minutes":minutes,"status":"COMPLETE_IEX_PRICES_ONLY",
            "theoretical_iex_open_to_close_pct":round(pct,4),
            "entry_iex_next_bar_open":open_price,
            "exit_iex_nth_bar_close":close,
            "expected_bars":minutes,"observed_bars":minutes,
            "real_fill_verified":False,"slippage_and_spread_included":False}


def build_report(frozen,review,bars,now):
    t0,reviewed,entries=validate_origins(frozen,review)
    now=as_utc(now)
    if not entries:
        raise ValueError("NO_FROZEN_SIGNALS")
    start,end=evaluation_window(entries)
    if now<end+dt.timedelta(minutes=1)+CUSHION:
        raise ValueError("FUTURE_OUTCOMES_NOT_READY")
    if type(bars) is not dict or set(bars)!=set(entries):
        raise ValueError("OUTCOME_UNIVERSE_MISMATCH")
    details=[]
    for sym,entry in entries.items():
        items=bars[sym]
        if type(items) is not list:
            raise ValueError("BAD_BARS")
        # Re-validate potentially external imported data with exact per-signal bounds.
        per_end=entry+dt.timedelta(minutes=59)
        cleaned=[valid_bar(x,entry,per_end) for x in items
                 if entry<=parse_utc(x.get("t"))<=per_end]
        if len(cleaned)!=len({x["t"] for x in cleaned}):
            raise ValueError("DUPLICATE_IEX_MINUTE")
        measures=[horizon_result(cleaned,entry,n) for n in HORIZONS]
        details.append({"symbol":sym,"known_at_utc":entry.isoformat(),
                        "horizons":measures,"grade":"D",
                        "sec_status":"SEC_UNVERIFIED","buy_allowed":False})
    return {
        "schema":"LUCA_V03_PROSPECTIVE_IEX_OUTCOMES_V1",
        "frozen_t0_sha256":frozen["sha256"],
        "frozen_at_utc":t0.isoformat(),
        "initial_reviewed_at_utc":reviewed.isoformat(),
        "outcomes_checked_at_utc":now.isoformat(),
        "horizon_minutes":list(HORIZONS),
        "evaluated_signals":len(details),
        "complete_horizons":sum(m["status"]=="COMPLETE_IEX_PRICES_ONLY"
                                for x in details for m in x["horizons"]),
        "signals":details,
        "measurement":"HYPOTHETICAL_IEX_NEXT_MINUTE_OPEN_TO_HORIZON_CLOSE",
        "same_exchange_limit":"IEX_ONLY_NOT_CONSOLIDATED_SIP",
        "not_real_fills":True,"fees_slippage_or_spread_included":False,
        "historical_accuracy_verified":False,"market_cap_verified":False,
        "float_verified":False,"sec_status":"SEC_UNVERIFIED",
        "validation_status":"NOT_VALIDATED","real_trades_allowed":False,
        "warning":"No claim of executable profits or predictive hit rate. Missing IEX minutes yield no result.",
    }


def run():
    folder=pathlib.Path(os.getenv("LUCA_FOLLOWUP_INPUT","luca_v03_forward"))
    output=pathlib.Path(os.getenv("LUCA_FOLLOWUP_OUTPUT","luca_v03_followup"))
    frozen=json.loads((folder/"frozen_t0.json").read_text(encoding="utf8"))
    review=json.loads((folder/"forward_review.json").read_text(encoding="utf8"))
    _t0,_reviewed,entries=validate_origins(frozen,review)
    now=dt.datetime.now(UTC)
    if not entries:
        print("NO_FROZEN_SIGNALS; NOT_VALIDATED; NO_ORDERS")
        raise SystemExit(4)
    start,end=evaluation_window(entries)
    if now<end+dt.timedelta(minutes=1)+CUSHION:
        print("FUTURE_OUTCOMES_NOT_READY; NOT_VALIDATED; NO_ORDERS")
        raise SystemExit(5)
    key,secret=os.getenv("ALPACA_KEY",""),os.getenv("ALPACA_SECRET","")
    data=fetch_forward_bars(entries,now,key,secret)
    result=build_report(frozen,review,data,now)
    output.mkdir(parents=True,exist_ok=True)
    with (output/"outcomes.json").open("x",encoding="utf8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print(f"PROSPECTIVE_OUTCOMES: SIGNALS={result['evaluated_signals']}; "
          f"HORIZONS_COMPLETE={result['complete_horizons']}; "
          "NOT_VALIDATED; NO_ORDERS; NOT_REAL_PROFITS")


if __name__=="__main__":
    run()
