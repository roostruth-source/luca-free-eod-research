"""LUCA V0.3 research-only observer scanner.

Purpose:
- turn the existing auto-discovery + IEX enrichment into one ranked WATCH list;
- never place orders and never convert an unverified name into a buy grade;
- support offline artifact ranking by default;
- permit fresh read-only market GETs only with an explicit environment approval.

This is an observer, not a trading engine.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

from auto_enrich_iex import run as enrich_run

SCHEMA = "LUCA_V03_OBSERVER_WATCHLIST_V1"
MAX_LIMIT = 12
LIVE_APPROVAL_ENV = "LUCA_READ_ONLY_OBSERVER_APPROVED"


def _rank_value(groups, key, fallback=999):
    value = groups.get(key, fallback)
    return value if type(value) is int and value > 0 else fallback


def observation_priority(row):
    """Return a deterministic observation-priority score, never a buy score."""
    if type(row) is not dict:
        raise ValueError("INVALID_ROW")
    symbol = row.get("symbol")
    if type(symbol) is not str or not symbol:
        raise ValueError("INVALID_SYMBOL")
    groups = row.get("screener_groups")
    if type(groups) is not dict:
        raise ValueError("INVALID_SCREENER_GROUPS")

    fresh = row.get("research_status") == "WATCH_ONLY_FRESH_IEX"
    in_band = row.get("price_band_0_20_to_20") is True
    spread = row.get("iex_quote_spread_pct")

    score = 0.0
    reasons = []

    volume_rank = _rank_value(groups, "active_volume")
    if volume_rank < 999:
        add = max(0.0, 42.0 - min(volume_rank, 40) * 0.8)
        score += add
        reasons.append("ACTIVE_VOLUME")

    trade_rank = _rank_value(groups, "active_trades")
    if trade_rank < 999:
        add = max(0.0, 32.0 - min(trade_rank, 40) * 0.6)
        score += add
        reasons.append("ACTIVE_TRADES")

    gain_rank = _rank_value(groups, "gainers")
    if gain_rank < 999:
        add = max(0.0, 20.0 - min(gain_rank, 30) * 0.5)
        score += add
        reasons.append("GAINER")

    loss_rank = _rank_value(groups, "losers")
    if loss_rank < 999:
        add = max(0.0, 8.0 - min(loss_rank, 30) * 0.2)
        score += add
        reasons.append("LOSER_WATCH")

    if fresh:
        score += 15.0
        reasons.append("FRESH_IEX")
    if in_band:
        score += 8.0
        reasons.append("PRICE_0_20_TO_20")

    if type(spread) in (int, float) and math.isfinite(spread) and spread >= 0:
        score += max(-20.0, 8.0 - spread * 2.0)
        reasons.append("SPREAD_MEASURED")
    else:
        score -= 12.0
        reasons.append("SPREAD_UNKNOWN")

    return round(score, 3), reasons


def build_watchlist(enrichment, limit=MAX_LIMIT):
    if type(enrichment) is not dict:
        raise ValueError("INVALID_ENRICHMENT")
    if enrichment.get("schema") != "LUCA_V03_IEX_CANDIDATE_ENRICHMENT_V1":
        raise ValueError("WRONG_ENRICHMENT_SCHEMA")
    if enrichment.get("validation_status") != "NOT_VALIDATED":
        raise ValueError("UNSAFE_VALIDATION_STATUS")
    if enrichment.get("real_trades_allowed") is not False:
        raise ValueError("TRADING_FLAG_MUST_BE_FALSE")
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise ValueError("INVALID_LIMIT")

    rows = enrichment.get("rows")
    if type(rows) is not list:
        raise ValueError("MISSING_ROWS")

    ranked = []
    for row in rows:
        if type(row) is not dict:
            raise ValueError("INVALID_ROW")
        if row.get("buy_allowed") is not False:
            raise ValueError("ROW_BUY_FLAG_MUST_BE_FALSE")
        if row.get("research_status") != "WATCH_ONLY_FRESH_IEX":
            continue
        if row.get("price_band_0_20_to_20") is not True:
            continue
        score, reasons = observation_priority(row)
        ranked.append({
            "symbol": row["symbol"],
            "observation_priority": score,
            "reasons": reasons,
            "iex_last_trade_price": row.get("iex_last_trade_price"),
            "iex_quote_spread_pct": row.get("iex_quote_spread_pct"),
            "screener_groups": row.get("screener_groups", {}),
            "sec_status": "SEC_UNVERIFIED",
            "float_verified": False,
            "market_cap_verified": False,
            "dilution_verified": False,
            "reverse_split_verified": False,
            "buy_allowed": False,
            "grade": "WATCH_ONLY",
        })

    ranked.sort(key=lambda x: (-x["observation_priority"], x["symbol"]))
    selected = ranked[:limit]
    return {
        "schema": SCHEMA,
        "source_schema": enrichment.get("schema"),
        "source_collected_at_utc": enrichment.get("collected_at_utc"),
        "candidate_count": len(selected),
        "candidates": selected,
        "ranking_purpose": "OBSERVATION_PRIORITY_ONLY",
        "early_spike_prediction_verified": False,
        "historical_hit_rate_verified": False,
        "sec_status": "SEC_UNVERIFIED",
        "float_verified": False,
        "dilution_verified": False,
        "reverse_split_verified": False,
        "validation_status": "NOT_VALIDATED",
        "real_trades_allowed": False,
        "orders_allowed": False,
        "warning": (
            "WATCH LIST ONLY. Ranking uses screener/IEX freshness and liquidity clues; "
            "SEC, float, dilution and reverse-split safety are not verified here."
        ),
    }


def run_live_readonly(key, secret, approval, now=None, opener=None, limit=MAX_LIMIT):
    """Fresh GET-only scan; explicit approval is required before any market request."""
    if approval != "YES":
        raise PermissionError("READ_ONLY_MARKET_OBSERVATION_NOT_APPROVED")
    if not key or not secret:
        raise ValueError("NO_API_CREDENTIALS")
    enrichment = enrich_run(key, secret, opener=opener, now=now)
    if enrichment.get("status") != "COLLECTED_UNVERIFIED":
        return {
            "schema": SCHEMA,
            "status": "SOURCE_UNAVAILABLE",
            "source_status": enrichment.get("status"),
            "candidate_count": 0,
            "candidates": [],
            "validation_status": "NOT_VALIDATED",
            "real_trades_allowed": False,
            "orders_allowed": False,
        }
    out = build_watchlist(enrichment, limit=limit)
    out["status"] = "WATCHLIST_CREATED_UNVERIFIED"
    out["market_requests"] = "READ_ONLY_GET"
    return out


def _write_new(path, payload):
    path = Path(path)
    if path.exists():
        raise FileExistsError("NO_OVERWRITE")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf8")


def main():
    p = argparse.ArgumentParser(description="LUCA V0.3 research-only observer scanner")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", help="existing IEX enrichment JSON; no network")
    source.add_argument("--live-readonly", action="store_true",
                        help="fresh GET-only observation; requires explicit env approval")
    p.add_argument("--output", required=True)
    p.add_argument("--limit", type=int, default=MAX_LIMIT)
    args = p.parse_args()

    if args.input:
        enrichment = json.loads(Path(args.input).read_text(encoding="utf8"))
        result = build_watchlist(enrichment, limit=args.limit)
        result["status"] = "OFFLINE_WATCHLIST_CREATED"
        result["market_requests"] = "NONE"
    else:
        result = run_live_readonly(
            os.getenv("ALPACA_KEY", ""),
            os.getenv("ALPACA_SECRET", ""),
            os.getenv(LIVE_APPROVAL_ENV, ""),
            limit=args.limit,
        )

    _write_new(args.output, result)
    print(
        "LUCA_V03_OBSERVER; STATUS=" + str(result.get("status")) +
        "; CANDIDATES=" + str(result.get("candidate_count", 0)) +
        "; NOT_VALIDATED; WATCH_ONLY; NO_ORDERS"
    )


if __name__ == "__main__":
    main()
