"""Read-only SEC recent-filings triage for automatic IEX price-band watchlist.

This is NOT SEC clearance. Form type alone cannot prove or disprove dilution.
Use exact EDGAR acceptance timestamp <= observation time; fail closed otherwise.
No orders, no personal data, no user-entered symbols, no production changes.
"""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request

from auto_enrich_iex import run as enrich_run

UTC = dt.timezone.utc
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_ROOT = "https://data.sec.gov/submissions/"
MAX_SEC_SYMBOLS = 50
MAX_RECENT = 1000
MAX_RESPONSE = 4_000_000
LOOKBACK_DAYS = 30
# Review signals only: these forms are not proof of dilution or safety.
REVIEW_FORMS = {"8-K", "6-K", "S-3", "F-3", "S-1", "F-1", "EFFECT",
                "POS AM", "S-3ASR", "F-3ASR", "SC 13D", "SC 13D/A",
                "SC 13G", "SC 13G/A", "4", "424B1", "424B2",
                "424B3", "424B4", "424B5", "424B7", "424B8"}
USER_AGENT = "LUCA-Research/0.3 (read-only non-commercial; github.com/roostruth-source/luca-free-eod-research)"


def parse_accepted(s):
    if type(s) is not str:
        return None
    try:
        x=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
        return x.astimezone(UTC) if x.tzinfo is not None else None
    except ValueError:
        return None


def get_json(url, opener=None):
    if url != TICKERS_URL and not re.fullmatch(
        r"https://data\.sec\.gov/submissions/CIK\d{10}\.json",url):
        raise ValueError("SEC_URL_NOT_ALLOWLISTED")
    req=urllib.request.Request(url,headers={
        "User-Agent":USER_AGENT,"Accept":"application/json",
        "Accept-Encoding":"identity",
    },method="GET")
    with (opener or urllib.request.urlopen)(req,timeout=20) as resp:
        raw=resp.read(MAX_RESPONSE+1)
    if len(raw)>MAX_RESPONSE:
        raise ValueError("SEC_RESPONSE_TOO_LARGE")
    return json.loads(raw)


def ticker_cik_map(data):
    if type(data) is not dict or len(data)>30000:
        raise ValueError("INVALID_TICKER_MAP")
    result={}
    for v in data.values():
        if not isinstance(v,dict):
            continue
        sym=v.get("ticker"); cik=v.get("cik_str")
        if (type(sym) is str and re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,12}",sym)
                and type(cik) is int and 1<=cik<=9999999999):
            if sym in result and result[sym]!=cik:
                raise ValueError("AMBIGUOUS_CIK_MAPPING")
            result[sym]=cik
    if not result:
        raise ValueError("EMPTY_SEC_TICKER_MAP")
    return result


def recent_filings(data, asof):
    if not isinstance(asof,dt.datetime) or asof.tzinfo is None:
        raise ValueError("ASOF_TIMESTAMP_REQUIRED")
    if not isinstance(data,dict) or not isinstance(data.get("filings"),dict):
        raise ValueError("INVALID_SEC_SUBMISSIONS")
    recent=data["filings"].get("recent")
    if not isinstance(recent,dict):
        raise ValueError("MISSING_RECENT_FILINGS")
    keys=("form","accessionNumber","acceptanceDateTime","filingDate","primaryDocument")
    values=[recent.get(k) for k in keys]
    if any(not isinstance(v,list) for v in values):
        raise ValueError("MALFORMED_FILINGS")
    count=len(values[0])
    if count>MAX_RECENT or any(len(v)!=count for v in values):
        raise ValueError("FILINGS_LENGTH_MISMATCH")
    cik=data.get("cik")
    if type(cik) is not int or not 1<=cik<=9999999999:
        raise ValueError("INVALID_CIK")
    cutoff=asof.astimezone(UTC)-dt.timedelta(days=LOOKBACK_DAYS)
    filings=[]
    invalid_timestamps=0
    for i in range(count):
        form,accession,accepted,filing_day,primary=(v[i] for v in values)
        if type(form) is not str or type(accession) is not str:
            raise ValueError("INVALID_FORM_OR_ACCESSION")
        t=parse_accepted(accepted)
        if t is None:
            invalid_timestamps+=1
            continue
        if not cutoff<=t<=asof.astimezone(UTC):
            continue
        if form not in REVIEW_FORMS:
            continue
        if not re.fullmatch(r"\d{10}-\d{2}-\d{6}",accession):
            raise ValueError("INVALID_ACCESSION")
        if type(primary) is not str or not re.fullmatch(r"[A-Za-z0-9._-]{1,150}",primary):
            raise ValueError("INVALID_PRIMARY_DOCUMENT")
        if type(filing_day) is not str or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",filing_day):
            raise ValueError("INVALID_FILING_DATE")
        url=(f"https://www.sec.gov/Archives/edgar/data/{cik}/"
             f"{accession.replace('-','')}/{primary}")
        filings.append({"form":form,"accepted_at_utc":t.isoformat(),
                        "filing_date":filing_day,"url":url,
                        "interpretation":"REVIEW_REQUIRED_NOT_PROOF_OF_DILUTION"})
    return {"review_filings":sorted(filings,key=lambda x:x["accepted_at_utc"],reverse=True),
            "invalid_acceptance_timestamps":invalid_timestamps,
            "recent_filings_count":count,
            "older_archive_not_checked":True}


