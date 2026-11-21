"""Measure later IEX daily bars for frozen V10 observations without calling them trades."""

from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import json
import math
import os
from pathlib import Path
import statistics
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
HORIZONS = (1, 3, 5, 10)
MFE_THRESHOLDS_PCT = (5.0, 10.0, 20.0)
BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
MAX_SYMBOLS = 50
MAX_BYTES = 5_000_000
MAX_PAGES = 10


def _time(raw: str) -> datetime:
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("timezone_required")
    return value.astimezone(timezone.utc)


def _valid_price(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _at_least(value: float, threshold: float) -> bool:
    return value >= threshold or math.isclose(value, threshold, rel_tol=1e-12, abs_tol=1e-9)


def fetch_daily_bars(symbols: list[str], start: date, end: date, key: str, secret: str,
                     opener=None, adjustment: str = "raw") -> dict[str, list[dict]]:
    if not symbols or len(symbols) > MAX_SYMBOLS or len(symbols) != len(set(symbols)):
        raise ValueError("invalid_symbol_batch")
    if not key or not secret:
        raise ValueError("alpaca_credentials_required")
    if adjustment not in {"raw", "split"}:
        raise ValueError("invalid_bar_adjustment")
    rows = {symbol: [] for symbol in symbols}
    seen = {symbol: set() for symbol in symbols}
    token = None
    used = set()
    opener = opener or urllib.request.urlopen
    for _ in range(MAX_PAGES):
        params = {
            "symbols": ",".join(symbols), "timeframe": "1Day",
            "start": start.isoformat(), "end": (end + timedelta(days=1)).isoformat(),
            "feed": "iex", "adjustment": adjustment, "sort": "asc", "limit": 10000,
        }
        if token:
            params["page_token"] = token
        request = urllib.request.Request(BARS_URL + "?" + urllib.parse.urlencode(params),
            headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
                     "Accept": "application/json", "User-Agent": "LUCA-V10-RESEARCH-READONLY/1.0"},
            method="GET")
        with opener(request, timeout=30) as response:
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("market_response_too_large")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("bars"), dict):
            raise ValueError("invalid_market_response")
        if not set(payload["bars"]).issubset(rows):
            raise ValueError("unexpected_market_symbol")
        for symbol, bars in payload["bars"].items():
            if not isinstance(bars, list):
                raise ValueError("invalid_market_bars")
            for bar in bars:
                timestamp = _time(bar["t"])
                session = timestamp.astimezone(ET).date().isoformat()
                if session in seen[symbol]:
                    raise ValueError("duplicate_daily_session")
                prices = {field: float(bar[field]) for field in ("o", "h", "l", "c")}
                if not all(_valid_price(value) for value in prices.values()):
                    raise ValueError("invalid_daily_price")
                if prices["l"] > min(prices["o"], prices["c"]) or prices["h"] < max(prices["o"], prices["c"]):
                    raise ValueError("invalid_daily_ohlc")
                seen[symbol].add(session)
                rows[symbol].append({"session_date": session, **prices})
        next_token = payload.get("next_page_token")
        if next_token is None:
            return rows
        if not isinstance(next_token, str) or not next_token or next_token in used:
            raise ValueError("invalid_market_pagination")
        used.add(next_token)
        token = next_token
    raise ValueError("market_pagination_limit")


def fetch_all_daily_bars(symbols: list[str], start: date, end: date, key: str, secret: str,
                         opener=None, adjustment: str = "raw") -> dict[str, list[dict]]:
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("invalid_symbol_universe")
    output = {}
    for index in range(0, len(symbols), MAX_SYMBOLS):
        batch = symbols[index:index + MAX_SYMBOLS]
        output.update(fetch_daily_bars(batch, start, end, key, secret, opener, adjustment))
    return output


def _eligible_sessions(event: dict, bars: list[dict], evaluated_at: datetime) -> list[dict]:
    observed = _time(event["observed_at"]).astimezone(ET)
    cutoff_date = observed.date()
    include_cutoff = observed.time() < time(16, 0)
    evaluated_et = evaluated_at.astimezone(ET)
    completed_today = evaluated_et.time() >= time(16, 15)
    output = []
    for bar in bars:
        session = date.fromisoformat(bar["session_date"])
        if session < cutoff_date or (session == cutoff_date and not include_cutoff):
            continue
        if session > evaluated_et.date() or (session == evaluated_et.date() and not completed_today):
            continue
        output.append(bar)
    return output


