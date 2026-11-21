"""Extract point-in-time outstanding shares from an official SEC Company Facts payload.

The SEC fact is historical disclosure evidence, not a real-time share count.  To
avoid same-day look-ahead, a fact filed on date D becomes usable at 00:00 UTC on
D+1.  EntityPublicFloat is intentionally ignored because that concept is a USD
market value, not a number of freely tradable shares.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import math
from urllib.parse import urlsplit


SCHEMA = "LUCA_V10_SEC_OS_CONTEXT_1"
CONCEPT = "EntityCommonStockSharesOutstanding"
MAX_FACTS = 5000
MAX_CURRENT_RATIO_AGE_DAYS = 180


def _utc(raw: object, label: str) -> datetime:
    if not isinstance(raw, str):
        raise ValueError(label + "_timestamp_required")
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(label + "_timestamp_invalid") from exc
    if value.tzinfo is None:
        raise ValueError(label + "_timezone_required")
    return value.astimezone(timezone.utc)


def _day(raw: object, label: str) -> date:
    if not isinstance(raw, str):
        raise ValueError(label + "_date_required")
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(label + "_date_invalid") from exc


def _source(raw: object, cik: int) -> str:
    if not isinstance(raw, str):
        raise ValueError("companyfacts_source_required")
    parsed = urlsplit(raw)
    expected = f"/api/xbrl/companyfacts/CIK{cik:010d}.json"
    if (parsed.scheme != "https" or parsed.netloc != "data.sec.gov"
            or parsed.path != expected or parsed.query or parsed.fragment
            or parsed.username or parsed.password):
        raise ValueError("companyfacts_source_not_official")
    return raw


def _base(status: str, source_url: str, retrieved_at: str) -> dict:
    return {
        "schema_version": SCHEMA,
        "status": status,
        "shares_outstanding": None,
        "os_verified": False,
        "os_asof_date": None,
        "os_filed_date": None,
        "os_knowable_at_utc": None,
        "os_form": None,
        "os_accession": None,
        "os_source_url": source_url,
        "os_retrieved_at_utc": retrieved_at,
        "os_basis": "SEC_COMPANYFACTS_POINT_IN_TIME",
        "os_age_days": None,
        "os_stale": None,
        "os_current_enough_for_ratio": False,
        "float_shares": None,
        "float_verified": False,
        "float_basis": "NOT_DERIVED_ENTITY_PUBLIC_FLOAT_IS_USD_VALUE",
        "NO_ORDERS": True,
    }


def extract(payload: dict, source_url: str, retrieved_at_utc: str,
            asof: datetime) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("companyfacts_payload_object_required")
    if not isinstance(asof, datetime) or asof.tzinfo is None:
        raise ValueError("companyfacts_asof_timezone_required")
    asof_utc = asof.astimezone(timezone.utc)
    cik = payload.get("cik")
    if type(cik) is not int or not 1 <= cik <= 9_999_999_999:
        raise ValueError("companyfacts_cik_invalid")
    source_url = _source(source_url, cik)
    retrieved = _utc(retrieved_at_utc, "companyfacts_retrieved")
    if retrieved > asof_utc:
        raise ValueError("future_companyfacts_retrieval_not_allowed")

    facts = payload.get("facts")
    if not isinstance(facts, dict):
        raise ValueError("companyfacts_facts_object_required")
    dei = facts.get("dei")
    if not isinstance(dei, dict) or CONCEPT not in dei:
        return _base("SEC_COMPANYFACTS_OS_CONCEPT_UNAVAILABLE",
                     source_url, retrieved.isoformat())
    concept = dei[CONCEPT]
    if not isinstance(concept, dict):
        raise ValueError("companyfacts_os_concept_invalid")
    units = concept.get("units")
    if not isinstance(units, dict):
        raise ValueError("companyfacts_os_units_invalid")
    entries = units.get("shares")
    if not isinstance(entries, list) or len(entries) > MAX_FACTS:
        raise ValueError("companyfacts_os_share_facts_invalid")

    usable = []
    identities: dict[tuple[str, str, str, str], int] = {}
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("companyfacts_os_fact_invalid")
        if not all(key in item for key in ("val", "end", "filed", "form", "accn")):
            continue
        raw_value = item["val"]
        if (type(raw_value) not in (int, float) or not math.isfinite(raw_value)
                or raw_value <= 0 or float(raw_value).is_integer() is not True):
            raise ValueError("companyfacts_os_value_invalid")
        value = int(raw_value)
        end = _day(item["end"], "companyfacts_os_end")
        filed = _day(item["filed"], "companyfacts_os_filed")
        if end > filed:
            raise ValueError("companyfacts_os_end_after_filing")
        form = item["form"]
        accession = item["accn"]
        if not isinstance(form, str) or not form or not isinstance(accession, str) or not accession:
            raise ValueError("companyfacts_os_identity_invalid")
        identity = (end.isoformat(), filed.isoformat(), form, accession)
        prior = identities.setdefault(identity, value)
        if prior != value:
            raise ValueError("companyfacts_os_conflicting_duplicate")
        knowable = datetime.combine(filed + timedelta(days=1), time.min,
                                    tzinfo=timezone.utc)
        if knowable <= asof_utc:
            usable.append((knowable, end, accession, value, filed, form))
    if not usable:
        return _base("SEC_COMPANYFACTS_OS_UNAVAILABLE_ASOF",
                     source_url, retrieved.isoformat())
    knowable, end, accession, value, filed, form = max(usable)
    age_days = (asof_utc.date() - end).days
    stale = age_days > MAX_CURRENT_RATIO_AGE_DAYS
    result = _base("SEC_COMPANYFACTS_OS_VERIFIED_POINT_IN_TIME",
                   source_url, retrieved.isoformat())
    result.update({
        "shares_outstanding": value,
        "os_verified": True,
        "os_asof_date": end.isoformat(),
        "os_filed_date": filed.isoformat(),
        "os_knowable_at_utc": knowable.isoformat(),
        "os_form": form,
        "os_accession": accession,
        "os_age_days": age_days,
        "os_stale": stale,
        "os_current_enough_for_ratio": not stale,
    })
    return result
