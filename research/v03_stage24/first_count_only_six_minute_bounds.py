"""Count-only observability bounds for LUCA V0.3's FIRST real IEX trial.

Offline, deterministic, no API, no order, no alteration of signal thresholds.
Enumerate every placement of k observed minutes among 14 slots. The original
first-session archive lacks raw minute timestamps/OHLCV, so bounds are NOT
measured actual consecutive windows and never imply a stock signal.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import json
from pathlib import Path

from first_iex_baseline_integrity import load_verified

OBSERVATION_SLOTS = 14
PATTERN_WINDOW = 6


@lru_cache(maxsize=1)
def exact_count_bounds(slots: int = OBSERVATION_SLOTS,
                       width: int = PATTERN_WINDOW) -> tuple[dict, ...]:
    """All 2**slots configurations, grouped by observed bar count.

    Each consecutive run of r bars contains max(0, r-width+1) windows.
    No interpolation; a missing minute breaks a run.
    """
    if (type(slots) is not int or type(width) is not int or
            slots != OBSERVATION_SLOTS or width != PATTERN_WINDOW):
        raise ValueError("LOCKED_FIRST_TRIAL_GRID_ONLY")
    entries = [
        {"min_six_min_windows": None, "max_six_min_windows": 0,
         "min_longest_consecutive": None, "max_longest_consecutive": 0}
        for _ in range(slots + 1)
    ]
    for mask in range(1 << slots):
        present = mask.bit_count()
        run = longest = windows = 0
        for minute in range(slots):
            if mask & (1 << minute):
                run += 1
                longest = max(longest, run)
                if run >= width:
                    windows += 1
            else:
                run = 0
        entry = entries[present]
        if entry["min_six_min_windows"] is None:
            entry["min_six_min_windows"] = windows
            entry["min_longest_consecutive"] = longest
        entry["min_six_min_windows"] = min(entry["min_six_min_windows"], windows)
        entry["max_six_min_windows"] = max(entry["max_six_min_windows"], windows)
        entry["min_longest_consecutive"] = min(entry["min_longest_consecutive"], longest)
        entry["max_longest_consecutive"] = max(entry["max_longest_consecutive"], longest)
    return tuple(entries)


def analyze_verified_first(root: str | Path | None = None) -> dict:
    """Fail closed unless the existing validated normalized first archive loads."""
    first = load_verified(root)
    data = exact_count_bounds()
    rows = []
    for row in first["rows"]:
        count = row["initial_iex_minutes"]
        if type(count) is not int or not 0 <= count <= OBSERVATION_SLOTS:
            raise ValueError("BAD_FIRST_BAR_COUNT")
        limits = data[count]
        if limits["min_six_min_windows"] > 0:
            status = "EXISTENCE_GUARANTEED_BUT_TIMESTAMPS_NOT_ARCHIVED"
        elif limits["max_six_min_windows"] == 0:
            status = "SIX_CONSECUTIVE_MINUTES_IMPOSSIBLE"
        else:
            status = "EXISTENCE_UNRESOLVED_WITHOUT_TIMESTAMPS"
        rows.append({
            "symbol": row["symbol"],
            "observed_iex_bars": count,
            "expected_minute_slots": OBSERVATION_SLOTS,
            **limits,
            "count_only_class": status,
            "actual_six_minute_windows_observed": None,
            "signal_pattern_recomputed": False,
            "buy_allowed": False,
        })
    if len(rows) != first["frozen_symbols"]:
        raise ValueError("FIRST_COUNT_DRIFT")
    minimum = sum(x["min_six_min_windows"] for x in rows)
    maximum = sum(x["max_six_min_windows"] for x in rows)
    guaranteed = sum(x["min_six_min_windows"] > 0 for x in rows)
    impossible = sum(x["max_six_min_windows"] == 0 for x in rows)
    unknown = len(rows) - guaranteed - impossible
    return {
        "schema": "LUCA_V03_FIRST_IEX_COUNT_ONLY_SIX_MIN_BOUNDS_V1",
        "source_run_id": first["source_run_id"],
        "frozen_t0_sha256": first["frozen_t0_sha256"],
        "observed_iex_bars": first["initial"]["observed_iex_bars"],
        "expected_iex_bars": first["initial"]["expected_symbol_minutes"],
        "expected_minute_slots_per_symbol": OBSERVATION_SLOTS,
        "six_consecutive_minutes_required": PATTERN_WINDOW,
        "candidate_count": len(rows),
        "guaranteed_evaluable_by_bar_count": guaranteed,
        "unresolved_by_bar_count": unknown,
        "impossible_by_bar_count": impossible,
        "possible_six_minute_windows_lower_bound": minimum,
        "possible_six_minute_windows_upper_bound": maximum,
        "rows": rows,
        "exact_minute_timestamps_unavailable": True,
        "actual_signal_recomputed": False,
        "first_recorded_pattern_symbols": 0,
        "not_prediction_accuracy": True,
        "single_exchange_only": True,
        "sec_status": "SEC_UNVERIFIED",
        "validation_status": "NOT_VALIDATED",
        "real_trades_allowed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="Optional NEW research-only JSON file path")
    args = parser.parse_args()
    result = analyze_verified_first()
    print(
        "COUNT_ONLY_6M: guaranteed={guaranteed_evaluable_by_bar_count} "
        "unknown={unresolved_by_bar_count} impossible={impossible_by_bar_count} "
        "possible_windows={possible_six_minute_windows_lower_bound}-"
        "{possible_six_minute_windows_upper_bound}; NOT_VALIDATED; NO_ORDERS".format(**result)
    )
    if args.output:
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf8") as file:
            json.dump(result, file, indent=2, ensure_ascii=False)
            file.write("\n")


if __name__ == "__main__":
    main()
