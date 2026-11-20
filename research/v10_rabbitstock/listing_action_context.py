"""Conservative SEC-text listing and reverse-split risk context.

Keyword evidence is sufficient to hold a candidate for manual review, but is
never sufficient to claim a current deficiency, an effective delisting date,
or a completed reverse split.  Missing and partial reviews remain unverified.
"""

from __future__ import annotations

from datetime import datetime, timezone


RISK_TERMS = {
    "REVERSE_SPLIT": "역분할 언급",
    "MINIMUM_BID": "최저주가 요건 언급",
    "LISTING_DEFICIENCY": "상장요건 미달 통지 언급",
    "DELISTING_OR_HEARING": "상장폐지·청문 절차 언급",
}
MAX_REVIEWS = 2
MAX_SIGNALS = 8


def _time(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("listing_evidence_timestamp_required")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("listing_evidence_timestamp_invalid") from exc
    if value.tzinfo is None:
        raise ValueError("listing_evidence_timezone_required")
    return value.astimezone(timezone.utc)


def build(review_filings: list[dict], unreviewed_filings: int,
          asof: datetime) -> dict:
    if not isinstance(asof, datetime) or asof.tzinfo is None:
        raise ValueError("listing_context_asof_timezone_required")
    if (not isinstance(review_filings, list)
            or len(review_filings) > MAX_REVIEWS
            or type(unreviewed_filings) is not int
            or unreviewed_filings < 0):
        raise ValueError("invalid_listing_review_coverage")

    signals = []
    completed = 0
    unavailable = 0
    asof_utc = asof.astimezone(timezone.utc)
    for review in review_filings:
        if not isinstance(review, dict):
            raise ValueError("invalid_listing_review")
        accepted = _time(review.get("accepted_at_utc"))
        if accepted > asof_utc:
            raise ValueError("future_listing_evidence_not_allowed")
        source_url = review.get("source_url")
        form = review.get("form")
        if not isinstance(source_url, str) or not source_url.startswith(
                "https://www.sec.gov/Archives/edgar/data/"):
            raise ValueError("official_sec_listing_source_required")
        if not isinstance(form, str) or not form:
            raise ValueError("listing_evidence_form_required")
        matched = review.get("matched_terms")
        if not isinstance(matched, list):
            unavailable += 1
            continue
        completed += 1
        for match in matched:
            if not isinstance(match, dict):
                raise ValueError("invalid_listing_term_match")
            term = match.get("term")
            if term not in RISK_TERMS:
                continue
            context = match.get("context")
            if not isinstance(context, str) or not context:
                raise ValueError("listing_term_context_required")
            signals.append({
                "code": term,
                "ko": RISK_TERMS[term],
                "form": form,
                "accepted_at_utc": accepted.isoformat(),
                "source_url": source_url,
                "context": context[:300],
            })
            if len(signals) > MAX_SIGNALS:
                raise ValueError("listing_signal_cap_exceeded")

    risk = bool(signals)
    incomplete = unreviewed_filings > 0 or unavailable > 0
    if risk:
        status = "SEC_TEXT_LISTING_OR_SPLIT_RISK_REVIEW_REQUIRED"
    elif completed and not incomplete:
        status = "REVIEWED_TEXT_NO_LISTING_TERM_NOT_CLEARED"
    elif completed:
        status = "PARTIAL_TEXT_REVIEW_NO_LISTING_TERM_NOT_CLEARED"
    else:
        status = "SEC_LISTING_TEXT_UNAVAILABLE"
    return {
        "schema_version": "LUCA_V10_LISTING_ACTION_CONTEXT_1",
        "status": status,
        "risk_detected": risk,
        "signals": signals,
        "reviewed_documents": completed,
        "unavailable_documents": unavailable,
        "unreviewed_filings": unreviewed_filings,
        "source": "SEC_FILING_TEXT",
        "current_status_confirmed": False,
        "effective_date_confirmed": False,
        "sec_clearance": False,
        "NO_ORDERS": True,
    }