def triage(enrichment, ticker_map, submissions, asof):
    if not isinstance(enrichment,dict) or enrichment.get("schema")!="LUCA_V03_IEX_CANDIDATE_ENRICHMENT_V1":
        raise ValueError("WRONG_ENRICHMENT")
    if enrichment.get("validation_status")!="NOT_VALIDATED" or enrichment.get("real_trades_allowed") is not False:
        raise ValueError("UNSAFE_ENRICHMENT")
    if not isinstance(asof,dt.datetime) or asof.tzinfo is None:
        raise ValueError("ASOF_TIMESTAMP_REQUIRED")
    if parse_accepted(enrichment.get("collected_at_utc"))!=asof.astimezone(UTC):
        raise ValueError("ASOF_ENRICHMENT_MISMATCH")
    rows=enrichment.get("rows")
    if type(rows) is not list or len(rows)>140:
        raise ValueError("INVALID_ENRICHMENT_ROWS")
    if type(ticker_map) is not dict or type(submissions) is not dict:
        raise ValueError("INVALID_SEC_INPUT")
    result=[]
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or row.get("buy_allowed") is not False:
            raise ValueError("UNSAFE_CANDIDATE")
        symbol=row.get("symbol")
        if type(symbol) is not str or symbol in seen:
            raise ValueError("DUPLICATE_OR_INVALID_SYMBOL")
        seen.add(symbol)
        if row.get("price_band_0_20_to_20") is not True:
            continue
        cik=ticker_map.get(symbol)
        item={"symbol":symbol,"iex_price":row.get("iex_last_trade_price"),
              "iex_status":row.get("research_status"),
              "cik":cik,"market_cap":None,"float_shares":None,
              "sec_verified":False,"sec_clearance":False,
              "buy_allowed":False,"grade":"D",
              "review_filings":[]}
        if cik is None:
            item["sec_status"]="CIK_NOT_MAPPED"
        elif symbol not in submissions:
            item["sec_status"]="SEC_SUBMISSIONS_UNAVAILABLE"
        else:
            payload=submissions[symbol]
            try:
                if payload.get("cik")!=cik:
                    raise ValueError("CIK_MISMATCH")
                reviewed=recent_filings(payload,asof)
                item["review_filings"]=reviewed["review_filings"]
                item["invalid_acceptance_timestamps"]=reviewed["invalid_acceptance_timestamps"]
                item["sec_status"]=("RECENT_FILINGS_REQUIRE_REVIEW" if reviewed["review_filings"]
                                    else "NO_REVIEW_FORMS_IN_RECENT_LIST_NOT_CLEARED")
                if reviewed["invalid_acceptance_timestamps"]:
                    item["sec_status"]="SEC_TIMESTAMPS_INCOMPLETE"
            except (ValueError,TypeError,AttributeError):
                item["sec_status"]="SEC_DATA_INVALID"
        result.append(item)
    return {
        "schema":"LUCA_V03_SEC_AUTOTRIAGE_RESEARCH_V1",
        "asof_utc":asof.astimezone(UTC).isoformat(),
        "price_band_watchlist":len(result),
        "cik_mapped":sum(x["cik"] is not None for x in result),
        "submissions_available":sum(x["sec_status"] not in (
            "CIK_NOT_MAPPED","SEC_SUBMISSIONS_UNAVAILABLE","SEC_DATA_INVALID") for x in result),
        "recent_review_forms":sum(len(x["review_filings"]) for x in result),
        "rows":result,
        "sec_status":"PARTIAL_RECENT_FORM_TRIAGE_NOT_DILUTION_CLEARANCE",
        "market_cap_verified":False,"float_verified":False,
        "historical_asof_sec_verified":False,"real_trades_allowed":False,
        "validation_status":"NOT_VALIDATED",
        "warning":"30-day recent forms only. 8-K/6-K do not themselves prove dilution. "
                  "No filing-content, older-archive, float, cap or registration-effectiveness clearance.",
    }


