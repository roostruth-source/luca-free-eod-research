"""Conservative SEC filing-text supply-risk context.

Text terms can require a hold, but they never prove current remaining capacity,
exerciseability, registration effectiveness, outstanding shares, or float.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit


RISK_TERMS = {
    "ATM": "ATM(시장가 수시매각) 언급",
    "ELOC": "ELOC(주식매입 약정) 언급",
    "CB": "CB(전환사채) 언급",
    "WARRANT": "Warrant(신주인수권) 언급",
    "SHELF": "Shelf(선반등록) 언급",
}
MAX_REVIEWS = 2
MAX_SIGNALS = 10


def _time(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("supply_evidence_timestamp_required")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("supply_evidence_timestamp_invalid") from exc
    if value.tzinfo is None:
        raise ValueError("supply_evidence_timezone_required")
    return value.astimezone(timezone.utc)


def _official_archive_url(raw: object) -> str:
    if not isinstance(raw, str):
        raise ValueError("official_sec_supply_source_required")
    parsed = urlsplit(raw)
    if (parsed.scheme != "https" or parsed.netloc != "www.sec.gov"
            or not parsed.path.startswith("/Archives/edgar/data/")
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError("official_sec_supply_source_required")
    return raw


def build(review_filings: list[dict], unreviewed_filings: int,
          asof: datetime) -> dict:
    if not isinstance(asof, datetime) or asof.tzinfo is None:
        raise ValueError("supply_context_asof_timezone_required")
    if (not isinstance(review_filings, list) or len(review_filings) > MAX_REVIEWS
            or type(unreviewed_filings) is not int or unreviewed_filings < 0):
        raise ValueError("invalid_supply_review_coverage")
    signals = []
    completed = 0
    unavailable = 0
    asof_utc = asof.astimezone(timezone.utc)
    for review in review_filings:
        if not isinstance(review, dict):
            raise ValueError("invalid_supply_review")
        accepted = _time(review.get("accepted_at_utc"))
        if accepted > asof_utc:
            raise ValueError("future_supply_evidence_not_allowed")
        source_url = _official_archive_url(review.get("source_url"))
        form = review.get("form")
        if not isinstance(form, str) or not form:
            raise ValueError("supply_evidence_form_required")
        matched = review.get("matched_terms")
        if not isinstance(matched, list):
            unavailable += 1
            continue
        completed += 1
        for match in matched:
            if not isinstance(match, dict):
                raise ValueError("invalid_supply_term_match")
            term = match.get("term")
            if term not in RISK_TERMS:
                continue
            context = match.get("context")
            if not isinstance(context, str) or not context:
                raise ValueError("supply_term_context_required")
            signals.append({
                "code": term, "ko": RISK_TERMS[term], "form": form,
                "accepted_at_utc": accepted.isoformat(),
                "source_url": source_url, "context": context[:300],
            })
            if len(signals) > MAX_SIGNALS:
                raise ValueError("supply_signal_cap_exceeded")
    risk = bool(signals)
    incomplete = unreviewed_filings > 0 or unavailable > 0
    if risk:
        status = "SEC_TEXT_SUPPLY_RISK_REVIEW_REQUIRED"
    elif completed and not incomplete:
        status = "REVIEWED_TEXT_NO_SUPPLY_TERM_NOT_CLEARED"
    elif completed:
        status = "PARTIAL_TEXT_REVIEW_NO_SUPPLY_TERM_NOT_CLEARED"
    else:
        status = "SEC_SUPPLY_TEXT_UNAVAILABLE"
    return {
        "schema_version": "LUCA_V10_SEC_SUPPLY_CONTEXT_1",
        "status": status,
        "dilution_risk_detected": risk,
        "signals": signals,
        "reviewed_documents": completed,
        "unavailable_documents": unavailable,
        "unreviewed_filings": unreviewed_filings,
        "shares_outstanding": None,
        "os_verified": False,
        "float_shares": None,
        "float_verified": False,
        "registration_effectiveness_verified": False,
        "remaining_capacity_verified": False,
        "source": "SEC_FILING_TEXT",
        "sec_clearance": False,
        "NO_ORDERS": True,
    }
