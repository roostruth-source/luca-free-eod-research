"""Read-only complete screener-to-IEX-batch path probe, NOT the T0 experiment.

This diagnoses all snapshot batches, not merely the first symbol. Outside the
US session a successful response is access evidence ONLY, never a live signal.
"""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path
from auto_enrich_iex import run as enrich_run

UTC=dt.timezone.utc

def evaluate(result,now):
    if not isinstance(now,dt.datetime) or now.tzinfo is None:
        raise ValueError("AWARE_CLOCK_REQUIRED")
    if type(result) is not dict or result.get("validation_status")!="NOT_VALIDATED" or result.get("real_trades_allowed") is not False:
        raise ValueError("UNSAFE_ENRICHMENT")
    batches=result.get("batches",[])
    if type(batches) is not list:
        raise ValueError("BAD_BATCH_LIST")
    report={
        "schema":"LUCA_V03_FULL_PATH_GET_ONLY_PREFLIGHT_V1",
        "checked_at_utc":now.astimezone(UTC).isoformat(),
        "enrichment_status":result.get("status"),
        "screener_symbols":result.get("discovered_count",0),
        "snapshot_batch_count":len(batches),
        "snapshot_batch_statuses":[{"size":x.get("size"),"status":x.get("status"),
                                    "returned":x.get("returned")} for x in batches],
        "snapshots_present":result.get("snapshots_present"),
        "priced_symbols":result.get("priced_count"),
        "price_band_symbols":result.get("price_band_count"),
        "full_path_access":"NOT_VERIFIED",
        "not_prospective_t0":True,
        "live_signals_confirmed":False,
        "prediction_accuracy_verified":False,
        "sec_status":"SEC_UNVERIFIED",
        "market_cap_verified":False,"float_verified":False,
        "validation_status":"NOT_VALIDATED","real_trades_allowed":False,
    }
    if result.get("status")=="COLLECTED_UNVERIFIED":
        rows=result.get("rows")
        if (type(rows) is not list or not rows or
            len(rows)!=result.get("discovered_count") or
            sum(x.get("size",0) for x in batches)!=len(rows) or
            not batches or any(x.get("status")!="OK" for x in batches)):
            raise ValueError("INCOMPLETE_SNAPSHOT_BATCHES")
        if type(report["snapshots_present"]) is not int or not 0<=report["snapshots_present"]<=len(rows):
            raise ValueError("BAD_SNAPSHOT_COUNT")
        if type(report["priced_symbols"]) is not int or not 0<=report["priced_symbols"]<=len(rows):
            raise ValueError("BAD_PRICE_COUNT")
        report["full_path_access"]="ALL_BATCH_GET_OK_SCHEMA_ONLY"
    return report

def main():
    key,secret=os.getenv("ALPACA_KEY",""),os.getenv("ALPACA_SECRET","")
    if not key or not secret:
        raise SystemExit("NO_KEYS; NO_LIVE_T0; NO_ORDERS")
    now=dt.datetime.now(UTC)
    result=enrich_run(key,secret)
    report=evaluate(result,now)
    dest=Path(os.getenv("LUCA_FULL_PATH_OUTPUT","luca_v03_full_path_preflight"))/"full_path.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open("x",encoding="utf8") as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print("FULL_PATH_GET_ONLY; STATUS="+str(report["full_path_access"])+
          "; SCREENER="+str(report["screener_symbols"])+
          "; BATCHES="+str(report["snapshot_batch_count"])+
          "; PRICED="+str(report["priced_symbols"])+
          "; NO_LIVE_T0; NOT_VALIDATED; NO_ORDERS")
    if report["full_path_access"]!="ALL_BATCH_GET_OK_SCHEMA_ONLY":
        raise SystemExit(3)

if __name__=="__main__":
    main()
