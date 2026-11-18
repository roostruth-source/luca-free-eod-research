"""Join existing read-only discovery with bounded SEC document review."""

from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
from html import escape
import json
import os
from pathlib import Path
import sys
import time
import urllib.error

from sec_document_review import fetch_filing, review_text

V03_DIR = Path(__file__).resolve().parents[1] / "v03_stage24"
sys.path.insert(0, str(V03_DIR))
from auto_enrich_iex import run as enrich_run  # noqa: E402
from sec_auto_triage import (  # noqa: E402
    TICKERS_URL, SUBMISSIONS_ROOT, get_json, ticker_cik_map, triage,
)

MAX_DOCUMENTS = 10
SAFETY = {"WATCH_ONLY": True, "NO_ORDERS": True, "validation_status": "NOT_VALIDATED"}


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
            filing_reviews.append(result)
            if delay:
                time.sleep(delay)
        rows.append({
            "ticker": row["symbol"],
            "iex_price": row.get("iex_price"),
            "sec_status": row["sec_status"],
            "review_filings": filing_reviews,
            "unreviewed_filings": max(0, len(row.get("review_filings", [])) - len(filing_reviews)),
            "float_verified": False,
            "supply_clearance": False,
            "state": "WATCH_ONLY_BLOCKED",
            **SAFETY,
        })
    return {
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
        "rows": rows,
        **SAFETY,
    }


def collect(key: str, secret: str, now: datetime | None = None,
            enrichment_runner=enrich_run, sec_json=get_json,
            fetcher=fetch_filing, delay=0.22) -> dict:
    now = now or datetime.now(timezone.utc)
    if not key or not secret:
        return assemble({"status": "NO_ALPACA_KEYS", "rows": []}, now, fetcher, delay)
    enrichment = enrichment_runner(key, secret, now=now)
    if enrichment.get("status") != "COLLECTED_UNVERIFIED":
        return assemble({"status": "DISCOVERY_UNAVAILABLE", "rows": []}, now, fetcher, delay)
    watch = [row for row in enrichment["rows"] if row["price_band_0_20_to_20"]]
    # Preserve the screener's deterministic order, record exactly what was excluded.
    selected = watch[:50]
    truncated = len(watch) - len(selected)
    bounded = copy.deepcopy(enrichment)
    bounded["rows"] = selected
    try:
        mapping = ticker_cik_map(sec_json(TICKERS_URL))
    except (OSError, ValueError, TypeError, urllib.error.HTTPError) as exc:
        source_status = (f"SEC_TICKER_MAP_HTTP_{exc.code}"
                         if isinstance(exc, urllib.error.HTTPError)
                         else "SEC_TICKER_MAP_UNAVAILABLE")
        result = {"status": source_status, "rows": [
            {"symbol": row["symbol"], "iex_price": row.get("iex_last_trade_price"),
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
    return assemble(result, now, fetcher, delay)


def render_html(report: dict) -> str:
    lines = ["<!doctype html><html lang='ko'><meta charset='utf-8'>",
             "<meta name='viewport' content='width=device-width, initial-scale=1'>",
             "<title>LUCA 실측 관찰 보고</title><style>body{font:16px/1.6 system-ui;max-width:720px;margin:auto;padding:18px;background:#f6f7fb;color:#18202c}article{background:white;border:1px solid #ddd;border-radius:12px;padding:12px;margin:12px 0;overflow-wrap:anywhere}</style><main>",
             "<h1>LUCA 새 종목 관찰</h1>",
             "<p>관찰 전용 · 주문 없음 · 예측 미검증 · SEC 안전 판정 없음</p>",
             "<p>자료 기준: " + escape(report["collected_at"]) + " · 수집 상태: " + escape(report["source_status"]) + "</p>"]
    lines.append("<p>가격 조건 후보 " + str(report["price_band_total"]) + "개 중 "
                 + str(report["candidate_count"]) + "개 관찰 · 한도 초과 "
                 + str(report["truncated_candidates"]) + "개</p>")
    if not report["rows"]:
        lines.append("<p>이번 실행에서는 새 후보 자료를 확보하지 못했습니다.</p>")
    for row in report["rows"]:
        terms = sorted({m["term"] for f in row["review_filings"] for m in f.get("matched_terms", [])})
        lines.append("<article><h2>" + escape(row["ticker"]) + "</h2><p>" + escape(row["state"])
                     + " · SEC: " + escape(row["sec_status"]) + "</p><p>문서 키워드: "
                     + escape(", ".join(terms) or "확인 없음/미확인") + "</p></article>")
    lines.append("<p>스크리너 일부 후보만 다룹니다. 공시 키워드는 계약 조건·현재 잔여 수량의 확정 근거가 아닙니다.</p></main></html>")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--html-output", type=Path, required=True)
    args = parser.parse_args()
    report = collect(os.getenv("ALPACA_KEY", ""), os.getenv("ALPACA_SECRET", ""))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.html_output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.html_output.write_text(render_html(report), encoding="utf-8")
    print(json.dumps({"status": report["source_status"], "candidates": report["candidate_count"], **SAFETY}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
