"""LUCA V0.3 isolated research-only stock discovery from Alpaca screeners.

No manual ticker list. No order endpoint, no websocket, no SEC safety approval.
These screeners are SIP-based and may require a paid entitlement: HTTP 403 is
NOT silently replaced with IEX or claimed to be live.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

HOST = "https://data.alpaca.markets"
SYMBOL = re.compile(r"^[A-Z][A-Z0-9.\\-]{0,12}$")
SOURCES = {
    "active_volume": "/v1beta1/screener/stocks/most-actives?top=40&by=volume",
    "active_trades": "/v1beta1/screener/stocks/most-actives?top=40&by=trades",
    "movers": "/v1beta1/screener/stocks/movers?top=30",
}
MAX_CANDIDATES = 140
UTC = dt.timezone.utc
NY = ZoneInfo("America/New_York")


def valid_symbol(raw):
    return type(raw) is str and SYMBOL.fullmatch(raw) is not None


def parse_source(name, data):
    if type(data) is not dict:
        raise ValueError("INVALID_SCREENER_RESPONSE")
    if name in ("active_volume", "active_trades"):
        records = data.get("most_actives")
        if type(records) is not list or len(records) > 100:
            raise ValueError("MISSING_MOST_ACTIVES")
        groups = [(name, records)]
    elif name == "movers":
        if type(data.get("gainers")) is not list or type(data.get("losers")) is not list:
            raise ValueError("MISSING_MOVERS")
        if len(data["gainers"]) > 50 or len(data["losers"]) > 50:
            raise ValueError("TOO_MANY_MOVERS")
        groups = [("gainers", data["gainers"]), ("losers", data["losers"])]
    else:
        raise ValueError("UNKNOWN_SOURCE")
    output = []
    for group, records in groups:
        for index, row in enumerate(records):
            if type(row) is not dict or not valid_symbol(row.get("symbol")):
                raise ValueError("INVALID_SYMBOL")
            output.append((row["symbol"], group, index+1))
    return output


def discover(responses, received_at):
    """Never infer small-cap, float, spread, realtime access or SEC safety."""
    if type(responses) is not dict or set(responses) != set(SOURCES):
        raise ValueError("INCOMPLETE_SCREENER_SOURCES")
    if not isinstance(received_at, dt.datetime) or received_at.tzinfo is None:
        raise ValueError("RECEIPT_TIMESTAMP_REQUIRED")
    observed = received_at.astimezone(NY)
    local_minute = observed.hour * 60 + observed.minute
    market_open_window = (observed.weekday() < 5 and
                          9*60+30 <= local_minute < 16*60)
    merged = {}
    for name in SOURCES:
        for symbol, group, rank in parse_source(name, responses[name]):
            item = merged.setdefault(symbol, {"symbol": symbol, "source_groups": {},
                                              "research_watch_only": True,
                                              "market_cap_verified": False,
                                              "float_verified": False,
                                              "sec_verified": False,
                                              "buy_allowed": False})
            item["source_groups"][group] = rank
    if not merged:
        raise ValueError("EMPTY_SCREENER_UNIVERSE")
    if len(merged) > MAX_CANDIDATES:
        raise ValueError("CANDIDATE_CAP_EXCEEDED")
    rows = list(merged.values())
    # First look for high turnover; not a prediction or a small-cap classification.
    rows.sort(key=lambda x: (
        "active_volume" not in x["source_groups"],
        "active_trades" not in x["source_groups"],
        x["source_groups"].get("active_volume", 999),
        x["source_groups"].get("active_trades", 999),
        x["symbol"],
    ))
    return {
        "schema": "LUCA_V03_AUTODISCOVERY_RESEARCH_V1",
        "collected_at_utc": received_at.astimezone(UTC).isoformat(),
        "new_york_date": observed.date().isoformat(),
        "new_york_session_hint": "REGULAR_WEEKDAY_NOT_HOLIDAY_VERIFIED"
                                 if market_open_window else "OUTSIDE_REGULAR_OR_WEEKEND",
        "feed": "ALPACA_SCREENER_SIP_REQUIRES_ENTITLEMENT",
        "freshness": "NOT_PROVEN",
        "all_us_stocks_scanned": False,
        "early_spike_predicted": False,
        "source_count": len(SOURCES),
        "candidate_count": len(rows),
        "candidates": rows,
        "missing_symbol_manual_input": True,
        "sec_status": "SEC_UNVERIFIED",
        "validation_status": "NOT_VALIDATED",
        "real_trades_allowed": False,
        "note": "Screeners show already active/moving names; not proven early signals. "
                "No live entitlement or full-market coverage claims.",
    }


def fetch_screener(path, key, secret, opener=None):
    if path not in SOURCES.values():
        raise ValueError("NON_ALLOWLISTED_API_PATH")
    if not key or not secret:
        raise ValueError("NO_API_CREDENTIALS")
    opener = opener or urllib.request.urlopen
    req = urllib.request.Request(HOST+path, headers={
        "APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json", "User-Agent": "LUCA-RESEARCH-GET-ONLY/0.3",
    }, method="GET")
    with opener(req, timeout=25) as response:
        raw = response.read(1_500_001)
    if len(raw) > 1_500_000:
        raise ValueError("SCREENER_RESPONSE_TOO_LARGE")
    return json.loads(raw)


def collect(key, secret, opener=None, now=None):
    responses = {}
    status = {}
    for name, path in SOURCES.items():
        try:
            responses[name] = fetch_screener(path, key, secret, opener=opener)
            status[name] = "OK"
        except urllib.error.HTTPError as exc:
            status[name] = "HTTP_"+str(exc.code)
        except Exception as exc:
            status[name] = "FAILED_"+type(exc).__name__
    if any(v != "OK" for v in status.values()):
        return {
            "schema": "LUCA_V03_AUTODISCOVERY_RESEARCH_V1",
            "status": "NOT_VALIDATED", "discovery_status": "UNAVAILABLE",
            "source_status": status, "candidate_count": 0, "candidates": [],
            "real_trades_allowed": False, "sec_status": "SEC_UNVERIFIED",
            "reason": "ALL_SOURCES_REQUIRED_NO_SILENT_FALLBACK",
        }
    out = discover(responses, now or dt.datetime.now(UTC))
    out["source_status"] = status
    out["discovery_status"] = "COLLECTED_UNVERIFIED"
    return out


def main():
    output = pathlib.Path(os.environ.get("LUCA_DISCOVERY_OUTPUT", "luca_v03_discovery"))
    output.mkdir(parents=True, exist_ok=True)
    key, secret = os.environ.get("ALPACA_KEY", ""), os.environ.get("ALPACA_SECRET", "")
    if not key or not secret:
        print("RESULT: NO_KEYS; NOT_VALIDATED; NO_ORDERS")
        raise SystemExit(2)
    result = collect(key, secret)
    path = output/"discovery.json"
    if path.exists():
        raise FileExistsError("NO_OVERWRITE")
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf8")
    print("RESULT: DISCOVERY_"+result["discovery_status"]+
          "; CANDIDATES="+str(result["candidate_count"])+
          "; SOURCES="+json.dumps(result["source_status"], sort_keys=True)+
          "; NOT_VALIDATED; NO_ORDERS")
    if result["discovery_status"] != "COLLECTED_UNVERIFIED":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