def run(key,secret,opener=None,now=None):
    now=now or dt.datetime.now(UTC)
    enrich=enrich_run(key,secret,opener=opener,now=now)
    if enrich.get("status")!="COLLECTED_UNVERIFIED":
        return {"status":"ENRICHMENT_UNAVAILABLE","details":enrich,
                "validation_status":"NOT_VALIDATED","real_trades_allowed":False}
    watch=[x["symbol"] for x in enrich["rows"] if x["price_band_0_20_to_20"]]
    if len(watch)>MAX_SEC_SYMBOLS:
        return {"status":"WATCHLIST_CAP_EXCEEDED","watch_count":len(watch),
                "validation_status":"NOT_VALIDATED","real_trades_allowed":False}
    try:
        mapping=ticker_cik_map(get_json(TICKERS_URL,opener))
    except Exception as e:
        # Preserve the actual watchlist, but never pretend SEC risk was checked.
        error_type=("HTTP_"+str(e.code) if isinstance(e,urllib.error.HTTPError)
                    else type(e).__name__)
        return {
            "status":"SEC_TICKER_MAP_UNAVAILABLE",
            "error_type":error_type,
            "watch_count":len(watch),
            "rows":[{"symbol":x["symbol"],
                     "iex_price":x.get("iex_last_trade_price"),
                     "sec_status":"SEC_NOT_CHECKED_SOURCE_UNAVAILABLE",
                     "market_cap":None,"float_shares":None,
                     "grade":"D","buy_allowed":False}
                    for x in enrich["rows"] if x["price_band_0_20_to_20"]],
            "market_cap_verified":False,"float_verified":False,
            "validation_status":"NOT_VALIDATED","real_trades_allowed":False}
    subs={}
    errors={}
    for symbol in watch:
        cik=mapping.get(symbol)
        if cik is None:
            continue
        try:
            # Respect SEC public request guidance; 5 requests/second at most.
            time.sleep(0.22)
            subs[symbol]=get_json(SUBMISSIONS_ROOT+f"CIK{cik:010d}.json",opener)
        except urllib.error.HTTPError as e:
            errors[symbol]="HTTP_"+str(e.code)
            if e.code in (403,429):
                break
        except Exception as e:
            errors[symbol]=type(e).__name__
    out=triage(enrich,mapping,subs,now)
    out["status"]="COLLECTED_PARTIAL_NOT_CLEARED"
    out["sec_fetch_errors"]=errors
    out["sec_fetch_stopped_on_permission_or_rate_limit"]=any(
        x in ("HTTP_403","HTTP_429") for x in errors.values())
    return out


def main():
    key,secret=os.getenv("ALPACA_KEY",""),os.getenv("ALPACA_SECRET","")
    if not key or not secret:
        print("RESULT: NO_KEYS; NOT_VALIDATED")
        raise SystemExit(2)
    result=run(key,secret)
    folder=Path(os.getenv("LUCA_SEC_TRIAGE_OUTPUT","luca_v03_sec_triage"))
    folder.mkdir(parents=True,exist_ok=True)
    output=folder/"sec_triage.json"
    if output.exists():
        raise FileExistsError("NO_OVERWRITE")
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
    print("RESULT: SEC_TRIAGE_"+result["status"]+
          "; WATCH="+str(result.get("price_band_watchlist",result.get("watch_count",0)))+
          "; CIK="+str(result.get("cik_mapped",0))+
          "; SEC_SUBMISSIONS="+str(result.get("submissions_available",0))+
          "; REVIEW_FORMS="+str(result.get("recent_review_forms",0))+
          "; ERROR_TYPE="+str(result.get("error_type","NONE"))+
          "; NOT_VALIDATED; NO_ORDERS")
    if result["status"]!="COLLECTED_PARTIAL_NOT_CLEARED":
        raise SystemExit(3)


if __name__=="__main__":
    main()