def _split_basis_guard(raw_sessions: list[dict], split_sessions: list[dict] | None) -> dict:
    """Detect provider-applied split differences without claiming official verification."""
    if split_sessions is None:
        return {"status": "NOT_CHECKED_LEGACY_CALL", "safe_for_descriptive_scorecard": True}
    raw_dates = [bar["session_date"] for bar in raw_sessions]
    split_dates = [bar["session_date"] for bar in split_sessions]
    if raw_dates != split_dates:
        return {
            "status": "RAW_SPLIT_SESSION_SET_MISMATCH",
            "safe_for_descriptive_scorecard": False,
            "raw_session_count": len(raw_dates),
            "split_session_count": len(split_dates),
        }
    changed = []
    for raw_bar, split_bar in zip(raw_sessions, split_sessions):
        if any(not math.isclose(raw_bar[field], split_bar[field], rel_tol=1e-6,
                                abs_tol=1e-6) for field in ("o", "h", "l", "c")):
            changed.append(raw_bar["session_date"])
    if changed:
        return {
            "status": "PROVIDER_SPLIT_ADJUSTMENT_DETECTED",
            "safe_for_descriptive_scorecard": False,
            "changed_session_dates": changed,
        }
    return {
        "status": "PROVIDER_RAW_SPLIT_PARITY_OBSERVED_NOT_OFFICIAL_VERIFICATION",
        "safe_for_descriptive_scorecard": True,
        "compared_session_count": len(raw_dates),
    }


def _candidate_scope_guard(event: dict) -> dict:
    if "security_scope" not in event:
        return {"status": "LEGACY_SCOPE_MISSING", "eligible": False}
    scope = event.get("security_scope")
    if not isinstance(scope, dict):
        return {"status": "INVALID_SCOPE_CONTEXT", "eligible": False}
    if scope.get("status") != "COMMON_EQUITY_CANDIDATE_SCOPE":
        return {"status": "SECURITY_NOT_COMMON_EQUITY_SCOPE", "eligible": False}
    financial_status = scope.get("financial_status")
    if financial_status not in {"N", "NOT_AVAILABLE"}:
        return {
            "status": "FINANCIAL_STATUS_NOT_ELIGIBLE",
            "eligible": False,
            "financial_status": financial_status,
        }
    return {
        "status": "COMMON_EQUITY_SCOPE_ELIGIBLE",
        "eligible": True,
        "financial_status": financial_status,
    }


def _descriptive_scorecard(records: list[dict], require_model_eligibility: bool = True) -> dict:
    """Summarize mature watchlist outcomes without claiming prediction accuracy."""
    scorecard = {}
    for horizon in HORIZONS:
        key = str(horizon)
        mature = [record["outcomes"][key] for record in records
                  if (not require_model_eligibility or record["eligible_for_model_validation"])
                  and record["outcomes"][key]["status"] == "COMPLETE_IEX_REFERENCE_ONLY"]
        if not mature:
            scorecard[key] = {
                "status": "NO_MATURE_FRESH_OBSERVATIONS",
                "sample_size": 0,
                "mfe_hit_rates_pct": {str(int(threshold)): None
                                      for threshold in MFE_THRESHOLDS_PCT},
            }
            continue
        close_returns = [item["close_return_pct"] for item in mature]
        mfe = [item["mfe_pct"] for item in mature]
        mae = [item["mae_pct"] for item in mature]
        scorecard[key] = {
            "status": "DESCRIPTIVE_ONLY_NOT_PREDICTION_ACCURACY",
            "sample_size": len(mature),
            "positive_close_rate_pct": 100.0 * sum(value > 0 for value in close_returns) / len(mature),
            "average_close_return_pct": statistics.fmean(close_returns),
            "median_close_return_pct": statistics.median(close_returns),
            "average_mfe_pct": statistics.fmean(mfe),
            "average_mae_pct": statistics.fmean(mae),
            "mae_minus_10_or_worse_rate_pct": 100.0 * sum(value <= -10.0 for value in mae) / len(mature),
            "mfe_hit_rates_pct": {
                str(int(threshold)): 100.0 * sum(_at_least(value, threshold) for value in mfe) / len(mature)
                for threshold in MFE_THRESHOLDS_PCT
            },
        }
    return scorecard


