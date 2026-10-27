"""Archive precise second followup step outcomes without fake zero returns.

Used by GitHub Actions AFTER market API steps, including partial failures.
The workflow still fails after upload if any essential step failed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

VALID={"success","failure","skipped","cancelled"}

def build_status(signal,reference,quality):
    values={"signal_outcomes":signal,"fixed_clock_reference":reference,"quality_report":quality}
    if any(type(x) is not str or x not in VALID for x in values.values()):
        raise ValueError("INVALID_GITHUB_STEP_OUTCOME")
    complete=all(x=="success" for x in values.values())
    return {
        "schema":"LUCA_V03_SECOND_FOLLOWUP_STEP_STATUS_V1",
        "steps":values,
        "all_essential_steps_succeeded":complete,
        "partial_evidence_must_not_be_interpreted_as_zero_returns":True,
        "not_an_iex_coverage_measurement":True,
        "quality":"NOT_VALIDATED" if complete else "INCOMPLETE_EVIDENCE",
        "sec_status":"SEC_UNVERIFIED",
        "real_trades_allowed":False,
        "actual_fill_or_profit_verified":False,
    }

def main():
    p=argparse.ArgumentParser()
    for name in ("signal","reference","quality"):
        p.add_argument("--"+name,required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    obj=build_status(a.signal,a.reference,a.quality)
    out=Path(a.output)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf8") as f:
        json.dump(obj,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print("SECOND_FOLLOWUP_STEP_STATUS; "+("COMPLETE" if obj["all_essential_steps_succeeded"] else "INCOMPLETE")+
          "; NOT_VALIDATED; NO_ORDERS")

if __name__=="__main__":
    main()
