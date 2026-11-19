"""Offline fixed-time cohort comparison. Synthetic tests only; not trading returns."""
import datetime as dt
from mobile_outcomes import _time, _price, build_report

HORIZONS = (5, 15, 30, 60)


def compare(raw, reference_time_utc):
    # Reuse all raw evidence and six-bar signal integrity checks.
    report = build_report(raw)
    anchor = _time(reference_time_utc)
    rows = raw["rows"]
    if not rows:
        raise ValueError("EMPTY_COHORT")
    results = []
    for row in rows:
        bars = {_time(bar["t"]): _price(bar["c"]) for bar in row["ohlcv"]}
        base = bars.get(anchor)
        changes = {}
        for minutes in HORIZONS:
            later = bars.get(anchor + dt.timedelta(minutes=minutes))
            changes[str(minutes)] = (
                round((later / base - 1) * 100, 4)
                if base is not None and later is not None else None)
        # Group membership must be known by the reference time, not learned later.
        prior_signals = [
            entry for entry in row["signals"]
            if _time(entry["signal"]["signal_bar_start_utc"]) <= anchor
        ]
        group = "signal_by_reference_time" if prior_signals else "no_signal_by_reference_time"
        results.append({"symbol": row["symbol"], "group": group,
                        "reference_close": base, "changes_pct": changes})
    counts = {}
    for minutes in HORIZONS:
        key = str(minutes)
        counts[key] = {
            group: sum(item["changes_pct"][key] is not None for item in results
                       if item["group"] == group)
            for group in ("signal_by_reference_time", "no_signal_by_reference_time")
        }
    return {
        "schema": "LUCA_V03_FIXED_TIME_COHORT_COMPARISON_V1",
        "reference_time_utc": anchor.isoformat(),
        "rows": results,
        "observed_counts_by_horizon": counts,
        "grouping_rule": "signal_observed_on_or_before_fixed_reference_time",
        "reference_time_must_be_precommitted": True,
        "statistical_significance_verified": False,
        "prediction_accuracy_verified": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "orders_allowed": False,
        "real_trades_allowed": False,
        "warning_ko": "고정 시각의 봉 종가 변화만 비교합니다. 실제 체결 수익이나 검증된 예측력은 아닙니다.",
    }
