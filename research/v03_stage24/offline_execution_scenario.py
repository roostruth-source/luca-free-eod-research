"""Synthetic-only spread and slippage sensitivity. NEVER proves execution."""
from __future__ import annotations
import math


def scenario(bid, ask, quantity, slippage_bps=0, halted=False, bid_size=None, ask_size=None):
    """Illustrate hypothetical buy then sell, without orders or live quotes."""
    values = (bid, ask, quantity, slippage_bps)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError("INVALID_SYNTHETIC_INPUT")
    if bid <= 0 or ask <= bid or quantity <= 0 or slippage_bps < 0 or slippage_bps > 10000:
        raise ValueError("INVALID_SYNTHETIC_INPUT")
    for size in (bid_size, ask_size):
        if size is not None and (type(size) not in (int, float) or not math.isfinite(size) or size <= 0):
            raise ValueError("INVALID_SYNTHETIC_DEPTH")
    if type(halted) is not bool:
        raise ValueError("INVALID_HALT_FLAG")
    depth_sufficient = (bid_size is not None and ask_size is not None
                        and quantity <= bid_size and quantity <= ask_size)
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
        "depth_claim_sufficient": depth_sufficient,
        "depth_claim_missing": bid_size is None or ask_size is None,
        "depth_claim_exceeded": ((bid_size is not None and quantity > bid_size)
                                 or (ask_size is not None and quantity > ask_size)),
        "depth_authenticated": False,
        "hypothetical_fill_eligible": False,
        "fill_status": "UNVERIFIED_SCENARIO_NOT_A_FILL",
        "depth_limit_warning": ("INSUFFICIENT_CLAIMED_TOP_OF_BOOK_DEPTH" if
                                (bid_size is not None and quantity > bid_size) or
                                (ask_size is not None and quantity > ask_size) else
                                "MISSING_CLAIMED_TOP_OF_BOOK_DEPTH" if
                                bid_size is None or ask_size is None else
                                "DEPTH_CLAIM_UNAUTHENTICATED"),
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
