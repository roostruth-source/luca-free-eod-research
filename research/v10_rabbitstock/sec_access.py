"""Declared, bounded SEC GET requests; no fallback around access denials."""

from __future__ import annotations

import json
import re
import urllib.request

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = re.compile(r"https://data\.sec\.gov/submissions/CIK\d{10}\.json")
USER_AGENT = re.compile(r"^LUCA-Research [A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
MAX_JSON_BYTES = 4_000_000


def validate_user_agent(value: str) -> str:
    if not USER_AGENT.fullmatch(value or "") or len(value) > 180:
        raise ValueError("sec_declared_contact_required")
    return value


def fetch_sec_json(url: str, user_agent: str, opener=None) -> dict:
    if url != TICKERS_URL and not SUBMISSIONS_URL.fullmatch(url):
        raise ValueError("sec_json_url_not_allowed")
    request = urllib.request.Request(url, headers={
        "User-Agent": validate_user_agent(user_agent),
        "Accept": "application/json", "Accept-Encoding": "identity",
    }, method="GET")
    with (opener or urllib.request.urlopen)(request, timeout=20) as response:
        raw = response.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("sec_json_too_large")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("sec_json_object_required")
    return result
