"""Reconcile frozen snapshots, two-source bars, and follow-up reference outcomes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from evaluate_followups import evaluate_followups
from evaluate_snapshot import evaluate_snapshot
from reconcile_daily_bars import reconcile_bar

MIN_INDEPENDENT_SIGNALS = 30  # Predeclared coverage floor, not a success threshold.


def _time(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return value.astimezone(timezone.utc)


def _load(base: Path, relative: str) -> dict:
    target = (base / relative).resolve()
    if not target.is_relative_to(base.resolve()) or target.suffix != ".json":
        raise ValueError("input_path_outside_base")
    return json.loads(target.read_text(encoding="utf-8"))


def verify_case(case: dict, base: Path, evaluation_asof: datetime) -> dict:
    snapshot = _load(base, case["snapshot"])
    followup = _load(base, case["followup"])
    evaluated = evaluate_snapshot(snapshot)
    signals = followup["signals"]
    if len(signals) != 1:
        raise ValueError("one_signal_per_case_required")
    signal = signals[0]
    if (signal["ticker"].upper() != evaluated["ticker"]
            or _time(signal["signal_at"]) != _time(evaluated["snapshot_at"])
            or not math.isclose(float(signal["entry_price"]), float(snapshot["entry"]), rel_tol=1e-9)
            or set(signal["engine_hits"]) != set(snapshot["engine_hits"])):
        raise ValueError("followup_snapshot_mismatch")
    if signal["entry_rule"] != "SCREEN_REFERENCE_PRICE":
        raise ValueError("only_reference_price_validation_supported")
    if (bool(signal["screen_dilution_warning"]) != evaluated["screen_dilution_warning"]
            or bool(signal["official_dilution_warning"]) != evaluated["official_dilution_warning"]):
        raise ValueError("followup_dilution_labels_mismatch")
    if _time(followup["evaluation_asof"]) > evaluation_asof:
        raise ValueError("future_followup_evaluation_not_allowed")
    sources = case["bar_sources"]
    if len(sources) != len(signal["bars"]):
        raise ValueError("bar_source_count_mismatch")
    for bar, path in zip(signal["bars"], sources):
        source_input = _load(base, path)
        if _time(source_input["evaluation_asof"]) > evaluation_asof:
            raise ValueError("future_price_source_not_allowed")
        result = reconcile_bar(source_input)
        canonical = result["canonical_bar"]
        if result["reconciliation_status"] != "VERIFIED":
            raise ValueError("price_source_not_verified:" + result["reconciliation_status"])
        if (result["ticker"] != evaluated["ticker"]
                or _time(result["signal_at"]) != _time(signal["signal_at"])
                or _time(canonical["session_close_at"]) != _time(bar["session_close_at"])
                or any(not math.isclose(float(canonical[field]), float(bar[field]), rel_tol=1e-9)
                       for field in ("open", "high", "low", "close"))):
            raise ValueError("canonical_bar_followup_mismatch")
    return signal


def validate(manifest: dict, base: Path) -> dict:
    evaluation_asof = _time(manifest["evaluation_asof"])
    verified = []
    rejected = []
    seen = set()
    for index, case in enumerate(manifest["cases"]):
        try:
            signal = verify_case(case, base, evaluation_asof)
            identity = (signal["ticker"].upper(), _time(signal["signal_at"]))
            if identity in seen:
                raise ValueError("duplicate_signal_not_independent")
            seen.add(identity)
            verified.append(signal)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            rejected.append({"case": index, "reason": str(exc)})
    outcomes = evaluate_followups({
        "evaluation_asof": evaluation_asof.isoformat(), "signals": verified,
    })
    matured = {str(h): sum(r["outcomes"][str(h)]["status"] == "MATURE"
                            for r in outcomes["records"]) for h in (1, 3, 5, 10)}
    ready = (not rejected and len(verified) >= MIN_INDEPENDENT_SIGNALS
             and matured["5"] >= MIN_INDEPENDENT_SIGNALS)
    return {
        "schema_version": "LUCA_V10_REFERENCE_VALIDATION_1",
        "evaluation_asof": evaluation_asof.isoformat(),
        "verified_signals": len(verified),
        "rejected_cases": rejected,
        "matured_horizons": matured,
        "coverage_status": "READY_FOR_STATISTICAL_REVIEW" if ready else "INSUFFICIENT_VERIFIED_SAMPLE",
        "min_independent_signals_predeclared": MIN_INDEPENDENT_SIGNALS,
        "reference_outcomes": outcomes,
        "trade_accuracy_validated": False,
        "WATCH_ONLY": True, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = validate(json.loads(args.manifest.read_text(encoding="utf-8")), args.manifest.parent)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"verified": report["verified_signals"],
                      "rejected": len(report["rejected_cases"]),
                      "coverage": report["coverage_status"], "NO_ORDERS": True}))
    return 2 if report["rejected_cases"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
