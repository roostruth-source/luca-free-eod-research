"""Route a live candidate to the China 1.0 research cohort using SEC text only."""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit


MAX_REVIEWS = 2


def _time(raw: object) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("issuer_region_timestamp_required")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("issuer_region_timestamp_invalid") from exc
    if value.tzinfo is None:
        raise ValueError("issuer_region_timezone_required")
    return value.astimezone(timezone.utc)


def _official_url(raw: object) -> str:
    if not isinstance(raw, str):
        raise ValueError("issuer_region_sec_source_required")
    parsed = urlsplit(raw)
    if (parsed.scheme != "https" or parsed.netloc != "www.sec.gov"
            or not parsed.path.startswith("/Archives/edgar/data/")
            or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError("issuer_region_sec_source_required")
    return raw


def build(review_filings: list[dict], unreviewed_filings: int,
          asof: datetime) -> dict:
    if not isinstance(asof, datetime) or asof.tzinfo is None:
        raise ValueError("issuer_region_asof_timezone_required")
    if (not isinstance(review_filings, list) or len(review_filings) > MAX_REVIEWS
            or type(unreviewed_filings) is not int or unreviewed_filings < 0):
        raise ValueError("invalid_issuer_region_review_coverage")
    signals = []
    completed = 0
    unavailable = 0
    asof_utc = asof.astimezone(timezone.utc)
    for review in review_filings:
        if not isinstance(review, dict):
            raise ValueError("invalid_issuer_region_review")
        accepted = _time(review.get("accepted_at_utc"))
        if accepted > asof_utc:
            raise ValueError("future_issuer_region_evidence_not_allowed")
        source_url = _official_url(review.get("source_url"))
        form = review.get("form")
        if not isinstance(form, str) or not form:
            raise ValueError("issuer_region_form_required")
        matched = review.get("matched_terms")
        if not isinstance(matched, list):
            unavailable += 1
            continue
        completed += 1
        for match in matched:
            if not isinstance(match, dict):
                raise ValueError("invalid_issuer_region_match")
            if match.get("term") != "PRC_OPERATIONS":
                continue
            context = match.get("context")
            if not isinstance(context, str) or not context:
                raise ValueError("issuer_region_context_required")
            signals.append({
                "code": "PRC_OPERATIONS",
                "ko": "PRC Operations(중국 사업 운영) SEC 문구",
                "form": form,
                "accepted_at_utc": accepted.isoformat(),
                "source_url": source_url,
                "context": context[:300],
            })
            if len(signals) > MAX_REVIEWS:
                raise ValueError("issuer_region_signal_cap_exceeded")
    evidence = bool(signals)
    incomplete = unreviewed_filings > 0 or unavailable > 0
    if evidence:
        status = "SEC_TEXT_PRC_OPERATIONS_CANDIDATE"
    elif completed and not incomplete:
        status = "REVIEWED_TEXT_NO_PRC_OPERATIONS_NOT_PROOF"
    elif completed:
        status = "PARTIAL_TEXT_REVIEW_NO_PRC_OPERATIONS_NOT_PROOF"
    else:
        status = "SEC_ISSUER_REGION_TEXT_UNAVAILABLE"
    return {
        "schema_version": "LUCA_V10_ISSUER_REGION_CONTEXT_1",
        "status": status,
        "detector_profile": "CHINA_1_0" if evidence else "NASDAQ_7_0",
        "issuer_region": "PRC_OPERATIONS" if evidence else "UNVERIFIED",
        "signals": signals,
        "reviewed_documents": completed,
        "unavailable_documents": unavailable,
        "unreviewed_filings": unreviewed_filings,
        "official_sec_text_evidence": evidence,
        "current_operating_region_confirmed": False,
        "classification_is_buy_signal": False,
        "NO_ORDERS": True,
    }