def _first_fresh_observation_per_ticker(records: list[dict]) -> list[dict]:
    """Keep one pre-existing frozen observation per ticker for an independent cohort."""
    first = {}
    fresh = [record for record in records if record["eligible_for_model_validation"]]
    for record in sorted(fresh, key=lambda item: (_time(item["observed_at"]), item["ticker"])):
        first.setdefault(record["ticker"], record)
    return list(first.values())


def _first_scope_audit_observation_per_ticker(records: list[dict]) -> list[dict]:
    """Keep one fresh, split-parity-safe record even when candidate scope is blocked."""
    first = {}
    audit = [record for record in records if record["fresh_price_observation"]
             and record["corporate_action_basis_guard"]
             ["safe_for_descriptive_scorecard"] is True]
    for record in sorted(audit, key=lambda item: (_time(item["observed_at"]), item["ticker"])):
        first.setdefault(record["ticker"], record)
    return list(first.values())


def _rank_segment(prefix: str, rank) -> str:
    if type(rank) is not int:
        return f"{prefix}:not_listed"
    if rank <= 10:
        return f"{prefix}:rank_1_10"
    if rank <= 40:
        return f"{prefix}:rank_11_40"
    return f"{prefix}:rank_over_40"


def _segment_labels(record: dict) -> list[str]:
    if not record["candidate_context_recorded"]:
        volume = "volume:legacy_context_missing"
        trades = "trades:legacy_context_missing"
        mover = "mover:legacy_context_missing"
    else:
        groups = record["screener_groups"]
        volume = _rank_segment("volume", groups.get("active_volume"))
        trades = _rank_segment("trades", groups.get("active_trades"))
        if "gainers" in groups and "losers" in groups:
            mover = "mover:conflicting_lists"
        elif "gainers" in groups:
            mover = "mover:gainer"
        elif "losers" in groups:
            mover = "mover:loser"
        else:
            mover = "mover:not_listed"
    spread = record["iex_quote_spread_pct"]
    if spread is None:
        spread_label = "spread:unknown"
    elif spread <= 2:
        spread_label = "spread:0_2_pct"
    elif spread <= 5:
        spread_label = "spread:over_2_to_5_pct"
    else:
        spread_label = "spread:over_5_pct"
    status = record["sec_status"]
    if status == "RECENT_FILINGS_REQUIRE_REVIEW":
        sec = "sec:recent_filings_require_review"
    elif status.startswith("SEC_NOT_CHECKED") or status == "SEC_SUBMISSIONS_UNAVAILABLE":
        sec = "sec:source_unavailable_or_unchecked"
    else:
        sec = "sec:other_not_cleared"
    if not record["volume_first_context_recorded"]:
        volume_first = "volume_first:legacy_context_missing"
    elif record["volume_first_context"].get("volume_first_recent") is True:
        volume_first = "volume_first:recent_pattern"
    elif record["volume_first_context"].get("status") == "NO_RECENT_VOLUME_FIRST_PATTERN":
        volume_first = "volume_first:no_recent_pattern"
    else:
        volume_first = "volume_first:unavailable_or_not_studied"
    if not record["research_priority_recorded"]:
        priority = "priority:legacy_context_missing"
    else:
        label = record["research_priority"].get("label", "not_computed").lower()
        priority = "priority:" + label
    if not record["security_scope_recorded"]:
        scope = "security_scope:legacy_context_missing"
    else:
        scope = "security_scope:" + record["security_scope"].get(
            "status", "missing").lower()
    if not record["security_scope_recorded"]:
        financial = "financial_status:legacy_context_missing"
    else:
        financial = "financial_status:" + str(record["security_scope"].get(
            "financial_status", "unverified")).lower()
    if record["observation_status"] == "FRESH_PREMARKET_WATCH_ONLY":
        session = "session:premarket"
    elif record["observation_status"] == "FRESH_WATCH_ONLY":
        session = "session:regular"
    else:
        session = "session:stale_or_missing_blocked"
    if not record["issuer_region_context_recorded"]:
        profile = "profile:legacy_context_missing"
    else:
        profile = "profile:" + str(record["issuer_region_context"].get(
            "detector_profile", "unverified")).lower()
    basis = "corporate_action_basis:" + str(record.get(
        "corporate_action_basis_guard", {}).get("status", "legacy_context_missing")).lower()
    cohort_scope = "candidate_scope_guard:" + str(record.get(
        "candidate_scope_guard", {}).get("status", "legacy_context_missing")).lower()
    if not record["listing_action_context_recorded"]:
        listing = ["listing_action:legacy_context_missing"]
    else:
        listing_context = record["listing_action_context"]
        signals = listing_context.get("signals", [])
        if listing_context.get("risk_detected") is True and signals:
            listing = ["listing_action:" + str(signal.get("code", "invalid")).lower()
                       for signal in signals]
        elif listing_context.get("status") == "REVIEWED_TEXT_NO_LISTING_TERM_NOT_CLEARED":
            listing = ["listing_action:no_term_found_not_cleared"]
        else:
            listing = ["listing_action:unavailable_or_partial"]
    if not record["sec_supply_context_recorded"]:
        supply = ["sec_supply:legacy_context_missing"]
        os_segment = "os:legacy_context_missing"
    else:
        supply_context = record["sec_supply_context"]
        if supply_context.get("os_verified") is True:
            os_segment = ("os:verified_point_in_time_stale"
                          if supply_context.get("os_stale") is True else
                          "os:verified_point_in_time_180d_or_less")
        else:
            os_segment = "os:unverified"
        signals = supply_context.get("signals", [])
        if supply_context.get("dilution_risk_detected") is True and signals:
            supply = ["sec_supply:" + str(signal.get("code", "invalid")).lower()
                      for signal in signals]
        elif supply_context.get("status") == "REVIEWED_TEXT_NO_SUPPLY_TERM_NOT_CLEARED":
            supply = ["sec_supply:no_term_found_not_cleared"]
        else:
            supply = ["sec_supply:unavailable_or_partial"]
    return [volume, trades, mover, spread_label, sec, volume_first, priority, scope,
            financial, session, profile, basis, cohort_scope, os_segment, *listing, *supply]


