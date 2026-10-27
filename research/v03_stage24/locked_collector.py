"""LUCA Stage24 prospective date-only Alpaca SIP reader; GET only, no orders/GitHub."""
import datetime as dt
import hashlib
import json
import math
import pathlib
import urllib.request
import urllib.parse
import urllib.error
import uuid
import zipfile
from zoneinfo import ZoneInfo

START='2026-10-26'
END='2026-11-20'
SYMBOLS=('GPUS','LAES','PFSA','NIKI','VCIG','AAPL')
UTC=dt.timezone.utc
ET=ZoneInfo('America/New_York')
ALLOWED_DAYS=tuple((dt.date(2026,10,26)+dt.timedelta(days=i)).isoformat()
                  for i in range((dt.date(2026,11,20)-dt.date(2026,10,26)).days+1)
                  if (dt.date(2026,10,26)+dt.timedelta(days=i)).weekday()<5)
RULE_SHA='b8e0dd350daba7c9b1e6fa41fd3886ca32ea1395a785478257132310d08d8d1b'
HYPOTHESES_SHA='a30de65d7f5e561178ebe888c45d3f4fd6f51209dd5ab03ff1551bd7a9a7a5eb'  # replaced at build
HOST='https://data.alpaca.markets/v2/stocks/bars'

def window(day):
    d=dt.date.fromisoformat(day)
    if day not in ALLOWED_DAYS:raise ValueError('DATE_NOT_IN_LOCKED_FUTURE_SAMPLE')
    start=dt.datetime.combine(d,dt.time(9,30),tzinfo=ET).astimezone(UTC)
    last=dt.datetime.combine(d,dt.time(12,29),tzinfo=ET).astimezone(UTC)
    return start,last

def eligible_days(now=None):
    """SIP delayed feed: >= 30min after last requested 1m bar."""
    now=now or dt.datetime.now(UTC)
    if now.tzinfo is None: raise ValueError('UTC_AWARE_NOW_REQUIRED')
    return [day for day in ALLOWED_DAYS if now>=window(day)[1]+dt.timedelta(minutes=31)]

def validate_row(b,day,st,en):
    if not isinstance(b,dict):raise ValueError('BAD_BAR')
    t=dt.datetime.fromisoformat(b['t'].replace('Z','+00:00'))
    if t.tzinfo is None or t.utcoffset()!=dt.timedelta(0) or not st<=t<=en or t.second or t.microsecond:
        raise ValueError('BAD_BAR_TIME')
    o,h,l,c=(b[k] for k in ('o','h','l','c'))
    v=b['v']
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in (o,h,l,c)):
        raise ValueError('BAD_BAR_PRICE')
    if not (0<l<=min(o,c)<=max(o,c)<=h and type(v)==int and v>=0):
        raise ValueError('BAD_BAR_OHLCV')
    return t

def fetch_day(day,key,secret,opener=None,now=None):
    if day not in eligible_days(now):raise ValueError('NEW_DAY_NOT_FINISHED')
    if opener is None:opener=urllib.request.urlopen
    st,en=window(day)
    bars={s:[] for s in SYMBOLS};seen={s:set() for s in SYMBOLS}
    token=None;seen_tokens=set();pages=0
    while True:
        pages+=1
        if pages>20:raise ValueError('TOO_MANY_PAGES')
        params={'symbols':','.join(SYMBOLS),'timeframe':'1Min',
                'start':st.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'end':en.strftime('%Y-%m-%dT%H:%M:%SZ'),
                'feed':'sip','adjustment':'raw','sort':'asc','limit':10000}
        if token:params['page_token']=token
        req=urllib.request.Request(HOST+'?'+urllib.parse.urlencode(params),
            headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret,'Accept':'application/json'},method='GET')
        with opener(req,timeout=60) as response:
            obj=json.loads(response.read())
        rows=obj.get('bars')
        if not isinstance(rows,dict) or not set(rows)<=set(SYMBOLS):raise ValueError('WRONG_BARS_RESPONSE')
        for s,items in rows.items():
            if items is None:continue
            if not isinstance(items,list):raise ValueError('WRONG_BARS_TYPE')
            for b in items:
                t=validate_row(b,day,st,en)
                if t in seen[s]:raise ValueError('DUPLICATE_MINUTE')
                seen[s].add(t);bars[s].append(b)
        nxt=obj.get('next_page_token')
        if nxt is None:break
        if not isinstance(nxt,str) or not nxt or nxt in seen_tokens:raise ValueError('INVALID_PAGE_TOKEN')
        seen_tokens.add(nxt);token=nxt
    for s in SYMBOLS:bars[s].sort(key=lambda v:v['t'])
    return {'feed':'SIP','bars':bars,'requested_day':day,
            'window_utc':{'start':st.isoformat(),'last_minute_start':en.isoformat()},
            'next_page_token':None,'pages_retrieved':pages,
            'validation_status':'NOT_VALIDATED','real_trades_allowed':False,'research_only':True,
            'sec_status':'SEC_UNVERIFIED'}

