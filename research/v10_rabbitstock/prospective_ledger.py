"""Append-only prospective observations; no hindsight labels or order signals."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

ZERO = "0" * 64
MAX_EVENTS = 5000
SCREENER_GROUPS = {"active_volume", "active_trades", "gainers", "losers"}
PRIORITY_LABELS = {"PRIORITY_1_RESEARCH", "PRIORITY_2_WATCH",
                   "PRIORITY_3_LOW_EVIDENCE", "HOLD_STALE_OR_MISSING_PRICE",
                   "HOLD_OUT_OF_SCOPE_OR_UNVERIFIED",
                   "HOLD_FINANCIAL_OR_LISTING_STATUS", "HOLD_SEC_SUPPLY_RISK"}


def _time(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timezone_required")
    return value.astimezone(timezone.utc)


def _hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def _official_sec_archive_url(raw: object) -> bool:
    if not isinstance(raw, str):
        return False
    parsed = urlsplit(raw)
    return (parsed.scheme == "https" and parsed.netloc == "www.sec.gov"
            and parsed.path.startswith("/Archives/edgar/data/")
            and not parsed.query and not parsed.fragment
            and parsed.username is None and parsed.password is None)


def _official_sec_companyfacts_url(raw: object) -> bool:
    if not isinstance(raw, str):
        return False
    parsed = urlsplit(raw)
    return (parsed.scheme == "https" and parsed.netloc == "data.sec.gov"
            and re.fullmatch(
                r"/api/xbrl/companyfacts/CIK\d{10}\.json", parsed.path) is not None
            and not parsed.query
            and not parsed.fragment and parsed.username is None
            and parsed.password is None)


def _candidate_context(row: dict) -> tuple[dict, float | int | None]:
    groups = row.get("screener_groups", {})
    if (not isinstance(groups, dict) or len(groups) > len(SCREENER_GROUPS)
            or not set(groups).issubset(SCREENER_GROUPS)
            or any(type(rank) is not int or not 1 <= rank <= 100
                   for rank in groups.values())):
        raise ValueError("invalid_screener_context")
    spread = row.get("iex_quote_spread_pct")
    if (spread is not None
            and (type(spread) not in (int, float) or not math.isfinite(spread)
                 or not 0 <= spread <= 1000)):
        raise ValueError("invalid_iex_spread_context")
    return dict(groups), spread


def _volume_first_context(row: dict, observed_at: datetime) -> dict:
    raw = row.get("volume_first_context", {
        "status": "VOLUME_FIRST_CONTEXT_MISSING",
        "volume_first_recent": False,
        "NO_ORDERS": True,
    })
    if not isinstance(raw, dict) or raw.get("NO_ORDERS") is not True:
        raise ValueError("unsafe_volume_first_context")
    status = raw.get("status")
    recent = raw.get("volume_first_recent")
    if not isinstance(status, str) or not status or type(recent) is not bool:
        raise ValueError("invalid_volume_first_context")
    pattern = raw.get("latest_pattern")
    if recent and not isinstance(pattern, dict):
        raise ValueError("volume_first_pattern_required")
    if pattern is not None:
        ratio = pattern.get("iex_volume_ratio")
        change = pattern.get("six_bar_price_change_pct")
        known = pattern.get("bar_knowable_after_utc")
        if (type(ratio) not in (int, float) or not math.isfinite(ratio) or ratio < 0
                or type(change) not in (int, float) or not math.isfinite(change)
                or not isinstance(known, str)):
            raise ValueError("invalid_volume_first_pattern")
        if _time(known) > observed_at:
            raise ValueError("future_volume_first_pattern_not_allowed")
        frozen_pattern = {
            "iex_volume_ratio": ratio,
            "six_bar_price_change_pct": change,
            "bar_knowable_after_utc": known,
        }
    else:
        frozen_pattern = None
    evidence = raw.get("evidence_bars", [])
    if not isinstance(evidence, list) or len(evidence) > 6:
        raise ValueError("invalid_volume_first_evidence")
    frozen_bars = []
    for bar in evidence:
        if not isinstance(bar, dict) or not isinstance(bar.get("t"), str):
            raise ValueError("invalid_volume_first_evidence")
        if _time(bar["t"]) + timedelta(minutes=1) > observed_at:
            raise ValueError("future_volume_first_evidence_not_allowed")
        values = [bar.get(field) for field in ("o", "h", "l", "c")]
        volume = bar.get("v")
        if (any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
                for value in values) or type(volume) is not int or volume < 0):
            raise ValueError("invalid_volume_first_evidence")
        frozen_bars.append({key: bar[key] for key in ("t", "o", "h", "l", "c", "v")})
    return {"status": status, "volume_first_recent": recent,
            "latest_pattern": frozen_pattern, "evidence_bars": frozen_bars,
            "selection_limit": raw.get("selection_limit"), "NO_ORDERS": True}


def _priority_context(row: dict) -> dict:
    if "research_priority_score" not in row:
        return {"status": "PRIORITY_NOT_COMPUTED", "priority_is_buy_signal": False}
    score = row.get("research_priority_score")
    rank = row.get("research_priority_rank")
    label = row.get("research_priority_label")
    reasons = row.get("priority_reasons")
    risks = row.get("risk_flags")
    if (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 100
            or type(rank) is not int or not 1 <= rank <= 50
            or label not in PRIORITY_LABELS
            or row.get("priority_is_buy_signal") is not False
            or row.get("buy_allowed") is not False
            or not isinstance(reasons, list) or len(reasons) > 12
            or not isinstance(risks, list) or len(risks) > 20):
        raise ValueError("invalid_research_priority")
    frozen_reasons = []
    for reason in reasons:
        if (not isinstance(reason, dict) or not isinstance(reason.get("code"), str)
                or not isinstance(reason.get("ko"), str)):
            raise ValueError("invalid_research_priority_reason")
        frozen_reasons.append({"code": reason["code"], "ko": reason["ko"]})
    if any(not isinstance(risk, str) or not risk for risk in risks):
        raise ValueError("invalid_research_priority_risk")
    return {"status": "PREDECLARED_RESEARCH_ORDER_NOT_BUY_SIGNAL",
            "score": score, "rank": rank, "label": label,
            "reasons": frozen_reasons, "risk_flags": list(risks),
            "priority_is_buy_signal": False}


def _security_scope_context(row: dict) -> dict:
    raw = row.get("security_scope", {
        "status": "SYMBOL_SCOPE_CONTEXT_MISSING", "security_name": None,
    })
    if not isinstance(raw, dict) or not isinstance(raw.get("status"), str):
        raise ValueError("invalid_security_scope_context")
    name = raw.get("security_name")
    if name is not None and not isinstance(name, str):
        raise ValueError("invalid_security_scope_name")
    return {key: raw.get(key) for key in (
        "status", "security_name", "etf_flag", "test_issue", "exchange_code",
        "financial_status", "financial_status_label", "financial_status_risk",
        "financial_status_ko", "source_url")}


def _listing_action_context(row: dict, observed_at: datetime) -> dict:
    raw = row.get("listing_action_context", {
        "schema_version": "LUCA_V10_LISTING_ACTION_CONTEXT_1",
        "status": "SEC_LISTING_TEXT_UNAVAILABLE", "risk_detected": False,
        "signals": [], "reviewed_documents": 0, "unavailable_documents": 0,
        "unreviewed_filings": 0, "source": "SEC_FILING_TEXT",
        "current_status_confirmed": False, "effective_date_confirmed": False,
        "sec_clearance": False, "NO_ORDERS": True,
    })
    if (not isinstance(raw, dict)
            or raw.get("schema_version") != "LUCA_V10_LISTING_ACTION_CONTEXT_1"
            or raw.get("NO_ORDERS") is not True
            or raw.get("sec_clearance") is not False
            or raw.get("current_status_confirmed") is not False
            or raw.get("effective_date_confirmed") is not False
            or type(raw.get("risk_detected")) is not bool
            or not isinstance(raw.get("status"), str)
            or raw.get("source") != "SEC_FILING_TEXT"):
        raise ValueError("invalid_or_unsafe_listing_action_context")
    signals = raw.get("signals")
    if not isinstance(signals, list) or len(signals) > 8:
        raise ValueError("invalid_listing_action_signals")
    frozen = []
    for signal in signals:
        if (not isinstance(signal, dict)
                or signal.get("code") not in {"REVERSE_SPLIT", "MINIMUM_BID",
                                               "LISTING_DEFICIENCY",
                                               "DELISTING_OR_HEARING"}
                or not isinstance(signal.get("ko"), str)
                or not isinstance(signal.get("form"), str)
                or not _official_sec_archive_url(signal.get("source_url"))
                or not isinstance(signal.get("context"), str)):
            raise ValueError("invalid_listing_action_signal")
        accepted = _time(signal.get("accepted_at_utc"))
        if accepted > observed_at:
            raise ValueError("future_listing_action_evidence_not_allowed")
        frozen.append({key: signal[key] for key in (
            "code", "ko", "form", "accepted_at_utc", "source_url", "context")})
    if raw["risk_detected"] != bool(frozen):
        raise ValueError("listing_action_risk_mismatch")
    counts = {}
    for key in ("reviewed_documents", "unavailable_documents", "unreviewed_filings"):
        value = raw.get(key)
        if type(value) is not int or value < 0:
            raise ValueError("invalid_listing_action_coverage")
        counts[key] = value
    return {
        "schema_version": raw["schema_version"], "status": raw["status"],
        "risk_detected": raw["risk_detected"], "signals": frozen,
        **counts, "source": raw["source"],
        "current_status_confirmed": False, "effective_date_confirmed": False,
        "sec_clearance": False, "NO_ORDERS": True,
    }


def _sec_supply_context(row: dict, observed_at: datetime) -> dict:
    raw = row.get("sec_supply_context", {
        "schema_version": "LUCA_V10_SEC_SUPPLY_CONTEXT_1",
        "status": "SEC_SUPPLY_TEXT_UNAVAILABLE",
        "dilution_risk_detected": False, "signals": [],
        "reviewed_documents": 0, "unavailable_documents": 0,
        "unreviewed_filings": 0, "shares_outstanding": None,
        "os_verified": False, "float_shares": None, "float_verified": False,
        "registration_effectiveness_verified": False,
        "remaining_capacity_verified": False, "source": "SEC_FILING_TEXT",
        "sec_clearance": False, "NO_ORDERS": True,
    })
    if (not isinstance(raw, dict)
            or raw.get("schema_version") != "LUCA_V10_SEC_SUPPLY_CONTEXT_1"
            or raw.get("NO_ORDERS") is not True
            or raw.get("sec_clearance") is not False
            or type(raw.get("dilution_risk_detected")) is not bool
            or raw.get("float_verified") is not False
            or raw.get("float_shares") is not None
            or raw.get("registration_effectiveness_verified") is not False
            or raw.get("remaining_capacity_verified") is not False
            or raw.get("source") not in {
                "SEC_FILING_TEXT", "SEC_FILING_TEXT_PLUS_COMPANYFACTS"}
            or not isinstance(raw.get("status"), str)):
        raise ValueError("invalid_or_unsafe_sec_supply_context")
    os_verified = raw.get("os_verified")
    shares = raw.get("shares_outstanding")
    if os_verified is False:
        if shares is not None:
            raise ValueError("unverified_os_value_not_allowed")
        frozen_os = {key: None for key in (
            "os_asof_date", "os_filed_date", "os_knowable_at_utc", "os_form",
            "os_accession", "os_source_url", "os_retrieved_at_utc")}
        frozen_os["os_basis"] = raw.get(
            "os_basis", "SEC_COMPANYFACTS_POINT_IN_TIME")
        frozen_os["os_status"] = raw.get(
            "os_status", "SEC_COMPANYFACTS_OS_NOT_AVAILABLE")
        frozen_os["os_rejection_reason"] = raw.get("os_rejection_reason")
        if (not isinstance(frozen_os["os_status"], str)
                or not frozen_os["os_status"]
                or (frozen_os["os_rejection_reason"] is not None
                    and not isinstance(frozen_os["os_rejection_reason"], str))):
            raise ValueError("invalid_unverified_os_status")
    elif os_verified is True:
        if (type(shares) is not int or shares <= 0
                or raw.get("os_basis") != "SEC_COMPANYFACTS_POINT_IN_TIME"
                or raw.get("source") != "SEC_FILING_TEXT_PLUS_COMPANYFACTS"
                or not _official_sec_companyfacts_url(raw.get("os_source_url"))):
            raise ValueError("invalid_verified_os_evidence")
        for key in ("os_asof_date", "os_filed_date", "os_form", "os_accession"):
            if not isinstance(raw.get(key), str) or not raw[key]:
                raise ValueError("verified_os_metadata_required")
        if (_time(raw.get("os_knowable_at_utc")) > observed_at
                or _time(raw.get("os_retrieved_at_utc")) > observed_at):
            raise ValueError("future_verified_os_evidence_not_allowed")
        frozen_os = {key: raw.get(key) for key in (
            "os_asof_date", "os_filed_date", "os_knowable_at_utc", "os_form",
            "os_accession", "os_source_url", "os_retrieved_at_utc", "os_basis")}
        frozen_os["os_status"] = raw.get(
            "os_status", "SEC_COMPANYFACTS_OS_VERIFIED_POINT_IN_TIME")
        frozen_os["os_rejection_reason"] = None
    else:
        raise ValueError("invalid_os_verified_flag")
    signals = raw.get("signals")
    if not isinstance(signals, list) or len(signals) > 10:
        raise ValueError("invalid_sec_supply_signals")
    frozen = []
    for signal in signals:
        if (not isinstance(signal, dict)
                or signal.get("code") not in {"ATM", "ELOC", "CB", "WARRANT", "SHELF"}
                or not isinstance(signal.get("ko"), str)
                or not isinstance(signal.get("form"), str)
                or not _official_sec_archive_url(signal.get("source_url"))
                or not isinstance(signal.get("context"), str)):
            raise ValueError("invalid_sec_supply_signal")
        if _time(signal.get("accepted_at_utc")) > observed_at:
            raise ValueError("future_sec_supply_evidence_not_allowed")
        frozen.append({key: signal[key] for key in (
            "code", "ko", "form", "accepted_at_utc", "source_url", "context")})
    if raw["dilution_risk_detected"] != bool(frozen):
        raise ValueError("sec_supply_risk_mismatch")
    counts = {}
    for key in ("reviewed_documents", "unavailable_documents", "unreviewed_filings"):
        value = raw.get(key)
        if type(value) is not int or value < 0:
            raise ValueError("invalid_sec_supply_coverage")
        counts[key] = value
    return {
        "schema_version": raw["schema_version"], "status": raw["status"],
        "dilution_risk_detected": raw["dilution_risk_detected"],
        "signals": frozen, **counts, "shares_outstanding": shares,
        "os_verified": os_verified, **frozen_os,
        "float_shares": None, "float_verified": False,
        "registration_effectiveness_verified": False,
        "remaining_capacity_verified": False, "source": raw["source"],
        "sec_clearance": False, "NO_ORDERS": True,
    }


def _price_session_context(row: dict, observed_at: datetime) -> dict:
    raw = row.get("price_session_context", {
        "status": row.get("iex_status", "PRICE_SESSION_CONTEXT_MISSING"),
        "market_session": "LEGACY_CONTEXT_MISSING", "NO_ORDERS": True,
    })
    if (not isinstance(raw, dict) or raw.get("NO_ORDERS") is not True
            or not isinstance(raw.get("status"), str)
            or raw.get("status") != row.get("iex_status")):
        raise ValueError("invalid_or_unsafe_price_session_context")
    session = raw.get("market_session")
    if not isinstance(session, str) or not session:
        raise ValueError("invalid_price_market_session")
    frozen = {key: raw.get(key) for key in (
        "status", "market_session", "trade_timestamp_utc", "quote_timestamp_utc",
        "trade_age_seconds", "quote_age_seconds", "trade_fresh", "quote_fresh",
        "full_market_quote_verified", "source", "rejection_reasons")}
    for key in ("trade_timestamp_utc", "quote_timestamp_utc"):
        if frozen[key] is not None and _time(frozen[key]) > observed_at:
            raise ValueError("future_price_session_evidence_not_allowed")
    if frozen["full_market_quote_verified"] is True:
        raise ValueError("full_market_quote_claim_not_allowed")
    if frozen["status"] == "WATCH_ONLY_FRESH_IEX_PREMARKET":
        ages = (frozen["trade_age_seconds"], frozen["quote_age_seconds"])
        if (session != "PREMARKET" or frozen["trade_fresh"] is not True
                or frozen["quote_fresh"] is not True
                or frozen["full_market_quote_verified"] is not False
                or frozen["source"] != "ALPACA_IEX_SINGLE_EXCHANGE_NOT_SIP"
                or any(type(age) not in (int, float) or not math.isfinite(age)
                       or not 0 <= age <= 600 for age in ages)):
            raise ValueError("invalid_premarket_price_evidence")
    frozen["NO_ORDERS"] = True
    return frozen


def append_observations(report: dict, built_at: str, previous: dict | None = None) -> dict:
    now = _time(built_at)
    observed_at = _time(report["collected_at"])
    if observed_at > now:
        raise ValueError("future_watchlist_not_allowed")
    if report.get("NO_ORDERS") is not True or report.get("validation_status") != "NOT_VALIDATED":
        raise ValueError("unsafe_watchlist")
    events = list(previous.get("events", [])) if previous else []
    chain = previous.get("last_chain_hash", ZERO) if previous else ZERO
    if previous:
        if previous.get("schema_version") != "LUCA_V10_PROSPECTIVE_LEDGER_1":
            raise ValueError("previous_ledger_schema_mismatch")
        if previous.get("NO_ORDERS") is not True or _time(previous["built_at"]) > now:
            raise ValueError("previous_ledger_invalid_or_future")
        expected = ZERO
        for event in events:
            actual = event.get("chain_hash")
            item = {key: value for key, value in event.items() if key != "chain_hash"}
            expected = hashlib.sha256((expected + _hash(item)).encode()).hexdigest()
            if actual != expected:
                raise ValueError("previous_ledger_chain_invalid")
        if chain != expected:
            raise ValueError("previous_ledger_head_invalid")
        if events and observed_at < _time(events[-1]["observed_at"]):
            raise ValueError("out_of_order_watchlist")
        if (observed_at == _time(previous["source_collected_at"])
                and _hash(report) != previous["input_report_hash"]):
            raise ValueError("same_time_report_revision_not_allowed")
    if len(events) + len(report["rows"]) > MAX_EVENTS:
        raise ValueError("prospective_ledger_capacity_exceeded")
    known = {(e["ticker"], e["observed_at"]) for e in events}
    new_count = 0
    for row in report["rows"]:
        identity = (row["ticker"], observed_at.isoformat())
        if identity in known:
            continue
        known.add(identity)
        groups, spread = _candidate_context(row)
        volume_first = _volume_first_context(row, observed_at)
        priority = _priority_context(row)
        security_scope = _security_scope_context(row)
        listing_action = _listing_action_context(row, observed_at)
        sec_supply = _sec_supply_context(row, observed_at)
        price_session = _price_session_context(row, observed_at)
        item = {
            "ticker": row["ticker"],
            "observed_at": observed_at.isoformat(),
            "iex_reference_price": row.get("iex_price"),
            "iex_status": row["iex_status"],
            "sec_status": row["sec_status"],
            "screener_groups": groups,
            "iex_quote_spread_pct": spread,
            "volume_first_context": volume_first,
            "research_priority": priority,
            "security_scope": security_scope,
            "listing_action_context": listing_action,
            "sec_supply_context": sec_supply,
            "price_session_context": price_session,
            "observation_status": (
                "FRESH_PREMARKET_WATCH_ONLY"
                if row["iex_status"] == "WATCH_ONLY_FRESH_IEX_PREMARKET"
                else "FRESH_WATCH_ONLY" if row["iex_status"] == "WATCH_ONLY_FRESH_IEX"
                else "STALE_OR_MISSING_PRICE_BLOCKED"),
            "outcome_status": "PENDING_NOT_MATURE",
            "predicted_spike": False,
            "NO_ORDERS": True,
        }
        chain = hashlib.sha256((chain + _hash(item)).encode()).hexdigest()
        events.append({**item, "chain_hash": chain})
        new_count += 1
    return {
        "schema_version": "LUCA_V10_PROSPECTIVE_LEDGER_1",
        "built_at": now.isoformat(),
        "source_collected_at": observed_at.isoformat(),
        "input_report_hash": _hash(report),
        "previous_event_count": len(events) - new_count,
        "new_event_count": new_count,
        "event_count": len(events),
        "continuity_status": "CHAIN_CONTINUED" if previous else "NEW_SERIES_PREVIOUS_UNAVAILABLE",
        "last_chain_hash": chain,
        "events": events,
        "WATCH_ONLY": True, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("watchlist", type=Path)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--built-at", required=True)
    args = parser.parse_args()
    report = json.loads(args.watchlist.read_text(encoding="utf-8"))
    previous = json.loads(args.previous.read_text(encoding="utf-8")) if args.previous else None
    result = append_observations(report, args.built_at, previous)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"new": result["new_event_count"], "total": result["event_count"],
                      "NO_ORDERS": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
