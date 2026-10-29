"""Future-only, isolated research review entrypoint with IEX provenance.

Never changes the original one-time workflow or main. The only side effects
are three new JSON files under an explicitly selected research directory.
"""
import datetime as dt
import json
import os
from pathlib import Path

from prospective_iex_research import UTC,check_frozen,write_json_new
from iex_provenance_adapter import fetch_review_with_raw_bars
from iex_timestamp_provenance import write_new
from iex_raw_evidence import build_raw_evidence,write_new as write_raw_new


def review_future_session(directory,now=None,opener=None):
    root=Path(directory)
    frozen=json.loads((root/"frozen_t0.json").read_text(encoding="utf8"))
    checked_at=now if now is not None else dt.datetime.now(UTC)
    names,_,_=check_frozen(frozen,checked_at)
    if not names:
        raise ValueError("NO_FROZEN_CANDIDATES")
    original=root/"forward_review.json"
    extra=root/"iex_timestamp_provenance.json"
    raw_archive=root/"iex_raw_ohlcv_evidence.json"
    if original.exists() or extra.exists() or raw_archive.exists():
        raise FileExistsError("REVIEW_ALREADY_ARCHIVED")
    key,secret=os.environ.get("ALPACA_KEY",""),os.environ.get("ALPACA_SECRET","")
    if not key or not secret:
        raise ValueError("MISSING_READONLY_DATA_CREDENTIALS")
    result,evidence,bars=fetch_review_with_raw_bars(
        frozen,checked_at,key,secret,None,opener)
    if result["real_trades_allowed"] is not False or evidence["real_trades_allowed"] is not False:
        raise ValueError("UNSAFE_REVIEW")
    if result["observed_iex_bars"]!=sum(x["observed_minutes"] for x in evidence["rows"]):
        raise ValueError("REVIEW_PROVENANCE_COUNT_MISMATCH")
    if evidence["frozen_t0_sha256"]!=frozen["sha256"]:
        raise ValueError("FROZEN_HASH_MISMATCH")
    raw_evidence=build_raw_evidence(frozen,result,bars,evidence)
    # Fail closed on any error; never overwrite the original T0 or a prior review.
    try:
        write_raw_new(raw_archive,raw_evidence)
        write_new(extra,evidence)
        write_json_new(original,result)
    except BaseException:
        raw_archive.unlink(missing_ok=True)
        extra.unlink(missing_ok=True)
        original.unlink(missing_ok=True)
        raise
    return result,evidence