def retrieve(key,secret,days=None,now=None,opener=None):
    allowed=eligible_days(now)
    request_days=days if days is not None else allowed
    if any(x not in allowed for x in request_days):raise ValueError('UNFINISHED_OR_UNAPPROVED_DAY')
    records={};checks=[]
    for day in request_days:
        try:
            doc=fetch_day(day,key,secret,opener=opener,now=now)
            records[day]=doc
            counts={s:len(doc['bars'][s]) for s in SYMBOLS}
            checks.append({'day':day,'status':'DOWNLOADED','counts':counts,
                           'missing_symbols':[s for s,n in counts.items() if n==0]})
        except urllib.error.HTTPError as ex:
            checks.append({'day':day,'status':'HTTP_ERROR','code':int(ex.code)})
            if ex.code in (401,403,429):break
        except Exception as ex:
            name=str(ex) if type(ex) is ValueError else type(ex).__name__
            checks.append({'day':day,'status':'FAILED','reason':name})
    return records,checks

def write_results(records,checks,folder='/content'):
    target=pathlib.Path(folder)/('LUCA_24_FUTURE_'+uuid.uuid4().hex[:8]+'.zip')
    manifest={'schema':'LUCA_STAGE24_FUTURE_DAYS_COLLECTION_V1',
        'source':'Alpaca SIP (declared; independently not provider-verified)',
        'frozen_protocol_sha256':RULE_SHA,'stage23_hypotheses_sha256':HYPOTHESES_SHA,
        'dates_allowed':list(ALLOWED_DAYS),'days_downloaded':list(records),
        'checks':checks,'successful_days':len(records),
        'status':'DATA_ONLY_NO_MODEL_SCORE','prediction_accuracy_verified':False,
        'new_rules_enabled':False,'real_trades_allowed':False,'validation_status':'NOT_VALIDATED',
        'sec_status':'SEC_UNVERIFIED','keys_saved':False,'files':{}}
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
        for day,doc in records.items():
            if day not in ALLOWED_DAYS:raise ValueError('DISALLOWED_DAY')
            raw=json.dumps(doc,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf8')
            name='sip_'+day+'.json'
            manifest['files'][name]={'sha256':hashlib.sha256(raw).hexdigest(),
                'bars':sum(map(len,doc['bars'].values()))}
            z.writestr(name,raw)
        z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    return target


# WORK adapter: original Stage 24 rules and source above are copied unchanged.
# This is NOT a new signal model; only a read-only GitHub Actions runner.
if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path
    key = os.environ.get("ALPACA_KEY", "")
    secret = os.environ.get("ALPACA_SECRET", "")
    requested = os.environ.get("LUCA_STAGE24_DAY", "2026-10-26")
    folder = Path(os.environ.get("LUCA_STAGE24_OUTPUT", "luca_stage24_new_evidence"))
    folder.mkdir(parents=True, exist_ok=True)
    if not key or not secret:
        print("RESULT: NO_KEYS; NOT_VALIDATED")
        sys.exit(2)
    try:
        # The notebook's own eligible_days() and window() checks remain active.
        records, checks = retrieve(key, secret, days=[requested])
        dest = write_results(records, checks, folder=str(folder))
        result = {
            "day": requested,
            "successful_days": len(records),
            "checks": checks,
            "source": "ALPACA_SIP_REQUESTED_NOT_INDEPENDENTLY_VERIFIED",
            "frozen_rule_sha256": RULE_SHA,
            "stage23_hypotheses_sha256": HYPOTHESES_SHA,
            "sec_status": "SEC_UNVERIFIED",
            "status": "NOT_VALIDATED",
            "real_trades_allowed": False,
            "zip_name": dest.name,
        }
        (folder / "collection_status.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf8"
        )
        print("RESULT: STAGE24_READ_ONLY; DAYS=", len(records),
              "; CHECKS=", json.dumps(checks, ensure_ascii=False),
              "; NOT_VALIDATED; NO_ORDERS")
        if not records:
            sys.exit(3)
    except Exception as exc:
        print("RESULT: STAGE24_FAIL_CLOSED; ERROR_TYPE=" + type(exc).__name__ +
              "; NOT_VALIDATED; NO_ORDERS")
        sys.exit(4)
    finally:
        key = ""
        secret = ""
