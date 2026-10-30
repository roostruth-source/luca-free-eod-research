"""Synthetic-only spread and slippage sensitivity. NEVER proves execution."""
from __future__ import annotations
import math


def scenario(bid, ask, quantity, slippage_bps=0, halted=False):
    """Illustrate hypothetical buy then sell, without orders or live quotes."""
    values = (bid, ask, quantity, slippage_bps)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("INVALID_SYNTHETIC_INPUT")
    if bid <= 0 or ask <= bid or quantity <= 0 or slippage_bps < 0 or slippage_bps > 10000:
        raise ValueError("INVALID_SYNTHETIC_INPUT")
    if type(halted) is not bool:
        raise ValueError("INVALID_HALT_FLAG")
    spread_pct = (ask - bid) / ask * 100
    buy = ask * (1 + slippage_bps / 10000)
    sell = bid * (1 - slippage_bps / 10000)
    return {
        "schema": "LUCA_V03_SYNTHETIC_EXECUTION_SCENARIO_V1",
        "hypothetical_buy": None if halted else buy,
        "hypothetical_sell": None if halted else sell,
        "hypothetical_round_trip_pct": None if halted else (sell / buy - 1) * 100,
        "quoted_spread_pct": spread_pct,
        "quantity": quantity,
        "halt_claim": halted,
        "quote_authenticated": False,
        "halt_verified": False,
        "fill_verified": False,
        "independent_sample_count_verified": 0,
        "aggregate_win_rate_computed": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "operating_mode": "NO_ORDERS",
        "orders_allowed": False,
    }
