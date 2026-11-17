"""Fail-closed adapter from partial EOD collector to mobile research JSON."""
import csv, datetime as dt, io, json, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
def main():
    feed=json.loads(Path("site_data/latest.json").read_text())
    if feed.get("status")!="PARTIAL_EOD_RESEARCH" or feed.get("validated") is not False or feed.get("orders_enabled") is not False or not feed.get("rows"):
        raise ValueError("EOD feed unavailable or unsafe")
    ts=dt.datetime.fromisoformat(feed["generated_at"].replace("Z","+00:00"))
    if ts.tzinfo is None or not (-dt.timedelta(hours=1)<=dt.datetime.now(dt.timezone.utc)-ts<=dt.timedelta(days=4)):
        raise ValueError("stale feed")
    out=[]
    for r in feed["rows"]:
        vol=float(r["volume"]);avg=float(r["avg_volume_20d"]);p=float(r["close"]);prev=float(r["prev_close"])
        if min(vol,avg,p,prev)<=0: raise ValueError("invalid price/volume")
        rv=vol/avg
        score=(35 if rv>=5 else 25 if rv>=3 else 15 if rv>=1.8 else 0)+(15 if 2<=100*(p/prev-1)<=20 else 0)
        # Float unavailable and SEC not independently verified: max score 29.
        score=min(score,29)
        out.append({"ticker":r["ticker"],"date":r["date"],"close":p,"change_pct":100*(p/prev-1),"volume":vol,
                    "rvol":rv,"float_shares":None,"research_score":score,"sec_status":"UNVERIFIED",
                    "active_risks":[],"unknown_risks":["atm_active","eloc_active","cb_active","warrants_active","reverse_split_pending","going_concern"],
                    "reasons":["RVOL "+str(round(rv,2))],"trading_allowed":False,"signal":"RESEARCH_ONLY"})
    target=Path("site_data/latest_mobile.json")
    target.write_text(json.dumps({"version":2,"generated_at":feed["generated_at"],"asof":feed["asof"],"status":"PARTIAL_RESEARCH",
      "universe":"FIXED_WATCHLIST_NOT_MARKET_WIDE","realtime":False,"validated":False,"sec_contracts_verified":False,
      "orders_enabled":False,"rows":out,"errors":[],"count":len(out)},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
