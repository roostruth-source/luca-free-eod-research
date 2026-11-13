"""Run the executable LUCA V10 research build on frozen, time-safe inputs.

This is a research detector, not an order system.  It joins the common
NASDAQ 7.0 safety gate with the China-related 1.0 classification and emits a
ranked observation report.  Ranking is consensus-first and is not a predicted
probability of a price increase.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluate_snapshot import evaluate_snapshot


PROFILES = {"NASDAQ_7_0", "CHINA_1_0"}
SAFETY = {"WATCH_ONLY": True, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED"}


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def _profile(payload: dict[str, Any]) -> tuple[str, list[str]]:
    profile = str(payload.get("detector_profile", "NASDAQ_7_0"))
    if profile not in PROFILES:
        raise ValueError("unsupported_detector_profile")
    reasons: list[str] = []
    if profile == "CHINA_1_0":
        evidence_at = payload.get("issuer_region_evidence_at")
        source_url = str(payload.get("issuer_region_source_url", ""))
        if not evidence_at:
            raise ValueError("china_profile_evidence_timestamp_required")
        if not source_url.startswith("https://www.sec.gov/"):
            raise ValueError("china_profile_sec_source_required")
        if _time(str(evidence_at)) > _time(payload["snapshot_at"]):
            raise ValueError("future_china_profile_evidence_not_allowed")
        if payload.get("issuer_region") != "PRC_OPERATIONS":
            raise ValueError("china_profile_prc_operations_required")
        reasons.append("SEC_VERIFIED_PRC_OPERATIONS")
    else:
        reasons.append("NASDAQ_CORE_PROFILE")
    return profile, reasons


def is_snapshot_payload(payload: object) -> bool:
    return isinstance(payload, dict) and {
        "ticker", "snapshot_at", "data_asof", "source_type", "entry", "engine_hits"
    }.issubset(payload)


def build_report(payloads: list[dict[str, Any]], built_at: str) -> dict[str, Any]:
    built_at_dt = _time(built_at)
    candidates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for payload in payloads:
        ticker = str(payload.get("ticker", "UNKNOWN")).upper()
        try:
            if _time(payload["snapshot_at"]) > built_at_dt:
                raise ValueError("future_snapshot_not_allowed")
            profile, profile_reasons = _profile(payload)
            evaluated = evaluate_snapshot(payload)
            best_rank = min(evaluated["engine_ranks"].values()) if evaluated["engine_ranks"] else None
            candidates.append({
                "ticker": evaluated["ticker"],
                "detector_profile": profile,
                "profile_reasons": profile_reasons,
                "snapshot_at": evaluated["snapshot_at"],
                "data_asof": evaluated["data_asof"],
                "engine_count": evaluated["engine_count"],
                "engine_ranks": evaluated["engine_ranks"],
                "best_engine_rank": best_rank,
                "target_median": evaluated["target_median"],
                "target_range": evaluated["target_range"],
                "screen_upside_pct": payload.get("screen_upside_pct"),
                "state": evaluated["state"],
                "block_reasons": evaluated["block_reasons"],
                "present_supply_checks": evaluated["present_supply_checks"],
                "unknown_supply_checks": evaluated["unknown_supply_checks"],
                "potential_dilution_pct": evaluated["potential_dilution_pct"],
                "cumulative_reverse_split_factor": evaluated["cumulative_reverse_split_factor"],
                "selection_reason": (
                    f"{evaluated['engine_count']}개 엔진 동시 포착; "
                    f"최고 순위 {best_rank}; 위험 차단 {len(evaluated['block_reasons'])}개"
                ),
                **SAFETY,
            })
        except (KeyError, TypeError, ValueError) as exc:
            errors.append({"ticker": ticker, "error": str(exc)})

    candidates.sort(key=lambda item: (
        -int(item["engine_count"]),
        int(item["best_engine_rank"] or 10**9),
        str(item["ticker"]),
    ))
    profile_counts = {
        profile: sum(1 for item in candidates if item["detector_profile"] == profile)
        for profile in sorted(PROFILES)
    }
    return {
        "schema_version": "LUCA_V10_EXECUTABLE_RESEARCH_1",
        "built_at": built_at_dt.isoformat(),
        "input_count": len(payloads),
        "evaluated_count": len(candidates),
        "error_count": len(errors),
        "profile_counts": profile_counts,
        "ranking_rule": "engine_count_desc_then_best_rank_asc_not_probability",
        "candidates": candidates,
        "errors": errors,
        "completed_features": [
            "NASDAQ_7_0_AND_CHINA_1_0_PROFILE_ROUTING",
            "FIVE_ENGINE_CONSENSUS_CAPTURE",
            "SEC_SUPPLY_AND_DILUTION_GATES",
            "FLOAT_AND_REVERSE_SPLIT_GATES",
            "EXCHANGE_STATUS_AND_FUTURE_DATA_GATES",
        ],
        "incomplete_features": [
            "LIVE_MARKET_WIDE_DISCOVERY",
            "FULL_SEC_AUTOMATIC_EXTRACTION",
            "PREDICTIVE_ACCURACY_VALIDATION",
            "INTRADAY_EXECUTION_OR_SLIPPAGE_MODEL",
        ],
        **SAFETY,
    }


def load_payloads(input_dir: Path) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for path in sorted(input_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if is_snapshot_payload(payload):
            payloads.append(payload)
    return payloads


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path(__file__).parent)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--built-at", required=True)
    args = parser.parse_args()
    report = build_report(load_payloads(args.input_dir), args.built_at)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(args.output),
        "evaluated_count": report["evaluated_count"],
        "error_count": report["error_count"],
        **SAFETY,
    }, ensure_ascii=False))
    return 0 if report["error_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
