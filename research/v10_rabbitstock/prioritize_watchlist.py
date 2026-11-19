"""Transparent research-only priority ordering for V10 watchlist rows."""

from __future__ import annotations

import copy
import math

LABELS = {
    "PRIORITY_1_RESEARCH": "우선 관찰",
    "PRIORITY_2_WATCH": "일반 관찰",
    "PRIORITY_3_LOW_EVIDENCE": "근거 부족",
    "HOLD_STALE_OR_MISSING_PRICE": "가격 확인 전 보류",
    "HOLD_OUT_OF_SCOPE_OR_UNVERIFIED": "종목 종류 확인 전 보류",
    "HOLD_FINANCIAL_OR_LISTING_STATUS": "거래소 상태 위험 보류",
}
def _rank_points(rank, maximum: int) -> int:
    if type(rank) is not int or rank < 1:
        return 0
    return max(0, maximum + 1 - rank)


def prioritize(report: dict) -> dict:
    if (report.get("NO_ORDERS") is not True
            or report.get("validation_status") != "NOT_VALIDATED"):
        raise ValueError("unsafe_watchlist_report")
    output = copy.deepcopy(report)
    rows = output.get("rows")
    if not isinstance(rows, list) or len(rows) > 50:
        raise ValueError("invalid_watchlist_rows")
    seen = set()
    for row in rows:
        ticker = row.get("ticker")
        if not isinstance(ticker, str) or ticker in seen:
            raise ValueError("invalid_or_duplicate_ticker")
        seen.add(ticker)
        if row.get("NO_ORDERS") is not True:
            raise ValueError("unsafe_watchlist_row")
        groups = row.get("screener_groups", {})
        spread = row.get("iex_quote_spread_pct")
        volume = row.get("volume_first_context", {})
        security_scope = row.get("security_scope", {})
        scope_status = security_scope.get("status")
        common_scope = scope_status == "COMMON_EQUITY_CANDIDATE_SCOPE"
        financial_status = security_scope.get("financial_status")
        financial_risk = security_scope.get("financial_status_risk") is True
        price_context = row.get("price_session_context", {})
        premarket_declared = row.get("iex_status") == "WATCH_ONLY_FRESH_IEX_PREMARKET"
        premarket = (premarket_declared and isinstance(price_context, dict)
                     and price_context.get("status") == row.get("iex_status")
                     and price_context.get("market_session") == "PREMARKET"
                     and price_context.get("trade_fresh") is True
                     and price_context.get("quote_fresh") is True
                     and price_context.get("full_market_quote_verified") is False
                     and price_context.get("NO_ORDERS") is True)
        fresh = row.get("iex_status") == "WATCH_ONLY_FRESH_IEX" or premarket
        score = 0
        reasons = []
        risks = ["SEC_UNVERIFIED", "FLOAT_UNVERIFIED",
                 "CONCURRENT_SCREENER_SELECTION_NOT_EARLY_PROOF"]
        if premarket_declared and not premarket:
            risks.append("PREMARKET_CONTEXT_INVALID")
        if fresh:
            score += 20
            reasons.append({
                "code": "FRESH_PREMARKET_IEX" if premarket else "FRESH_IEX",
                "ko": ("장전 최근 10분 이내 IEX 체결·호가" if premarket
                       else "최근 10분 이내 IEX 가격"),
            })
        if premarket:
            risks.extend(["PREMARKET_SINGLE_EXCHANGE_CONTEXT",
                          "REGULAR_SESSION_VOLUME_PATTERN_UNAVAILABLE"])
        # A regular-session volume pattern is not proof of premarket volume.
        regular_volume_confirmed = (volume.get("volume_first_recent") is True
                                    and not premarket_declared)
        if regular_volume_confirmed:
            score += 35
            reasons.append({"code": "VOLUME_FIRST_RECENT", "ko": "최근 거래량 선행 연구 패턴"})
        elif premarket_declared:
            risks.append("PREMARKET_VOLUME_FIRST_UNVERIFIED")
        else:
            risks.append("VOLUME_FIRST_NOT_CONFIRMED")
        volume_rank = groups.get("active_volume")
        volume_points = _rank_points(volume_rank, 20)
        if volume_points:
            score += volume_points
            reasons.append({"code": "ACTIVE_VOLUME_RANK",
                            "ko": f"거래량 상위 {volume_rank}위"})
        trades_rank = groups.get("active_trades")
        trades_points = _rank_points(trades_rank, 10)
        if trades_points:
            score += trades_points
            reasons.append({"code": "ACTIVE_TRADES_RANK",
                            "ko": f"거래 횟수 상위 {trades_rank}위"})
        if "gainers" in groups:
            score += 5
            reasons.append({"code": "MOVER_GAINER", "ko": "상승 종목 목록 포함"})
        if spread is not None:
            if type(spread) not in (int, float) or not math.isfinite(spread) or spread < 0:
                raise ValueError("invalid_priority_spread")
            if spread <= 2:
                score += 10
                reasons.append({"code": "TIGHT_IEX_SPREAD", "ko": "IEX 호가 차이 2% 이하"})
            elif spread <= 5:
                score += 5
                reasons.append({"code": "MODERATE_IEX_SPREAD", "ko": "IEX 호가 차이 5% 이하"})
            else:
                score -= 10
                risks.append("WIDE_IEX_SPREAD")
        else:
            risks.append("IEX_SPREAD_UNKNOWN")
        score = max(0, min(100, score)) if fresh and common_scope and not financial_risk else 0
        if not common_scope:
            label = "HOLD_OUT_OF_SCOPE_OR_UNVERIFIED"
            risks.append(scope_status or "SYMBOL_SCOPE_UNVERIFIED")
        elif financial_risk:
            label = "HOLD_FINANCIAL_OR_LISTING_STATUS"
            risks.append("NASDAQ_FINANCIAL_STATUS_" + str(financial_status or "UNKNOWN"))
        elif not fresh:
            label = "HOLD_STALE_OR_MISSING_PRICE"
            risks.append("PRICE_STALE_OR_MISSING")
        elif premarket:
            label = "PRIORITY_2_WATCH" if score >= 40 else "PRIORITY_3_LOW_EVIDENCE"
        elif regular_volume_confirmed and score >= 60:
            label = "PRIORITY_1_RESEARCH"
        elif score >= 40:
            label = "PRIORITY_2_WATCH"
        else:
            label = "PRIORITY_3_LOW_EVIDENCE"
        row.update({
            "research_priority_score": score,
            "research_priority_label": label,
            "research_priority_ko": LABELS[label],
            "priority_reasons": reasons,
            "risk_flags": list(dict.fromkeys(risks)),
            "priority_is_buy_signal": False,
            "buy_allowed": False,
        })
    rows.sort(key=lambda row: (
        row["research_priority_label"].startswith("HOLD_"),
        -row["research_priority_score"], row["ticker"]))
    for index, row in enumerate(rows, 1):
        row["research_priority_rank"] = index
    output["priority_summary"] = {
        label: sum(row["research_priority_label"] == label for row in rows)
        for label in LABELS
    }
    output["priority_formula_status"] = "PREDECLARED_RESEARCH_ORDER_NOT_BUY_SIGNAL"
    output["priority_score_validated"] = False
    return output
