"""Offline cohort scorecard: count wins, losses and missing outcomes separately.

Descriptive bar-close changes only. Not actual fills or verified predictions.
"""
from __future__ import annotations
from offline_reference_commitment import compare_committed

HORIZONS = ("5", "15", "30", "60")
GROUPS = ("signal_by_reference_time", "no_signal_by_reference_time")


def scorecard(raw, manifest, threshold_pct=5):
    if type(threshold_pct) not in (int, float) or not 0 < threshold_pct <= 100:
        raise ValueError("INVALID_THRESHOLD")
    comparison = compare_committed(raw, manifest)
    rows = comparison["rows"]
    groups = {}
    for group in GROUPS:
        subset = [r for r in rows if r["group"] == group]
        horizons = {}
        for horizon in HORIZONS:
            changes = [r["changes_pct"][horizon] for r in subset]
            observed = [x for x in changes if x is not None]
            missing = len(changes) - len(observed)
            wins = sum(x >= threshold_pct for x in observed)
            declines = sum(x < 0 for x in observed)
            flat_or_positive_below_threshold = sum(0 <= x < threshold_pct for x in observed)
            horizons[horizon] = {
                "candidates": len(subset),
                "observed": len(observed),
                "missing": missing,
                "threshold_reached": wins,
                "declined": declines,
                "flat_or_positive_below_threshold": flat_or_positive_below_threshold,
                "observed_mean_change_pct": (
                    round(sum(observed) / len(observed), 4) if observed else None),
                "threshold_rate_among_observed_pct": (
                    round(wins / len(observed) * 100, 4) if observed else None),
                "missing_count_in_denominator": False,
            }
        groups[group] = {"candidates": len(subset), "horizons": horizons}
    return {
        "schema": "LUCA_V03_OFFLINE_COHORT_SCORECARD_V1",
        "reference_time_utc": comparison["reference_time_utc"],
        "commitment_sha256": comparison["commitment_sha256"],
        "threshold_pct": threshold_pct,
        "groups": groups,
        "prediction_accuracy_verified": False,
        "statistical_significance_verified": False,
        "commitment_timestamp_externally_verified": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "orders_allowed": False,
        "real_trades_allowed": False,
        "warning_ko": "관찰된 종가 변화의 설명용 성적표입니다. 결측은 0%나 성공으로 취급하지 않습니다. 실제 체결 수익·예측 성공률이 아닙니다.",
    }