def _segment_scorecards(independent: list[dict], require_model_eligibility: bool = True) -> dict:
    segments = {}
    for record in independent:
        for label in _segment_labels(record):
            segments.setdefault(label, []).append(record)
    output = {}
    for label, records in sorted(segments.items()):
        scorecard = _descriptive_scorecard(records, require_model_eligibility)
        mature_five = scorecard["5"]["sample_size"]
        output[label] = {
            "independent_ticker_count": len(records),
            "comparison_ready": len(records) >= 10 and mature_five >= 10,
            "horizons": scorecard,
        }
    return output


def build_outcomes(ledger: dict, bars: dict[str, list[dict]], evaluated_at: str,
                   split_bars: dict[str, list[dict]] | None = None) -> dict:
    now = _time(evaluated_at)
    if ledger.get("schema_version") != "LUCA_V10_PROSPECTIVE_LEDGER_1" or ledger.get("NO_ORDERS") is not True:
        raise ValueError("invalid_prospective_ledger")
    records = []
    for event in ledger["events"]:
        symbol = event["ticker"]
        entry = event.get("iex_reference_price")
        sessions = _eligible_sessions(event, bars.get(symbol, []), now)
        adjusted_sessions = None if split_bars is None else _eligible_sessions(
            event, split_bars.get(symbol, []), now)
        basis_guard = _split_basis_guard(sessions, adjusted_sessions)
        scope_guard = _candidate_scope_guard(event)
        outcomes = {}
        for horizon in HORIZONS:
            if not _valid_price(entry) or len(sessions) < horizon:
                outcomes[str(horizon)] = {"status": "NOT_MATURE", "completed_sessions": len(sessions)}
                continue
            if basis_guard["safe_for_descriptive_scorecard"] is not True:
                outcomes[str(horizon)] = {
                    "status": "CORPORATE_ACTION_BASIS_BLOCKED",
                    "completed_sessions": len(sessions),
                    "basis_guard_status": basis_guard["status"],
                }
                continue
            window = sessions[:horizon]
            outcomes[str(horizon)] = {
                "status": "COMPLETE_IEX_REFERENCE_ONLY",
                "close_return_pct": (window[-1]["c"] / entry - 1.0) * 100.0,
                "mfe_pct": (max(bar["h"] for bar in window) / entry - 1.0) * 100.0,
                "mae_pct": (min(bar["l"] for bar in window) / entry - 1.0) * 100.0,
                "exit_session": window[-1]["session_date"],
            }
        fresh_price_observation = event["observation_status"] in {
            "FRESH_WATCH_ONLY", "FRESH_PREMARKET_WATCH_ONLY"}
        eligible_for_model = (fresh_price_observation
                              and basis_guard["safe_for_descriptive_scorecard"] is True
                              and scope_guard["eligible"] is True)
        records.append({
            "ticker": symbol, "observed_at": event["observed_at"],
            "event_chain_hash": event["chain_hash"], "entry_reference": entry,
            "observation_status": event["observation_status"],
            "candidate_context_recorded": "screener_groups" in event,
            "screener_groups": event.get("screener_groups", {}),
            "iex_quote_spread_pct": event.get("iex_quote_spread_pct"),
            "sec_status": event.get("sec_status", "SEC_STATUS_MISSING"),
            "volume_first_context_recorded": "volume_first_context" in event,
            "volume_first_context": event.get("volume_first_context", {}),
            "research_priority_recorded": "research_priority" in event,
            "research_priority": event.get("research_priority", {}),
            "security_scope_recorded": "security_scope" in event,
            "security_scope": event.get("security_scope", {}),
            "price_session_context_recorded": "price_session_context" in event,
            "price_session_context": event.get("price_session_context", {}),
            "listing_action_context_recorded": "listing_action_context" in event,
            "listing_action_context": event.get("listing_action_context", {}),
            "sec_supply_context_recorded": "sec_supply_context" in event,
            "sec_supply_context": event.get("sec_supply_context", {}),
            "issuer_region_context_recorded": "issuer_region_context" in event,
            "issuer_region_context": event.get("issuer_region_context", {}),
            "corporate_action_basis_guard": basis_guard,
            "candidate_scope_guard": scope_guard,
            "fresh_price_observation": fresh_price_observation,
            "eligible_for_model_validation": eligible_for_model,
            "outcomes": outcomes,
        })
    fresh = [record for record in records if record["eligible_for_model_validation"]]
    fresh_price = [record for record in records if record["fresh_price_observation"]]
    basis_blocked_fresh = [record for record in fresh_price
                           if record["corporate_action_basis_guard"]
                           ["safe_for_descriptive_scorecard"] is False]
    scope_blocked_fresh = [record for record in fresh_price
                           if record["corporate_action_basis_guard"]
                           ["safe_for_descriptive_scorecard"] is True
                           and record["candidate_scope_guard"]["eligible"] is False]
    mature = {str(h): sum(record["outcomes"][str(h)]["status"] == "COMPLETE_IEX_REFERENCE_ONLY"
                          for record in fresh) for h in HORIZONS}
    independent = _first_fresh_observation_per_ticker(records)
    scope_audit_independent = _first_scope_audit_observation_per_ticker(records)
    independent_mature = {
        str(h): sum(record["outcomes"][str(h)]["status"] == "COMPLETE_IEX_REFERENCE_ONLY"
                    for record in independent) for h in HORIZONS
    }
    scorecard = _descriptive_scorecard(independent)
    segment_scorecards = _segment_scorecards(independent)
    scope_audit_segment_scorecards = _segment_scorecards(
        scope_audit_independent, require_model_eligibility=False)
    sample_size_gate_met = len(independent) >= 30 and independent_mature["5"] >= 30
    corporate_action_basis_verified = False
    split_adjustment_blocked = sum(
        record["corporate_action_basis_guard"]["safe_for_descriptive_scorecard"] is False
        for record in records)
    split_parity_observed = sum(
        record["corporate_action_basis_guard"]["status"] ==
        "PROVIDER_RAW_SPLIT_PARITY_OBSERVED_NOT_OFFICIAL_VERIFICATION"
        for record in records)
    readiness_blockers = []
    if len(independent) < 30:
        readiness_blockers.append("INDEPENDENT_FRESH_TICKERS_BELOW_30")
    if independent_mature["5"] < 30:
        readiness_blockers.append("INDEPENDENT_MATURE_5_SESSION_OUTCOMES_BELOW_30")
    if not corporate_action_basis_verified:
        readiness_blockers.append("CORPORATE_ACTION_BASIS_UNVERIFIED")
    readiness_blockers.extend([
        "IEX_SINGLE_FEED_REFERENCE_ONLY",
        "REAL_FILL_AND_SLIPPAGE_NOT_MEASURED",
    ])
    return {
        "schema_version": "LUCA_V10_PROSPECTIVE_OUTCOMES_1",
        "evaluated_at": now.isoformat(), "ledger_event_count": len(records),
        "fresh_price_observation_count": len(fresh_price),
        "corporate_action_basis_blocked_fresh_observation_count": len(basis_blocked_fresh),
        "candidate_scope_blocked_fresh_observation_count": len(scope_blocked_fresh),
        "fresh_observation_count": len(fresh), "mature_fresh_horizons": mature,
        "independent_fresh_ticker_count": len(independent),
        "repeated_fresh_observation_count": len(fresh) - len(independent),
        "independent_mature_fresh_horizons": independent_mature,
        "independent_cohort_rule": "FIRST_FRESH_OBSERVATION_PER_TICKER",
        "descriptive_candidate_scorecard": scorecard,
        "descriptive_segment_scorecards": segment_scorecards,
        "descriptive_scope_audit_segment_scorecards": scope_audit_segment_scorecards,
        "scope_audit_rule": (
            "FIRST_FRESH_SPLIT_PARITY_SAFE_OBSERVATION_PER_TICKER_NOT_MODEL_COHORT"),
        "segment_comparison_minimum": "10_INDEPENDENT_TICKERS_WITH_MATURE_5_SESSION_OUTCOMES",
        "scorecard_scope": "FIRST_FRESH_OBSERVATION_PER_TICKER_NOT_BUY_SIGNALS",
        "mfe_thresholds_pct_predeclared": list(MFE_THRESHOLDS_PCT),
        "records": records,
        "measurement": "IEX_REFERENCE_PRICE_TO_RAW_IEX_DAILY_BAR_NOT_REAL_FILL",
        "corporate_action_basis_guard": {
            "method": "ALPACA_IEX_RAW_VS_SPLIT_ADJUSTED_PARITY_NOT_OFFICIAL_ACTION_DATA",
            "split_adjustment_blocked_record_count": split_adjustment_blocked,
            "raw_split_parity_observed_record_count": split_parity_observed,
            "official_corporate_action_verification": False,
        },
        "sample_size_gate_met": sample_size_gate_met,
        "sample_size_rule": "30_INDEPENDENT_TICKERS_WITH_MATURE_5_SESSION_OUTCOMES",
        "corporate_action_basis_verified": corporate_action_basis_verified,
        "readiness_blockers": readiness_blockers,
        "performance_validation_ready": (
            sample_size_gate_met and corporate_action_basis_verified
            and not readiness_blockers),
        "prediction_accuracy_verified": False,
        "WATCH_ONLY": True, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
    }


