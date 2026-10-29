"""Network-free synthetic rehearsal of the complete third-trial data path.

The fake opener is the only transport. Output is always labelled synthetic and
is created in a temporary directory by the CLI, never in the real archive path.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile

from iex_provenance_adapter import fetch_review_with_raw_bars
from iex_raw_evidence import (
    build_raw_evidence, replay_raw_evidence, signal_formula_source_sha256,
    write_new as write_raw_new,
)
from iex_timestamp_provenance import write_new as write_timestamp_new
from nyse_session_gate import CALENDAR_MARKERS, CALENDAR_URL, STATUS_URL
from prospective_iex_research import digest_frozen, freeze, write_json_new
from third_durable_archive import build_archive, verify_archive
from third_trial_gate import (
    approval_sha256, validate_with_official_calendar,
    BASELINE_COMMIT, BRANCH, HEADER,
)


UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 29, 14, 0, 5, tzinfo=UTC)
T1 = T0 + dt.timedelta(minutes=17)
EXPECTED_FIND_PATTERNS_SHA256 = "8b51d1b83ccd7791a39b84e69b8df17d04a867587aa23eb325765208e958d3e6"
SYNTHETIC_RUN_ID = "999999"


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, count=-1):
        return self.payload[:count]


class FakeOfficialResponse:
    status = 200

    def __init__(self, url, text):
        self.url = url
        self.payload = text.encode("utf8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, count=-1):
        return self.payload[:count]


def _bar(index, volume=20):
    timestamp = T0.replace(second=0, microsecond=0) + dt.timedelta(minutes=index + 1)
    low = 1.00 + index * .01
    return {
        "t": timestamp.isoformat(), "o": 1.5, "h": 1.7,
        "l": low, "c": 1.5, "v": volume,
    }


def _synthetic_request(nonce):
    expires = T0 + dt.timedelta(minutes=10)
    return (f"{HEADER}\n"
            "session_day_ny=2026-10-29\n"
            f"expires_at_utc={expires.isoformat()}\n"
            f"approval_nonce={nonce}\n"
            f"baseline_commit={BASELINE_COMMIT}\n"
            f"approved_code_commit={BASELINE_COMMIT}\n"
            "research_only=true\n"
            "orders_allowed=false\n")


def run_dry_run(work_root):
    if signal_formula_source_sha256() != EXPECTED_FIND_PATTERNS_SHA256:
        raise ValueError("FIND_PATTERNS_BASELINE_CHANGED")
    root = Path(work_root)
    if root.exists():
        raise FileExistsError("SYNTHETIC_DRY_RUN_ROOT_EXISTS")
    root.mkdir(parents=True)
    nonce = "b" * 64
    calendar_calls = []

    def fake_official_opener(request, timeout):
        calendar_calls.append(request.full_url)
        if request.get_method() != "GET":
            raise AssertionError("SYNTHETIC_CALENDAR_NOT_GET")
        if request.full_url == CALENDAR_URL:
            return FakeOfficialResponse(CALENDAR_URL, " | ".join(CALENDAR_MARKERS))
        if request.full_url == STATUS_URL:
            return FakeOfficialResponse(STATUS_URL, "Market Status System Status Normal")
        raise AssertionError("SYNTHETIC_CALENDAR_UNEXPECTED_URL")

    gate = validate_with_official_calendar(
        _synthetic_request(nonce), T0, "push", BRANCH, "1", 1,
        T0 - dt.timedelta(minutes=1), approval_sha256(nonce), 0,
        BASELINE_COMMIT,
        calendar_opener=fake_official_opener)
    enrichment = {
        "schema": "LUCA_V03_IEX_CANDIDATE_ENRICHMENT_V1",
        "status": "COLLECTED_UNVERIFIED",
        "validation_status": "NOT_VALIDATED",
        "real_trades_allowed": False,
        "collected_at_utc": (T0 - dt.timedelta(seconds=10)).isoformat(),
        "rows": [
            {"symbol": "TESTA", "price_band_0_20_to_20": True,
             "research_status": "WATCH_ONLY_FRESH_IEX", "buy_allowed": False},
            {"symbol": "TESTB", "price_band_0_20_to_20": True,
             "research_status": "WATCH_ONLY_FRESH_IEX", "buy_allowed": False},
        ],
    }
    frozen = freeze(enrichment, T0)
    frozen["synthetic_only"] = True
    frozen["sha256"] = digest_frozen(frozen)
    fake_bars = [_bar(index, 300 if index == 5 else 20) for index in range(12)]
    calls = []

    def fake_opener(request, timeout):
        if request.get_method() != "GET" or "feed=iex" not in request.full_url:
            raise AssertionError("DRY_RUN_NON_READONLY_REQUEST")
        calls.append({"method": request.get_method(), "timeout": timeout})
        return FakeResponse({
            "bars": {"TESTA": fake_bars}, "next_page_token": None,
        })

    review, timestamps, bars = fetch_review_with_raw_bars(
        frozen, T1, "synthetic-key", "synthetic-secret",
        T1 + dt.timedelta(seconds=1), fake_opener)
    raw = build_raw_evidence(frozen, review, bars, timestamps)
    replay = replay_raw_evidence(raw, frozen, review, timestamps)
    evidence = root / "synthetic_evidence"
    write_json_new(evidence / "frozen_t0.json", frozen)
    write_json_new(evidence / "forward_review.json", review)
    write_timestamp_new(evidence / "iex_timestamp_provenance.json", timestamps)
    write_raw_new(evidence / "iex_raw_ohlcv_evidence.json", raw)
    write_json_new(evidence / "replay_result.json", replay)
    archive_root = root / "synthetic_durable_archives"
    archive, manifest = build_archive(
        evidence, archive_root, SYNTHETIC_RUN_ID, BASELINE_COMMIT,
        T1 + dt.timedelta(seconds=2), synthetic_only=True)
    verify_archive(archive)
    return {
        "schema": "LUCA_V03_THIRD_SYNTHETIC_DRY_RUN_V1",
        "synthetic_only": True,
        "internet_or_real_market_api_used": False,
        "fake_get_calls": len(calls),
        "fake_official_calendar_get_calls": len(calendar_calls),
        "gate_passed": gate["allowed"],
        "official_calendar_live_verified":
            gate["nyse_session_calendar"]["official_sources_live_verified"],
        "symbols": review["symbols"],
        "observed_iex_bars": review["observed_iex_bars"],
        "signal_symbols": review["forward_pattern_symbols"],
        "raw_ohlcv_archived": raw["canonical_ohlcv_archived"],
        "replay_exact_match": replay["recorded_review_exact_match"],
        "durable_archive_status": manifest["archive_status"],
        "durable_archive_synthetic_label": manifest["synthetic_only"],
        "find_patterns_source_sha256": signal_formula_source_sha256(),
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "real_trades_allowed": False,
        "orders_allowed": False,
    }


def main():
    with tempfile.TemporaryDirectory(prefix="luca-v03-third-synthetic-") as folder:
        result = run_dry_run(Path(folder) / "run")
    print(json.dumps(result, sort_keys=True))
    print("SYNTHETIC_ONLY; NO_MARKET_API; NOT_VALIDATED; SEC_UNVERIFIED; D; NO_ORDERS")


if __name__ == "__main__":
    main()
