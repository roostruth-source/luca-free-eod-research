"""Conservative SEC evidence and historical-event primitives. NO_ORDERS.
Text matches are review flags, NOT evidence that financing is active.
"""
import re,html,datetime as dt,math
from urllib.parse import urlparse
from collections import defaultdict
PATTERNS={'ATM':r'\bat[- ]the[- ]market\b|\bsales agreement\b','ELOC':r'\bequity line of credit\b|\bequity purchase agreement\b','CB':r'\bconvertible (?:promissory )?notes?\b|\bconvertible debentures?\b','WARRANT':r'\bwarrants?\b','RESET':r'\b(?:conversion price|exercise price)\b.{0,160}\b(?:reset|adjust|discount)\b|\b(?:reset|floor) price\b','REVERSE_SPLIT':r'\breverse stock split\b|\breverse split\b','GOING_CONCERN':r'\bsubstantial doubt\b.{0,100}\bgoing concern\b'}
def evidence(raw,url):
 u=urlparse(url)
 if u.scheme!='https' or u.hostname!='www.sec.gov' or not u.path.startswith('/Archives/edgar/data/') or u.username or u.password or u.port:raise ValueError('SEC URL required')
 if len(raw)>3000000:raise ValueError('document too large')
 s=raw.decode('utf-8','replace')
 s=re.sub(r'(?is)<(script|style)\b[^>]*>.*?</\1\s*>',' ',s)
 s=re.sub(r'(?s)<[^>]*>',' ',s)
 s=re.sub(r'\s+',' ',html.unescape(s))
 flags=[]
 for label,pattern in PATTERNS.items():
  matches=[{'excerpt':s[max(0,m.start()-100):m.end()+120],'offset':m.start()} for m in re.finditer(pattern,s,re.I)]
  if matches:flags.append({'category':label,'hits':matches[:3]})
 return {'source_url':url,'evidence_flags':flags,'sec_contract_terms_verified':False,'active_financing_verified':False,'manual_review_required':True,'orders_enabled':False}
def walkforward(rows,horizon=5,threshold=.20,min_history=20):
 if not 1<=horizon<=30:raise ValueError('horizon')
 groups=defaultdict(list)
 for r in rows:
  date=dt.date.fromisoformat(str(r['date']));price=float(r['close']);score=float(r['score'])
  if price<=0 or not all(map(math.isfinite,[price,score])):raise ValueError('price/score')
  groups[str(r['ticker']).upper()].append((date,price,score))
 events=[]
 for ticker,seq in groups.items():
  seq.sort()
  if len({r[0] for r in seq})!=len(seq):raise ValueError('duplicate')
  for i in range(min_history,len(seq)-horizon):
   date,price,score=seq[i];future=[r[1] for r in seq[i+1:i+1+horizon]]
   events.append({'date':str(date),'score':score,'hit':max(future)/price-1>=threshold})
 if not events:return {'status':'INSUFFICIENT_HISTORY','validated':False,'orders_enabled':False}
 dates=sorted({e['date'] for e in events});cut=dates[max(0,int(len(dates)*.7)-1)]
 def metric(x):
  flagged=[e for e in x if e['score']>=40]
  return {'observations':len(x),'flagged':len(flagged),'hits':sum(e['hit'] for e in flagged),'precision':sum(e['hit'] for e in flagged)/len(flagged) if flagged else None}
 return {'status':'EXPLORATORY_NOT_VALIDATED','validated':False,'orders_enabled':False,'split_date':cut,'train':metric([e for e in events if e['date']<=cut]),'test':metric([e for e in events if e['date']>cut]),'caveats':['historical universe required','corporate actions not adjusted','transaction costs omitted','point-in-time score required']}