def unavailable(ledger: dict, evaluated_at: str, reason: str) -> dict:
    return {
        "schema_version": "LUCA_V10_PROSPECTIVE_OUTCOMES_1",
        "evaluated_at": _time(evaluated_at).isoformat(),
        "ledger_event_count": len(ledger.get("events", [])), "records": [],
        "source_status": reason,
        "sample_size_gate_met": False,
        "sample_size_rule": "30_INDEPENDENT_TICKERS_WITH_MATURE_5_SESSION_OUTCOMES",
        "corporate_action_basis_verified": False,
        "readiness_blockers": ["OUTCOME_SOURCE_UNAVAILABLE", reason],
        "performance_validation_ready": False,
        "prediction_accuracy_verified": False,
        "WATCH_ONLY": True, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evaluated-at", required=True)
    args = parser.parse_args()
    ledger = json.loads(args.ledger.read_text(encoding="utf-8"))
    symbols = sorted({event["ticker"] for event in ledger.get("events", [])})
    if not symbols:
        report = unavailable(ledger, args.evaluated_at, "NO_LEDGER_EVENTS")
    else:
        try:
            start = min(_time(event["observed_at"]).astimezone(ET).date() for event in ledger["events"])
            end = _time(args.evaluated_at).astimezone(ET).date()
            key, secret = os.getenv("ALPACA_KEY", ""), os.getenv("ALPACA_SECRET", "")
            bars = fetch_all_daily_bars(symbols, start, end, key, secret,
                                        adjustment="raw")
            split_bars = fetch_all_daily_bars(symbols, start, end, key, secret,
                                              adjustment="split")
            report = build_outcomes(ledger, bars, args.evaluated_at, split_bars)
            report["source_status"] = "IEX_RAW_AND_SPLIT_ADJUSTED_DAILY_BARS_COLLECTED"
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            report = unavailable(ledger, args.evaluated_at, type(exc).__name__)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"source": report.get("source_status"),
                      "events": report["ledger_event_count"],
                      "fresh": report.get("fresh_observation_count", 0),
                      "mature_fresh": report.get("mature_fresh_horizons", {}),
                      "ready": report["performance_validation_ready"], "NO_ORDERS": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
