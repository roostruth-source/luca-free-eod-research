"""Read-only fixed-clock benchmark for every preselected LUCA T0 ticker.

A precommitted shared timestamp is the same for signaled and nonsignaled stocks.
This provides a reference group without choosing an entry after watching prices.
It is NOT a randomized control, causal experiment, executable return, SEC
clearance, proof of an absent signal, or a valid prediction accuracy estimate.
"""
from __future__ import annotations
import datetime as dt
import json
import os
from pathlib import Path

from forward_outcomes_iex import (
    HORIZONS, CUSHION, parse_utc, validate_origins, fetch_forward_bars,
    horizon_result
)
from iex_1min_research import valid_bar
from prospective_iex_research import as_utc, next_bar_start


def fixed_reference_entries(frozen, review):
    """Defined solely by T0, not by eventual IEX price, signal, or outcome."""
    t0, reviewed, _signals=validate_origins(frozen,review)
    shared=next_bar_start(t0)+dt.timedelta(minutes=6)
    if shared>reviewed:
        raise ValueError("REFERENCE_NOT_YET_OBSERVABLE")
    return {symbol:shared for symbol in frozen["candidates"]}


def prepare_result(frozen, review, bars, now):
    """Return separate evidence for all T0 symbols; no outcome until mature."""
    t0,reviewed,signal_entries=validate_origins(frozen,review)
    candidates=fixed_reference_entries(frozen,review)
    now=as_utc(now)
    if not candidates:
        raise ValueError("EMPTY_CONTROL_UNIVERSE")
    if type(bars) is not dict or set(bars)!=set(candidates):
        raise ValueError("FROZEN_REFERENCE_UNIVERSE_MISMATCH")
    entry=list(candidates.values())[0]
    last=entry+dt.timedelta(minutes=59)
    if now<last+dt.timedelta(minutes=1)+CUSHION:
        raise ValueError("FIXED_REFERENCE_FUTURE_NOT_MATURE")
    results=[]
    for item in review["results"]:
        sym=item["symbol"]
        if item.get("grade")!="D" or item.get("buy_allowed") is not False:
            raise ValueError("UNSAFE_BENCHMARK_ROW")
        source=bars[sym]
        if type(source) is not list:
            raise ValueError("INVALID_BAR_LIST")
        # Do not silently include observations from before reference decision.
        # A bad timestamp (including a future timestamp) fails the whole report.
        clean=[valid_bar(b,entry,last) for b in source]
        ts=[parse_utc(b["t"]) for b in clean]
        if len(ts)!=len(set(ts)):
            raise ValueError("DUPLICATE_IEX_BAR")
        measures=[horizon_result(clean,entry,minutes) for minutes in HORIZONS]
        bar_count=item.get("observed_iex_bars")
        if type(bar_count) is not int or bar_count<0:
            raise ValueError("INVALID_PREVIOUS_OBSERVATION_COUNT")
        results.append({
            "symbol":sym,
            "control_entry_utc":entry.isoformat(),
            "initial_16min_pattern_observed":item["pattern_count"]>0,
            "initial_16min_iex_bar_count":bar_count,
            "absence_of_pattern_proven":False,
            "horizons":measures,
            "sec_status":"SEC_UNVERIFIED","grade":"D","buy_allowed":False
        })
    return {
        "schema":"LUCA_V03_FROZEN_FIXED_CLOCK_REFERENCE_V1",
        "freeze_sha256":frozen["sha256"],
        "selected_at_utc":t0.isoformat(),
        "original_reviewed_at_utc":reviewed.isoformat(),
        "reference_utc":entry.isoformat(),
        "checked_at_utc":now.isoformat(),
        "frozen_symbols":len(results),
        "initial_pattern_observed":sum(x["initial_16min_pattern_observed"] for x in results),
        "initial_no_pattern_observed":sum(not x["initial_16min_pattern_observed"] for x in results),
        "observed_iex_prices_complete":sum(
            p["status"]=="COMPLETE_IEX_PRICES_ONLY"
            for row in results for p in row["horizons"]
        ),
        "rows":results,
        "reference_design":"SAME_FIXED_CLOCK_ALL_FROZEN_SYMBOLS_T0_PLUS_7ISH_MINUTES",
        "entry_chosen_before_outcomes":True,
        "not_randomized_control":True,
        "not_proof_of_no_signal":True,
        "not_a_causal_effect_estimate":True,
        "not_prospective_accuracy_verified":True,
        "fees_spread_slippage_or_fills_verified":False,
        "market_cap_verified":False,"float_verified":False,
        "sec_status":"SEC_UNVERIFIED",
        "feed":"ALPACA_IEX_SINGLE_EXCHANGE",
        "validation_status":"NOT_VALIDATED","real_trades_allowed":False,
        "warning":"Same T0-frozen candidate universe at fixed clock; labels use later observation for description only. Missing IEX minutes remain unknown. No investment grade."
    }


def run():
    folder=Path(os.environ.get("LUCA_FOLLOWUP_INPUT","luca_v03_forward"))
    output=Path(os.environ.get("LUCA_REFERENCE_OUTPUT","luca_v03_reference"))
    frozen=json.loads((folder/"frozen_t0.json").read_text(encoding="utf8"))
    review=json.loads((folder/"forward_review.json").read_text(encoding="utf8"))
    references=fixed_reference_entries(frozen,review)
    if not references:
        raise SystemExit("EMPTY_REFERENCE_GROUP_NOT_VALIDATED")
    now=dt.datetime.now(dt.timezone.utc)
    latest=max(references.values())+dt.timedelta(minutes=60)+CUSHION
    if now<latest:
        raise SystemExit("REFERENCE_FUTURE_NOT_READY; NOT_VALIDATED; NO_ORDERS")
    key,secret=os.getenv("ALPACA_KEY",""),os.getenv("ALPACA_SECRET","")
    result=prepare_result(
        frozen,review,fetch_forward_bars(references,now,key,secret),now)
    output.mkdir(parents=True,exist_ok=True)
    with (output/"fixed_clock_reference.json").open("x",encoding="utf8") as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
        f.write("\n")
    print("REFERENCE_COMPLETED; FROZEN="+str(result["frozen_symbols"])+
          "; NO_PATTERN_OBSERVED="+str(result["initial_no_pattern_observed"])+
          "; VALID_HORIZONS="+str(result["observed_iex_prices_complete"])+
          "; NOT_VALIDATED; NO_ORDERS; NOT_CAUSAL")


if __name__=="__main__":
    run()
