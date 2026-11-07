"""Offline-only quote-claim audit; structural consistency is NOT executability.

An OHLCV close or hypothetical signal window never proves a bid/ask quote,
available size, a fill, or a permitted order. Even complete synthetic quote
claims are untrusted; this module never creates an order or calls a provider.
"""
from __future__ import annotations

import datetime as dt
import math

from mobile_outcomes import _time
from offline_signal_observation_window import audit_signal_observation_window

FIELDS = frozenset({
    "session_day_ny", "symbol", "quote_time_utc", "captured_at_utc",
    "bid", "ask", "bid_size", "ask_size", "venue", "provider", "quote_id",
})
MAX_CLAIMS = 500
MAX_QUOTE_AGE_SECONDS = 5


def _instant(value, field):
    if not isinstance(value, str):
        raise ValueError("INVALID_" + field)
    try:
        stamp = dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_" + field) from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("NAIVE_" + field)
    return stamp.astimezone(dt.timezone.utc)


def _positive(value, field):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("INVALID_" + field)
    return float(value)


def _parse_claims(claims):
    if not isinstance(claims, list) or len(claims) > MAX_CLAIMS:
        raise ValueError("INVALID_QUOTE_CLAIM_LIST")
    result = {}
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) != FIELDS:
            raise ValueError("INVALID_QUOTE_CLAIM_FIELDS")
        day, symbol = claim["session_day_ny"], claim["symbol"]
        if not isinstance(day, str) or not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("INVALID_QUOTE_CLAIM_KEY")
        key = (day, symbol)
        if key in result:
            raise ValueError("DUPLICATE_QUOTE_CLAIM")
        for field in ("venue", "provider", "quote_id"):
            if not isinstance(claim[field], str) or not claim[field].strip():
                raise ValueError("INVALID_" + field.upper())
        bid = _positive(claim["bid"], "BID")
        ask = _positive(claim["ask"], "ASK")
        _positive(claim["bid_size"], "BID_SIZE")
        _positive(claim["ask_size"], "ASK_SIZE")
        if bid >= ask:
            raise ValueError("LOCKED_OR_CROSSED_QUOTE_CLAIM")
        quote_time = _instant(claim["quote_time_utc"], "QUOTE_TIME")
        captured = _instant(claim["captured_at_utc"], "CAPTURE_TIME")
        if captured < quote_time:
            raise ValueError("CAPTURE_BEFORE_QUOTE")
        result[key] = (quote_time, captured)
    return result


def audit_quote_claims(sessions, quote_claims=None):
    """Inspect one frozen zero-delay scenario, never certify real execution.

    quote_claims are optional user-supplied *claims*, not authenticated data.
    Rejects malformed/crossed/late/stale claims and unknown candidate keys.
    The frozen T, source-archive validation, holiday and repeated-symbol
    guards are delegated to the existing observation-window audit.
    """
    base = audit_signal_observation_window(sessions, [0], [0], [0])
    if (base["validation_status"] != "NOT_VALIDATED"
            or base["sec_status"] != "SEC_UNVERIFIED"
            or base["all_grades"] != "D"
            or base["operating_mode"] != "NO_ORDERS"
            or base["orders_allowed"] is not False):
        raise ValueError("UNSAFE_OBSERVATION_BASE")
    claims = _parse_claims([] if quote_claims is None else quote_claims)
    candidates = {
        (s["session_day_ny"], r["symbol"])
        for s in base["sessions"] for r in s["scenarios"][0]["rows"]
    }
    if set(claims) - candidates:
        raise ValueError("UNKNOWN_QUOTE_CLAIM_CANDIDATE")

    output = []
    for s in base["sessions"]:
        close = _time(s["scheduled_close_utc"])
        rows = []
        for r in s["scenarios"][0]["rows"]:
            key = (s["session_day_ny"], r["symbol"])
            claim = claims.get(key)
            considered = (None if r["first_hypothetical_review_complete_utc"] is None
                          else _time(r["first_hypothetical_review_complete_utc"]))
            if claim is not None:
                quote_time, captured = claim
                if quote_time >= close or captured >= close:
                    raise ValueError("QUOTE_CLAIM_AT_OR_AFTER_SCHEDULED_CLOSE")
                if considered is None or quote_time < considered:
                    raise ValueError("QUOTE_CLAIM_BEFORE_HYPOTHETICAL_REVIEW")
                if (captured - quote_time).total_seconds() > MAX_QUOTE_AGE_SECONDS:
                    raise ValueError("STALE_QUOTE_CLAIM")
            if r["status"] != "HYPOTHETICAL_OBSERVATION_WINDOW_ONLY":
                status = "NO_FROZEN_OBSERVATION_WINDOW"
            elif claim is None:
                status = "MISSING_QUOTE_EVIDENCE"
            else:
                status = "STRUCTURALLY_PLAUSIBLE_UNVERIFIED_QUOTE_CLAIM"
            rows.append({
                "symbol": r["symbol"],
                "status": status,
                "frozen_signal_ready": r["signal_ready_by_frozen_reference"],
                "hypothetical_review_complete_utc":
                    r["first_hypothetical_review_complete_utc"],
                "quote_claim_supplied": claim is not None,
                "quote_source_authenticated": False,
                "quote_timestamp_externally_verified": False,
                "halt_status_verified": False,
                "quote_executable_verified": False,
                "actual_liquidity_verified": False,
                "fill_price_verified": False,
                "order_ready": False,
                "orders_allowed": False,
            })
        output.append({
            "session_day_ny": s["session_day_ny"],
            "reference_time_utc": s["reference_time_utc"],
            "scheduled_close_utc": s["scheduled_close_utc"],
            "rows": rows,
            "candidate_count": len(rows),
            "missing_quote_evidence_count": sum(
                r["status"] == "MISSING_QUOTE_EVIDENCE" for r in rows
            ),
            "unverified_claim_count": sum(
                r["status"] == "STRUCTURALLY_PLAUSIBLE_UNVERIFIED_QUOTE_CLAIM"
                for r in rows
            ),
        })
    return {
        "schema": "LUCA_V03_OFFLINE_QUOTE_CLAIM_AUDIT_V1",
        "sessions": output,
        "session_count": len(output),
        "claims_supplied": len(claims),
        "quote_claims_are_untrusted": True,
        "quote_source_authenticated": False,
        "real_time_market_status_verified": False,
        "actual_fill_verified": False,
        "independent_sample_count_verified": 0,
        "aggregate_win_rate_computed": False,
        "prediction_accuracy_verified": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "operating_mode": "NO_ORDERS",
        "orders_allowed": False,
        "real_trades_allowed": False,
        "warnings": sorted(set(base["warnings"]) | {
            "UNAUTHENTICATED_QUOTE_CLAIMS_ARE_NOT_EXECUTION_EVIDENCE",
            "NO_LIVE_HALT_OR_LIQUIDITY_VERIFICATION",
            "NO_ORDERS_OR_FILL_PROOF",
            "NO_POOLED_INDEPENDENT_WIN_RATE",
        }),
        "note_ko": (
            "가상 신호가 보여도 호가와 체결은 증명되지 않습니다. "
            "사용자가 넣은 호가 기록은 모양과 시각만 검사하며 실제 시장 자료인지 "
            "확인하지 못합니다. 호가가 빠졌거나 그럴듯해도 주문 가능은 항상 거짓입니다."
        ),
    }
