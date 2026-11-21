"""Join existing read-only discovery with bounded SEC document review."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timedelta, timezone
from html import escape
import json
import math
import os
from pathlib import Path
import sys
import time
import urllib.error

from sec_document_review import fetch_filing, review_text
from sec_access import fetch_sec_json, validate_user_agent
from sec_official_bundle import load_bundle_file, validate_official_bundle
from sec_companyfacts_os import extract as extract_companyfacts_os
from listing_action_context import build as build_listing_action_context
from issuer_region_context import build as build_issuer_region_context
from sec_supply_context import build as build_sec_supply_context
from prioritize_watchlist import prioritize
from nasdaq_symbol_scope import collect as collect_symbol_scope
from price_session_context import classify as classify_price_session
from volume_first_live import MAX_SYMBOLS as VOLUME_MAX_SYMBOLS
from volume_first_live import collect as collect_volume_first

V03_DIR = Path(__file__).resolve().parents[1] / "v03_stage24"
sys.path.insert(0, str(V03_DIR))
from auto_enrich_iex import run as enrich_run  # noqa: E402
from sec_auto_triage import TICKERS_URL, SUBMISSIONS_ROOT, ticker_cik_map, triage  # noqa: E402

MAX_DOCUMENTS = 10
SAFETY = {"WATCH_ONLY": True, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED"}
SCREENER_GROUPS = {"active_volume", "active_trades", "gainers", "losers"}


def attach_candidate_context(result: dict, selected: list[dict]) -> dict:
    """Carry frozen screener ranks and IEX spread into V10 without inferring safety."""
    source = {row["symbol"]: row for row in selected}
    for row in result.get("rows", []):
        original = source.get(row["symbol"], {})
        groups = original.get("screener_groups", {})
        if (not isinstance(groups, dict) or len(groups) > len(SCREENER_GROUPS)
                or not set(groups).issubset(SCREENER_GROUPS)
                or any(type(rank) is not int or not 1 <= rank <= 100
                       for rank in groups.values())):
            raise ValueError("invalid_screener_context")
        spread = original.get("iex_quote_spread_pct")
        if (spread is not None
                and (type(spread) not in (int, float) or not math.isfinite(spread)
                     or not 0 <= spread <= 1000)):
            raise ValueError("invalid_iex_spread_context")
        row["screener_groups"] = copy.deepcopy(groups)
        row["iex_quote_spread_pct"] = spread
        row["volume_first_context"] = copy.deepcopy(
            original.get("volume_first_context", {
                "status": "VOLUME_FIRST_CONTEXT_MISSING",
                "volume_first_recent": False,
                "NO_ORDERS": True,
            }))
        row["security_scope"] = copy.deepcopy(
            original.get("security_scope", {
                "status": "SYMBOL_SCOPE_CONTEXT_MISSING",
                "security_name": None,
            }))
        price_context = copy.deepcopy(original.get("price_session_context", {
            "status": row.get("iex_status", "PRICE_FRESHNESS_UNVERIFIED"),
            "market_session": "UNKNOWN", "NO_ORDERS": True,
        }))
        if (not isinstance(price_context, dict)
                or price_context.get("NO_ORDERS") is not True):
            raise ValueError("unsafe_price_session_context")
        row["price_session_context"] = price_context
        row["iex_status"] = price_context["status"]
    sessions = {row.get("price_session_context", {}).get("market_session")
                for row in result.get("rows", [])}
    if len(sessions) == 1:
        result["market_session"] = sessions.pop()
    return result


def attach_volume_first(selected: list[dict], report: dict) -> None:
    if (report.get("schema_version") != "LUCA_V10_VOLUME_FIRST_ASOF_1"
            or report.get("NO_ORDERS") is not True
            or report.get("validation_status") != "NOT_VALIDATED"):
        raise ValueError("unsafe_volume_first_report")
    rows = report.get("rows")
    if not isinstance(rows, list) or len(rows) > VOLUME_MAX_SYMBOLS:
        raise ValueError("invalid_volume_first_rows")
    by_symbol = {}
    for row in rows:
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or symbol in by_symbol:
            raise ValueError("invalid_volume_first_symbol")
        by_symbol[symbol] = row
    allowed = {row["symbol"] for row in selected[:VOLUME_MAX_SYMBOLS]}
    if not set(by_symbol).issubset(allowed):
        raise ValueError("volume_first_symbol_outside_studied_cap")
    for index, row in enumerate(selected):
        symbol = row["symbol"]
        if symbol in by_symbol:
            context = by_symbol[symbol]
        elif index >= VOLUME_MAX_SYMBOLS:
            context = {"status": "NOT_STUDIED_TOP_12_CAP", "volume_first_recent": False,
                       "NO_ORDERS": True}
        else:
            context = {"status": report["status"], "volume_first_recent": False,
                       "NO_ORDERS": True}
        row["volume_first_context"] = copy.deepcopy(context)


def attach_security_scope(selected: list[dict], report: dict) -> None:
    if (report.get("schema_version") != "LUCA_V10_SYMBOL_SCOPE_1"
            or report.get("NO_ORDERS") is not True
            or report.get("validation_status") != "NOT_VALIDATED"):
        raise ValueError("unsafe_symbol_scope_report")
    rows = report.get("rows")
    if not isinstance(rows, list) or len(rows) > 50:
        raise ValueError("invalid_symbol_scope_rows")
    by_symbol = {}
    allowed = {row["symbol"] for row in selected}
    for row in rows:
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or symbol in by_symbol or symbol not in allowed:
            raise ValueError("invalid_symbol_scope_symbol")
        by_symbol[symbol] = row
    for row in selected:
        row["security_scope"] = copy.deepcopy(by_symbol.get(row["symbol"], {
            "status": report["status"], "security_name": None,
            "source_url": None,
        }))


def attach_companyfacts_os(result: dict, bundle_input: dict,
                           asof: datetime) -> None:
    payloads = bundle_input.get("companyfacts", {})
    sources = bundle_input.get("companyfact_sources", {})
    for row in result.get("rows", []):
        symbol = row.get("symbol")
        if symbol not in payloads:
            continue
        source = sources.get(symbol)
        if not isinstance(source, dict):
            raise ValueError("companyfacts_source_metadata_required")
        try:
            row["official_os_context"] = extract_companyfacts_os(
                payloads[symbol], source.get("source_url"),
                source.get("retrieved_at_utc"), asof)
        except ValueError as exc:
            reason = str(exc)[:120]
            row["official_os_context"] = {
                "schema_version": "LUCA_V10_SEC_OS_CONTEXT_1",
                "status": "SEC_COMPANYFACTS_OS_REJECTED_NOT_USED",
                "rejection_reason": reason,
                "shares_outstanding": None, "os_verified": False,
                "os_asof_date": None, "os_filed_date": None,
                "os_knowable_at_utc": None, "os_form": None,
                "os_accession": None,
                "os_source_url": source.get("source_url"),
                "os_retrieved_at_utc": source.get("retrieved_at_utc"),
                "os_basis": "SEC_COMPANYFACTS_POINT_IN_TIME",
                "os_age_days": None, "os_stale": None,
                "os_current_enough_for_ratio": False,
                "float_shares": None, "float_verified": False,
                "float_basis": "NOT_DERIVED_ENTITY_PUBLIC_FLOAT_IS_USD_VALUE",
                "NO_ORDERS": True,
            }
            result.setdefault("companyfacts_os_rejections", {})[symbol] = reason


def assemble(triage: dict, asof: datetime, fetcher=fetch_filing, delay=0.22) -> dict:
    if asof.tzinfo is None:
        raise ValueError("asof_timezone_required")
    rows = []
    document_count = 0
    for row in triage.get("rows", [])[:50]:
        filing_reviews = []
        for filing in row.get("review_filings", [])[:2]:
            if document_count >= MAX_DOCUMENTS:
                break
            accepted = datetime.fromisoformat(filing["accepted_at_utc"].replace("Z", "+00:00"))
            if accepted.tzinfo is None or accepted > asof:
                raise ValueError("future_or_naive_sec_acceptance_not_allowed")
            url = filing["url"]
            document_count += 1
            try:
                result = review_text(fetcher(url), url)
                result["accepted_at_utc"] = accepted.astimezone(timezone.utc).isoformat()
                result["form"] = filing["form"]
            except urllib.error.HTTPError as exc:
                result = {"source_url": url, "status": f"HTTP_{exc.code}_NOT_CLEARED"}
            except (OSError, ValueError, UnicodeError) as exc:
                result = {"source_url": url, "status": type(exc).__name__ + "_NOT_CLEARED"}
            result["accepted_at_utc"] = accepted.astimezone(timezone.utc).isoformat()
            result["form"] = filing["form"]
            filing_reviews.append(result)
            if delay:
                time.sleep(delay)
        unreviewed = max(0, len(row.get("review_filings", [])) - len(filing_reviews))
        listing_context = build_listing_action_context(
            filing_reviews, unreviewed, asof)
        issuer_region_context = build_issuer_region_context(
            filing_reviews, unreviewed, asof)
        supply_context = build_sec_supply_context(
            filing_reviews, unreviewed, asof,
            row.get("official_os_context"))
        rows.append({
            "ticker": row["symbol"],
            "iex_price": row.get("iex_price"),
            "iex_status": row.get("iex_status", "PRICE_FRESHNESS_UNVERIFIED"),
            "sec_status": row["sec_status"],
            "screener_groups": copy.deepcopy(row.get("screener_groups", {})),
            "iex_quote_spread_pct": row.get("iex_quote_spread_pct"),
            "volume_first_context": copy.deepcopy(row.get("volume_first_context", {})),
            "security_scope": copy.deepcopy(row.get("security_scope", {})),
            "price_session_context": copy.deepcopy(row.get("price_session_context", {})),
            "review_filings": filing_reviews,
            "unreviewed_filings": unreviewed,
            "listing_action_context": listing_context,
            "issuer_region_context": issuer_region_context,
            "detector_profile": issuer_region_context["detector_profile"],
            "sec_supply_context": supply_context,
            "float_verified": False,
            "supply_clearance": False,
            "state": "WATCH_ONLY_BLOCKED",
            **SAFETY,
        })
    report = {
        "schema_version": "LUCA_V10_LIVE_WATCHLIST_1",
        "collected_at": asof.astimezone(timezone.utc).isoformat(),
        "source_status": triage.get("status", "UNKNOWN"),
        "discovery_status": "COLLECTED_PARTIAL" if rows else "UNAVAILABLE",
        "candidate_count": len(rows),
        "price_band_total": triage.get("price_band_total", len(rows)),
        "truncated_candidates": triage.get("truncated_candidates", 0),
        "documents_attempted": document_count,
        "coverage": "ALPACA_SCREENER_CANDIDATES_ONLY_NOT_FULL_MARKET",
        "sec_clearance": False,
        "data_quality_status": "SEC_AND_FLOAT_UNVERIFIED",
        "rows": rows,
        **SAFETY,
    }
    report["profile_counts"] = {
        profile: sum(row["detector_profile"] == profile for row in rows)
        for profile in ("NASDAQ_7_0", "CHINA_1_0")
    }
    for key in ("sec_live_fetch_status", "sec_bundle_provenance", "market_session",
                "volume_first_collection_status", "security_scope_collection_status",
                "companyfacts_os_rejections"):
        if key in triage:
            report[key] = triage[key]
    return prioritize(report)


def collect(key: str, secret: str, now: datetime | None = None,
            enrichment_runner=enrich_run, sec_json=None,
            fetcher=None, delay=0.22, sec_user_agent: str = "",
            sec_bundle: dict | None = None,
            volume_context_runner=collect_volume_first,
            symbol_scope_runner=None, clock=None) -> dict:
    clock = clock or (lambda: datetime.now(timezone.utc))
    fixed_asof = now is not None
    started_at = now or clock()
    now = started_at
    if fetcher is None:
        fetcher = lambda url: fetch_filing(url, sec_user_agent)
    if not key or not secret:
        return assemble({"status": "NO_ALPACA_KEYS", "rows": []}, now, fetcher, delay)
    enrichment = enrichment_runner(key, secret, now=now if fixed_asof else None)
    if enrichment.get("status") != "COLLECTED_UNVERIFIED":
        return assemble({"status": "DISCOVERY_UNAVAILABLE", "rows": []}, now, fetcher, delay)
    if not fixed_asof:
        try:
            collected = datetime.fromisoformat(
                enrichment["collected_at_utc"].replace("Z", "+00:00"))
        except (KeyError, AttributeError, ValueError) as exc:
            raise ValueError("enrichment_collection_timestamp_invalid") from exc
        wall_now = clock()
        if (collected.tzinfo is None or collected < started_at
                or collected > wall_now + timedelta(seconds=5)):
            raise ValueError("enrichment_collection_timestamp_out_of_bounds")
        now = collected.astimezone(timezone.utc)
    watch = [row for row in enrichment["rows"] if row["price_band_0_20_to_20"]]
    # Preserve the screener's deterministic order, record exactly what was excluded.
    selected = copy.deepcopy(watch[:50])
    truncated = len(watch) - len(selected)
    for row in selected:
        row["price_session_context"] = classify_price_session(row, now)
    volume_report = volume_context_runner(
        [row["symbol"] for row in selected], key, secret, now)
    attach_volume_first(selected, volume_report)
    if symbol_scope_runner is None:
        symbol_scope_report = {
            "schema_version": "LUCA_V10_SYMBOL_SCOPE_1",
            "status": "SYMBOL_DIRECTORY_NOT_REQUESTED",
            "rows": [], "NO_ORDERS": True, "validation_status": "NOT_VALIDATED",
        }
    else:
        symbol_scope_report = symbol_scope_runner(
            [row["symbol"] for row in selected], now)
    attach_security_scope(selected, symbol_scope_report)
    bounded = copy.deepcopy(enrichment)
    bounded["rows"] = selected
    if sec_json is None:
        try:
            validate_user_agent(sec_user_agent)
        except ValueError:
            result = {"status": "SEC_CONTACT_NOT_CONFIGURED", "rows": [
                {"symbol": row["symbol"], "iex_price": row.get("iex_last_trade_price"),
                 "iex_status": row.get("research_status", "PRICE_FRESHNESS_UNVERIFIED"),
                 "sec_status": "SEC_NOT_CHECKED_CONTACT_REQUIRED", "review_filings": []}
                for row in selected]}
            result["price_band_total"] = len(watch)
            result["truncated_candidates"] = truncated
            result["volume_first_collection_status"] = volume_report["status"]
            result["security_scope_collection_status"] = symbol_scope_report["status"]
            return assemble(attach_candidate_context(result, selected), now, fetcher, delay)
        sec_json = lambda url: fetch_sec_json(url, sec_user_agent)
    try:
        mapping = ticker_cik_map(sec_json(TICKERS_URL))
    except (OSError, ValueError, TypeError, urllib.error.HTTPError) as exc:
        source_status = (f"SEC_TICKER_MAP_HTTP_{exc.code}"
                         if isinstance(exc, urllib.error.HTTPError)
                         else "SEC_TICKER_MAP_UNAVAILABLE")
        if sec_bundle is not None:
            try:
                bundle_input = validate_official_bundle(
                    sec_bundle, now, [row["symbol"] for row in selected])
                result = triage(bounded, bundle_input["ticker_map"],
                                bundle_input["submissions"], now)
                attach_companyfacts_os(result, bundle_input, now)
            except (ValueError, TypeError, AttributeError) as bundle_exc:
                source_status += "_BUNDLE_" + type(bundle_exc).__name__.upper()
            else:
                result["status"] = "SEC_OFFICIAL_BUNDLE_PARTIAL_NOT_CLEARED"
                result["sec_live_fetch_status"] = source_status
                result["sec_bundle_provenance"] = bundle_input["provenance"]
                result["price_band_total"] = len(watch)
                result["truncated_candidates"] = truncated
                result["volume_first_collection_status"] = volume_report["status"]
                result["security_scope_collection_status"] = symbol_scope_report["status"]
                return assemble(attach_candidate_context(result, selected), now, fetcher, delay)
        result = {"status": source_status, "rows": [
            {"symbol": row["symbol"], "iex_price": row.get("iex_last_trade_price"),
             "iex_status": row.get("research_status", "PRICE_FRESHNESS_UNVERIFIED"),
             "sec_status": "SEC_NOT_CHECKED_SOURCE_UNAVAILABLE", "review_filings": []}
            for row in selected]}
    else:
        submissions = {}
        errors = {}
        for row in selected:
            symbol = row["symbol"]
            cik = mapping.get(symbol)
            if cik is None:
                continue
            try:
                if delay:
                    time.sleep(delay)
                submissions[symbol] = sec_json(SUBMISSIONS_ROOT + f"CIK{cik:010d}.json")
            except urllib.error.HTTPError as exc:
                errors[symbol] = f"HTTP_{exc.code}"
                if exc.code in (403, 429):
                    break
            except (OSError, ValueError, TypeError) as exc:
                errors[symbol] = type(exc).__name__
        result = triage(bounded, mapping, submissions, now)
        result["status"] = "SEC_SUBMISSIONS_PARTIAL" if errors else "COLLECTED_PARTIAL_NOT_CLEARED"
        result["sec_fetch_errors"] = errors
    result["price_band_total"] = len(watch)
    result["truncated_candidates"] = truncated
    result["volume_first_collection_status"] = volume_report["status"]
    result["security_scope_collection_status"] = symbol_scope_report["status"]
    return assemble(attach_candidate_context(result, selected), now, fetcher, delay)


def render_html(report: dict) -> str:
    lines = ["<!doctype html><html lang='ko'><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width, initial-scale=1'>",
             "<title>LUCA 실측 관찰 보고</title><style>body{font:16px/1.55 system-ui;max-width:720px;margin:auto;padding:16px;background:#f4f6fa;color:#18202c}article{background:white;border:1px solid #d9deea;border-radius:14px;padding:14px;margin:12px 0;overflow-wrap:anywhere}.rank{font-size:14px;color:#667085}.score{font-size:24px;font-weight:800}.p1{border-left:6px solid #e65100}.p2{border-left:6px solid #1565c0}.hold{opacity:.72}.tag{display:inline-block;background:#eef2f8;border-radius:999px;padding:3px 8px;margin:2px;font-size:13px}.risk{color:#a12b2b}small{color:#667085}</style><main>",
             "<h1>LUCA 새 종목 관찰</h1>",
             "<p>관찰 전용 · 주문 없음 · 예측 미검증 · SEC 안전 판정 없음</p>",
             "<p>자료 기준: " + escape(report["collected_at"]) + " · 수집 상태: " + escape(report["source_status"]) + "</p>"]
    lines.append("<p>가격 조건 후보 " + str(report["price_band_total"]) + "개 중 "
                 + str(report["candidate_count"]) + "개 관찰 · 한도 초과 "
                 + str(report["truncated_candidates"]) + "개</p>")
    if not report["rows"]:
        lines.append("<p>이번 실행에서는 새 후보 자료를 확보하지 못했습니다.</p>")
    for row in report["rows"]:
        os_context = row["sec_supply_context"]
        if os_context.get("os_verified"):
            os_text = (format(os_context["shares_outstanding"], ",")
                       + "주 · SEC 기준일 "
                       + str(os_context.get("os_asof_date") or "미확인")
                       + " · " + str(os_context.get("os_age_days")) + "일 경과"
                       + (" · 오래된 과거값(현재 비율 계산 금지)"
                          if os_context.get("os_stale") else
                          " · 180일 이내 과거값(실시간 아님)"))
        else:
            os_text = ("공식값 미확인 · "
                       + str(os_context.get("os_status") or "미확인"))
        terms = sorted({m["term"] for f in row["review_filings"] for m in f.get("matched_terms", [])})
        label = row["research_priority_label"]
        css = "p1" if label == "PRIORITY_1_RESEARCH" else (
            "p2" if label == "PRIORITY_2_WATCH" else "hold")
        reasons = "".join("<span class='tag'>" + escape(item["ko"]) + "</span>"
                          for item in row["priority_reasons"])
        risks = ", ".join(row["risk_flags"])
        lines.append("<article class='" + css + "'><div class='rank'>관찰 순위 #"
                     + str(row["research_priority_rank"]) + "</div><h2>"
                     + escape(row["ticker"]) + "</h2><div class='score'>"
                     + str(row["research_priority_score"]) + "점 · "
                     + escape(row["research_priority_ko"]) + "</div><p>" + reasons
                     + "</p><p>가격: " + escape(row["iex_status"])
                     + "<br>종목 종류: "
                     + escape(row["security_scope"].get("status", "미확인"))
                     + (" · " + escape(row["security_scope"].get("security_name") or ""))
                     + "<br>거래소 재무상태: "
                     + escape(row["security_scope"].get("financial_status", "미확인"))
                     + " · "
                     + escape(row["security_scope"].get("financial_status_ko", "미확인"))
                     + " (" + escape(row["security_scope"].get(
                         "financial_status_label", "UNVERIFIED")) + ")"
                     + "<br>Volume-First: "
                     + escape(row["volume_first_context"].get("status", "미확인"))
                     + "<br>연구 경로: " + escape(row.get("detector_profile", "NASDAQ_7_0"))
                     + " · " + escape(row["issuer_region_context"].get(
                         "status", "미확인"))
                     + "<br>SEC: " + escape(row["sec_status"])
                     + "<br>공시 키워드: "
                     + escape(", ".join(terms) or "확인 없음/미확인")
                     + "<br>역분할·상장통지: "
                     + escape(row["listing_action_context"].get("status", "미확인"))
                     + (" · " + escape(", ".join(
                         signal["ko"] for signal in
                         row["listing_action_context"].get("signals", [])))
                        if row["listing_action_context"].get("signals") else "")
                     + "<br>SEC 희석위험: "
                     + escape(row["sec_supply_context"].get("status", "미확인"))
                     + (" · " + escape(", ".join(
                         signal["ko"] for signal in
                         row["sec_supply_context"].get("signals", [])))
                        if row["sec_supply_context"].get("signals") else "")
                     + "<br>OS(발행주식 수): "
                     + escape(os_text)
                     + " · Float(유통주식 수): 공식값 미확인"
                     + "</p><p class='risk'>주의: " + escape(risks)
                     + "</p><small>이 점수는 관찰 순서이며 매수 점수가 아닙니다.</small></article>")
    lines.append("<p>스크리너 일부 후보만 다룹니다. 공시 키워드는 계약 조건·현재 잔여 수량의 확정 근거가 아닙니다.</p></main></html>")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--html-output", type=Path, required=True)
    parser.add_argument("--sec-bundle", type=Path)
    args = parser.parse_args()
    sec_bundle = load_bundle_file(args.sec_bundle) if args.sec_bundle else None
    report = collect(os.getenv("ALPACA_KEY", ""), os.getenv("ALPACA_SECRET", ""),
                     sec_user_agent=os.getenv("SEC_USER_AGENT", ""),
                     sec_bundle=sec_bundle,
                     symbol_scope_runner=collect_symbol_scope)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.html_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.html_output.write_text(render_html(report), encoding="utf-8")
    print(json.dumps({"status": report["source_status"],
                      "price_band_total": report["price_band_total"],
                      "candidates": report["candidate_count"],
                      "truncated": report["truncated_candidates"],
                      "data_quality": report["data_quality_status"], **SAFETY}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
