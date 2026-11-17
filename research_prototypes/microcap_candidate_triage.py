"""Conservative microcap candidate triage (research only, no orders).

All inputs are supplied by a separate, auditable data source. Missing SEC,
float, and dilution evidence MUST NOT be silently treated as safe.
"""
from math import isfinite

UNKNOWN_RISKS = ("atm_active", "eloc_active", "cb_active", "warrants_active",
                 "reverse_split_pending", "going_concern")

def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if isfinite(value) else None

def assess(row):
    """Score a candidate without manufacturing SEC or float verification."""
    ticker = row.get("ticker")
    price = _number(row.get("close"))
    previous = _number(row.get("prev_close"))
    volume = _number(row.get("volume"))
    average = _number(row.get("avg_volume_20d"))
    if not isinstance(ticker, str) or not ticker.isascii() or not ticker.isalnum() or len(ticker) > 8:
        raise ValueError("invalid ticker")
    if any(x is None or x <= 0 for x in (price, previous, volume, average)):
        raise ValueError("missing or invalid market data")
    rvol = volume / average
    change = 100 * (price / previous - 1)
    raw_score = (35 if rvol >= 5 else 25 if rvol >= 3 else 15 if rvol >= 1.8 else 0)
    raw_score += 15 if 2 <= change <= 20 else 0
    # No verified point-in-time float and independently reviewed SEC contracts:
    # never upgrade to an actionable signal, regardless of raw score.
    return {
        "ticker": ticker, "close": price, "change_pct": round(change, 3),
        "rvol": round(rvol, 3), "research_score": min(raw_score, 29),
        "sec_status": "UNVERIFIED", "float_shares": None,
        "unknown_risks": list(UNKNOWN_RISKS), "trading_allowed": False,
        "signal": "RESEARCH_ONLY", "validated": False,
        "reason": "volume anomaly" if rvol >= 1.8 else "no volume anomaly",
    }

def rank(rows):
    """Sort valid candidates by evidence-limited score; report rejected rows."""
    candidates, errors = [], []
    for index, row in enumerate(rows):
        try:
            candidates.append(assess(row))
        except (ValueError, TypeError, AttributeError) as exc:
            errors.append({"row": index, "error": str(exc)})
    candidates.sort(key=lambda x: (-x["research_score"], -x["rvol"], x["ticker"]))
    return {"status": "PARTIAL_RESEARCH", "market_wide": False,
            "realtime": False, "validated": False, "orders_enabled": False,
            "candidates": candidates, "errors": errors}
