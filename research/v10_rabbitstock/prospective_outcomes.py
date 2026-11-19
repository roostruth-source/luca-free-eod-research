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
                     opener=None) -> dict[str, list[dict]]:
    if not symbols or len(symbols) > MAX_SYMBOLS or len(symbols) != len(set(symbols)):
        raise ValueError("invalid_symbol_batch")
    if not key or not secret:
        raise ValueError("alpaca_credentials_required")
    rows = {symbol: [] for symbol in symbols}
    seen = {symbol: set() for symbol in symbols}
    token = None
    used = set()
    opener = opener or urllib.request.urlopen
    for _ in range(MAX_PAGES):
        params = {
            "symbols": ",".join(symbols), "timeframe": "1Day",
            "start": start.isoformat(), "end": (end + timedelta(days=1)).isoformat(),
            "feed": "iex", "adjustment": "raw", "sort": "asc", "limit": 10000,
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
                         opener=None) -> dict[str, list[dict]]:
    if not symbols or len(symbols) != len(set(symbols)):
        raise ValueError("invalid_symbol_universe")
    output = {}
    for index in range(0, len(symbols), MAX_SYMBOLS):
        batch = symbols[index:index + MAX_SYMBOLS]
        output.update(fetch_daily_bars(batch, start, end, key, secret, opener))
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


def _descriptive_scorecard(records: list[dict]) -> dict:
    """Summarize mature watchlist outcomes without claiming prediction accuracy."""
    scorecard = {}
    for horizon in HORIZONS:
        key = str(horizon)
        mature = [record["outcomes"][key] for record in records
                  if record["eligible_for_model_validation"]
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
    return [volume, trades, mover, spread_label, sec]


def _segment_scorecards(independent: list[dict]) -> dict:
    segments = {}
    for record in independent:
        for label in _segment_labels(record):
            segments.setdefault(label, []).append(record)
    output = {}
    for label, records in sorted(segments.items()):
        scorecard = _descriptive_scorecard(records)
        mature_five = scorecard["5"]["sample_size"]
        output[label] = {
            "independent_ticker_count": len(records),
            "comparison_ready": len(records) >= 10 and mature_five >= 10,
            "horizons": scorecard,
        }
    return output


def build_outcomes(ledger: dict, bars: dict[str, list[dict]], evaluated_at: str) -> dict:
    now = _time(evaluated_at)
    if ledger.get("schema_version") != "LUCA_V10_PROSPECTIVE_LEDGER_1" or ledger.get("NO_ORDERS") is not True:
        raise ValueError("invalid_prospective_ledger")
    records = []
    for event in ledger["events"]:
        symbol = event["ticker"]
        entry = event.get("iex_reference_price")
        sessions = _eligible_sessions(event, bars.get(symbol, []), now)
        outcomes = {}
        for horizon in HORIZONS:
            if not _valid_price(entry) or len(sessions) < horizon:
                outcomes[str(horizon)] = {"status": "NOT_MATURE", "completed_sessions": len(sessions)}
                continue
            window = sessions[:horizon]
            outcomes[str(horizon)] = {
                "status": "COMPLETE_IEX_REFERENCE_ONLY",
                "close_return_pct": (window[-1]["c"] / entry - 1.0) * 100.0,
                "mfe_pct": (max(bar["h"] for bar in window) / entry - 1.0) * 100.0,
                "mae_pct": (min(bar["l"] for bar in window) / entry - 1.0) * 100.0,
                "exit_session": window[-1]["session_date"],
            }
        eligible_for_model = event["observation_status"] == "FRESH_WATCH_ONLY"
        records.append({
            "ticker": symbol, "observed_at": event["observed_at"],
            "event_chain_hash": event["chain_hash"], "entry_reference": entry,
            "observation_status": event["observation_status"],
            "candidate_context_recorded": "screener_groups" in event,
            "screener_groups": event.get("screener_groups", {}),
            "iex_quote_spread_pct": event.get("iex_quote_spread_pct"),
            "sec_status": event.get("sec_status", "SEC_STATUS_MISSING"),
            "eligible_for_model_validation": eligible_for_model,
            "outcomes": outcomes,
        })
    fresh = [record for record in records if record["eligible_for_model_validation"]]
    mature = {str(h): sum(record["outcomes"][str(h)]["status"] == "COMPLETE_IEX_REFERENCE_ONLY"
                          for record in fresh) for h in HORIZONS}
    independent = _first_fresh_observation_per_ticker(records)
    independent_mature = {
        str(h): sum(record["outcomes"][str(h)]["status"] == "COMPLETE_IEX_REFERENCE_ONLY"
                    for record in independent) for h in HORIZONS
    }
    scorecard = _descriptive_scorecard(independent)
    segment_scorecards = _segment_scorecards(independent)
    return {
        "schema_version": "LUCA_V10_PROSPECTIVE_OUTCOMES_1",
        "evaluated_at": now.isoformat(), "ledger_event_count": len(records),
        "fresh_observation_count": len(fresh), "mature_fresh_horizons": mature,
        "independent_fresh_ticker_count": len(independent),
        "repeated_fresh_observation_count": len(fresh) - len(independent),
        "independent_mature_fresh_horizons": independent_mature,
        "independent_cohort_rule": "FIRST_FRESH_OBSERVATION_PER_TICKER",
        "descriptive_candidate_scorecard": scorecard,
        "descriptive_segment_scorecards": segment_scorecards,
        "segment_comparison_minimum": "10_INDEPENDENT_TICKERS_WITH_MATURE_5_SESSION_OUTCOMES",
        "scorecard_scope": "FIRST_FRESH_OBSERVATION_PER_TICKER_NOT_BUY_SIGNALS",
        "mfe_thresholds_pct_predeclared": list(MFE_THRESHOLDS_PCT),
        "records": records,
        "measurement": "IEX_REFERENCE_PRICE_TO_RAW_IEX_DAILY_BAR_NOT_REAL_FILL",
        "corporate_action_basis_verified": False,
        "performance_validation_ready": len(independent) >= 30 and independent_mature["5"] >= 30,
        "prediction_accuracy_verified": False,
        "WATCH_ONLY": True, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
    }


def unavailable(ledger: dict, evaluated_at: str, reason: str) -> dict:
    return {
        "schema_version": "LUCA_V10_PROSPECTIVE_OUTCOMES_1",
        "evaluated_at": _time(evaluated_at).isoformat(),
        "ledger_event_count": len(ledger.get("events", [])), "records": [],
        "source_status": reason, "performance_validation_ready": False,
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
            bars = fetch_all_daily_bars(symbols, start, end, os.getenv("ALPACA_KEY", ""),
                                        os.getenv("ALPACA_SECRET", ""))
            report = build_outcomes(ledger, bars, args.evaluated_at)
            report["source_status"] = "IEX_DAILY_BARS_COLLECTED"
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
