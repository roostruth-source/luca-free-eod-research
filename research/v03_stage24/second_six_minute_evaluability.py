"""Explain when a frozen second IEX ticker was actually evaluable for 6m patterns.

Analyzes verified, observed minute timestamps only; never backfills missing
minutes. It cannot validate prices, predict spikes, or authorize any orders.
"""
from __future__ import annotations
import datetime as dt

from first_iex_baseline_integrity import load_verified
from two_session_iex_comparison import compare
from forward_outcomes_iex import parse_utc

MIN_CONTEXT=6


def assess_six_minute_evaluability(frozen, review, provenance, second_run_id):
    """Independent strict source-grid recheck, then analyze contiguous windows."""
    verified=compare(load_verified(),frozen,review,provenance,second_run_id)
    expected=verified["second"]["expected_minutes_per_symbol"]
    rows=[]
    for original,rev in zip(provenance["rows"],review["results"]):
        stamps=sorted(parse_utc(s) for s in original["observed_bar_start_utc"])
        streak=longest=0
        windows=0
        previous=None
        for t in stamps:
            streak=(streak+1 if previous is not None and t-previous==dt.timedelta(minutes=1) else 1)
            longest=max(longest,streak)
            if streak>=MIN_CONTEXT:
                windows+=1
            previous=t
        possible=max(0,expected-MIN_CONTEXT+1)
        if windows>possible:
            raise ValueError("IMPOSSIBLE_EVALUABLE_WINDOW_COUNT")
        has_pattern=rev["pattern_count"]>0
        if has_pattern and windows==0:
            raise ValueError("PATTERN_WITHOUT_SIX_CONTIGUOUS_MINUTES")
        # A valid six-minute streak SOMEWHERE in the observation window is
        # insufficient. The very first declared signal must land on an
        # actually observed IEX minute and have its own five preceding bars.
        # These are timestamp checks, NOT recomputation of price/volume.
        signal_window_verified=False
        if has_pattern:
            first=rev.get("first_pattern")
            if type(first) is not dict:
                raise ValueError("MISSING_FIRST_PATTERN_EVIDENCE")
            signal_end=parse_utc(first.get("signal_bar_start_utc"))
            observed=set(stamps)
            if signal_end not in observed:
                raise ValueError("FIRST_PATTERN_BAR_NOT_OBSERVED")
            if any(signal_end-dt.timedelta(minutes=i) not in observed
                   for i in range(MIN_CONTEXT)):
                raise ValueError("FIRST_PATTERN_WITHOUT_MATCHING_SIX_MINUTE_GRID")
            signal_window_verified=True
        status=("PATTERN_RECORDED_RESEARCH_ONLY" if has_pattern else
                "NO_EVALUABLE_SIX_MINUTE_WINDOW" if not windows else
                "EVALUABLE_NO_PATTERN_RECORDED")
        rows.append({
            "symbol":original["symbol"],
            "iex_minutes_observed":len(stamps),
            "iex_minutes_expected":expected,
            "longest_contiguous_minutes":longest,
            "evaluable_six_minute_windows":windows,
            "possible_six_minute_windows":possible,
            "evaluability_status":status,
            "first_pattern_six_minute_timestamps_verified":signal_window_verified,
            "first_pattern_price_and_volume_recomputed":False,
            "no_pattern_is_not_no_future_spike":True,
            "grade":"D","buy_allowed":False
        })
    return {
        "schema":"LUCA_V03_SECOND_IEX_SIX_MIN_EVALUABILITY_V1",
        "second_source_run_id":second_run_id,
        "six_contiguous_minutes_required":MIN_CONTEXT,
        "candidate_count":len(rows),
        "evaluable_symbols":sum(r["evaluable_six_minute_windows"]>0 for r in rows),
        "not_evaluable_symbols":sum(r["evaluable_six_minute_windows"]==0 for r in rows),
        "evaluable_windows":sum(r["evaluable_six_minute_windows"] for r in rows),
        "possible_windows":sum(r["possible_six_minute_windows"] for r in rows),
        "rows":rows,
        "single_exchange_only":True,
        "no_future_price_behavior_verified":True,
        "prediction_accuracy_verified":False,
        "sec_status":"SEC_UNVERIFIED",
        "validation_status":"NOT_VALIDATED",
        "real_trades_allowed":False,
    }
