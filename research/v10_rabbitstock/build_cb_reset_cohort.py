"""Build a comparable CB-reset cohort from exact filed contract mechanics.

Contracts that merely mention a sixteenth trading day are not automatically
comparable.  Window length, number of low-VWAP observations, direction of the
adjustment, and any floor constraint must all match the reference contract.
An event also must occur on or after the contract became effective.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


FINGERPRINT_FIELDS = (
    "reset_after_trading_sessions",
    "event_market_price_window_sessions",
    "lowest_vwap_count",
    "reduction_only",
    "floor_constraint",
)


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp_timezone_required")
    return parsed.astimezone(timezone.utc)


def _date(value: str) -> date:
    return date.fromisoformat(value)


def _official_sec_url(value: str) -> None:
    if not value.startswith("https://www.sec.gov/Archives/edgar/data/"):
        raise ValueError("official_sec_filing_url_required")


def _fingerprint(contract: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in FINGERPRINT_FIELDS if key not in contract]
    if missing:
        raise ValueError(f"contract_fingerprint_fields_missing:{','.join(missing)}")
    result = {key: contract[key] for key in FINGERPRINT_FIELDS}
    if int(result["reset_after_trading_sessions"]) <= 0:
        raise ValueError("invalid_reset_session_count")
    window = int(result["event_market_price_window_sessions"])
    low_count = int(result["lowest_vwap_count"])
    if window <= 0 or low_count <= 0 or low_count > window:
        raise ValueError("invalid_event_market_price_definition")
    if result["floor_constraint"] not in {"NONE", "PRESENT", "UNKNOWN"}:
        raise ValueError("invalid_floor_constraint")
    return result


def build_cb_reset_cohort(payload: dict[str, Any]) -> dict[str, Any]:
    evaluation_asof = _time(payload["evaluation_asof"])
    contracts = payload["contracts"]
    ids = [str(item["contract_id"]) for item in contracts]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_contract_id")

    by_id = {str(item["contract_id"]): item for item in contracts}
    reference_id = str(payload["reference_contract_id"])
    if reference_id not in by_id:
        raise ValueError("reference_contract_not_found")
    reference = by_id[reference_id]
    reference_fingerprint = _fingerprint(reference)

    rows: list[dict[str, Any]] = []
    outcome_eligible_ids: list[str] = []
    mechanics_match_ids: list[str] = []
    for contract in contracts:
        contract_id = str(contract["contract_id"])
        _official_sec_url(str(contract["source_url"]))
        evidence_at = _time(contract["evidence_available_at"])
        if evidence_at > evaluation_asof:
            raise ValueError("future_contract_evidence_not_allowed")
        terms_effective_date = _date(contract["terms_effective_date"])
        fingerprint = _fingerprint(contract)
        mismatches = [
            field
            for field in FINGERPRINT_FIELDS
            if fingerprint[field] != reference_fingerprint[field]
        ]
        mechanics_match = not mismatches
        if mechanics_match:
            mechanics_match_ids.append(contract_id)

        event_results: list[dict[str, Any]] = []
        qualifying_mature_event = False
        for event in contract.get("share_combination_events", []):
            _official_sec_url(str(event["source_url"]))
            event_evidence_at = _time(event["evidence_available_at"])
            if event_evidence_at > evaluation_asof:
                raise ValueError("future_event_evidence_not_allowed")
            event_date = _date(event["event_date"])
            if event.get("verification_status") != "OFFICIAL_VERIFIED":
                event_status = "SPLIT_EVENT_UNVERIFIED"
            elif event_date < terms_effective_date:
                event_status = "EVENT_PRECEDES_TERMS_NOT_ELIGIBLE"
            elif int(event.get("trading_sessions_elapsed_asof", 0)) < int(
                contract["reset_after_trading_sessions"]
            ):
                event_status = "RESET_DATE_NOT_REACHED"
            else:
                event_status = "QUALIFYING_MATURE_EVENT"
                if mechanics_match:
                    qualifying_mature_event = True
            event_results.append(
                {
                    "event_date": event["event_date"],
                    "ratio": event.get("ratio"),
                    "status": event_status,
                }
            )

        reasons: list[str] = []
        if mismatches:
            reasons.extend(f"CONTRACT_FINGERPRINT_MISMATCH:{field}" for field in mismatches)
        if not event_results:
            reasons.append("NO_SHARE_COMBINATION_EVENT_VERIFIED")
        elif not any(item["status"] == "QUALIFYING_MATURE_EVENT" for item in event_results):
            reasons.extend(
                item["status"]
                for item in event_results
                if item["status"] != "QUALIFYING_MATURE_EVENT"
            )

        outcome_eligible = mechanics_match and qualifying_mature_event
        if outcome_eligible:
            outcome_eligible_ids.append(contract_id)
        rows.append(
            {
                "contract_id": contract_id,
                "ticker": contract["ticker"],
                "mechanics_match": mechanics_match,
                "fingerprint_mismatches": mismatches,
                "events": event_results,
                "outcome_cohort_eligible": outcome_eligible,
                "block_reasons": list(dict.fromkeys(reasons)),
            }
        )

    non_reference_outcome_ids = [
        contract_id for contract_id in outcome_eligible_ids if contract_id != reference_id
    ]
    return {
        "evaluation_asof": evaluation_asof.isoformat(),
        "reference_contract_id": reference_id,
        "reference_fingerprint": reference_fingerprint,
        "contract_count": len(contracts),
        "mechanics_match_ids": mechanics_match_ids,
        "outcome_cohort_eligible_ids": outcome_eligible_ids,
        "independent_comparator_count": len(non_reference_outcome_ids),
        "hypothesis_status": (
            "COMPARATOR_OUTCOMES_AVAILABLE"
            if non_reference_outcome_ids
            else "NO_INDEPENDENT_COMPARATOR_EVENT"
        ),
        "contracts": rows,
        "WATCH_ONLY": True,
        "NO_ORDERS": True,
        "validation_status": "NOT_VALIDATED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input_json.read_text())
    print(json.dumps(build_cb_reset_cohort(payload), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
