#!/usr/bin/env python3
"""Rotating NASDAQ-listed research sampler and SEC filing metadata. NO_ORDERS."""
import csv,datetime as dt,io,json,os,re,time,urllib.request
from pathlib import Path
NASDAQ_URL="https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
SEC_TICKERS="https://www.sec.gov/files/company_tickers.json"
FORMS={"8-K","10-Q","10-K","S-1","S-3","424B5","424B3","424B2","6-K","F-1","F-3","POS AM","EFFECT","DEF 14A"}
def get(url,ua):
 if not ua or "@" not in ua or "example.invalid" in ua:raise ValueError("Set LUCA_USER_AGENT with genuine contact email")
 req=urllib.request.Request(url,headers={"User-Agent":ua,"Accept":"application/json,text/plain,text/csv"})
 with urllib.request.urlopen(req,timeout=20) as response:raw=response.read(5000001)
 if len(raw)>5000000:raise ValueError("oversized response")
 return raw
def parse_symbols(raw):
 rows=csv.DictReader(raw.decode("utf-8-sig").splitlines(),delimiter="|")
 out=[]
 for r in rows:
  s=(r.get("Symbol") or "").strip();name=(r.get("Security Name") or "").lower()
  if not re.fullmatch("[A-Z]{1,5}",s) or r.get("ETF")!="N" or r.get("Test Issue")!="N" or r.get("NextShares")=="Y":continue
  if any(x in name for x in ("warrant","rights","unit ","preferred","depositary share","etf","exchange traded")):continue
  out.append(s)
 return sorted(set(out))
def ticker_map(raw):
 return {str(v["ticker"]).upper():int(v["cik_str"]) for v in json.loads(raw).values() if "ticker" in v and "cik_str" in v}
def parse_recent(raw,cik,asof):
 recent=json.loads(raw).get("filings",{}).get("recent",{});out=[]
 for form,date,accession,doc in zip(recent.get("form",[]),recent.get("filingDate",[]),recent.get("accessionNumber",[]),recent.get("primaryDocument",[])):
  if form not in FORMS:continue
  try:age=(asof-dt.date.fromisoformat(date)).days
  except ValueError:continue
  if not 0<=age<=120:continue
  acc=accession.replace("-","")
  if not re.fullmatch("[0-9]{18}",acc) or not re.fullmatch("[A-Za-z0-9_.-]+",doc):continue
  out.append({"form":form,"filing_date":date,"url":f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"})
  if len(out)>=8:break
 return out
def sample(symbols,day,limit):
 if not symbols:return []
 start=(day.toordinal()*limit)%len(symbols)
 return [symbols[(start+i)%len(symbols)] for i in range(min(limit,len(symbols)))]
def run():
 ua=os.environ.get("LUCA_USER_AGENT","");today=dt.datetime.now(dt.timezone.utc).date()
 symbols=parse_symbols(get(NASDAQ_URL,ua))
 if len(symbols)<1000:raise ValueError("Unexpectedly small NASDAQ universe")
 mapping=ticker_map(get(SEC_TICKERS,ua))
 limit=min(120,max(1,int(os.environ.get("LUCA_BATCH_SIZE","40"))))
 selected=sample(symbols,today,limit);rows=[];errors={}
 for ticker in selected:
  cik=mapping.get(ticker);filings=[];status="CIK_NOT_MAPPED"
  if cik is not None:
   try:
    raw=get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json",ua)
    filings=parse_recent(raw,cik,today);status="RECENT_FORMS_FETCHED"
   except Exception as e:status="FETCH_FAILED";errors[ticker]=type(e).__name__
   time.sleep(.15)
  rows.append({"ticker":ticker,"cik":cik,"sec_recent_status":status,"filings":filings,"sec_contract_terms_verified":False})
 out={"generated_at":dt.datetime.now(dt.timezone.utc).isoformat(),"date":str(today),"universe_size":len(symbols),"sample_size":len(selected),"coverage":"ROTATING_PARTIAL_SAMPLE","sec_scope":"RECENT_FORM_METADATA_ONLY","float_verified":False,"sec_contract_terms_verified":False,"orders_enabled":False,"validated":False,"rows":rows,"failures":errors}
 p=Path("site_data/universe_sample.json");p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print("NASDAQ sample",len(rows),"of",len(symbols),"SEC errors",len(errors))
if __name__=="__main__":run()
