"""Research-only SEC as-of risk gate. Never authorizes trading.

This gate is separate from the frozen Stage20/24 signal rules. It can only
block or label a historical case; it cannot turn a signal into a buy order.
"""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path

STUDY_SYMBOLS = ("GPUS", "LAES", "PFSA", "NIKI", "VCIG")
ALLOWED_RISKS = {"HIGH", "VERY_HIGH", "UNKNOWN"}
EXPECTED_STATUS = "NOT_VALIDATED"


def _iso_day(value: str) -> dt.date:
    if type(value) is not str:
        raise ValueError("DATE_MUST_BE_STRING")
    try:
        date = dt.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_ISO_DAY") from exc
    if date.isoformat() != value:
        raise ValueError("NON_CANONICAL_DAY")
    return date


def annotate_case(case: dict, snapshot: dict) -> dict:
    """Fail closed for unknown, stale, future, missing or unsafe evidence."""
    if type(case) is not dict or type(snapshot) is not dict:
        raise ValueError("INVALID_INPUT")
    symbol = case.get("symbol")
    day = _iso_day(case.get("day"))
    if symbol not in STUDY_SYMBOLS:
        raise ValueError("NOT_STUDY_SYMBOL")
    if snapshot.get("schema") != "LUCA_V03_SEC_ASOF_SNAPSHOT_V1":
        raise ValueError("WRONG_SEC_SCHEMA")
    if snapshot.get("validation_status") != EXPECTED_STATUS:
        raise ValueError("UNSAFE_SEC_SNAPSHOT")
    if snapshot.get("real_trades_allowed") is not False:
        raise ValueError("UNSAFE_TRADING_FLAG")
    snapshot_day = _iso_day(snapshot.get("asof_market_day"))
    if snapshot_day != day:
        raise ValueError("SEC_SNAPSHOT_DAY_MISMATCH")
    symbols = snapshot.get("symbols")
    if type(symbols) is not dict or set(symbols) != set(STUDY_SYMBOLS):
        raise ValueError("INCOMPLETE_SEC_UNIVERSE")
    evidence = symbols[symbol]
    if type(evidence) is not dict or evidence.get("risk") not in ALLOWED_RISKS:
        raise ValueError("UNSAFE_OR_MISSING_SEC_RISK")
    if evidence.get("coverage_complete") is not False:
        raise ValueError("SEC_COVERAGE_MUST_REMAIN_UNVERIFIED")
    filings = evidence.get("filings")
    if type(filings) is not list:
        raise ValueError("FILINGS_MISSING")
    for filing in filings:
        if type(filing) is not dict:
            raise ValueError("INVALID_FILING")
        filing_day = _iso_day(filing.get("filing_date"))
        if filing_day > day:
            raise ValueError("FUTURE_SEC_FILING_LEAKAGE")
        url = filing.get("url")
        if type(url) is not str or not url.startswith("https://www.sec.gov/Archives/edgar/data/"):
            raise ValueError("SEC_SOURCE_NOT_PRIMARY")
    return {
        "day": day.isoformat(),
        "symbol": symbol,
        "sec_risk": evidence["risk"],
        "sec_coverage_complete": False,
        "evidence_filing_dates": [x["filing_date"] for x in filings],
        "historical_research_only": True,
        "actual_buy_allowed": False,
        "buy_grade": "BLOCKED",
        "reason": "DILUTION_RISK" if evidence["risk"] != "UNKNOWN" else "SEC_NOT_VERIFIED",
        "validation_status": EXPECTED_STATUS,
    }


def annotate_replay(replay: dict, snapshot: dict) -> dict:
    """Attach an audit, never mutate frozen replay or original case outcomes."""
    if type(replay) is not dict or replay.get("validation_status") != EXPECTED_STATUS:
        raise ValueError("UNSAFE_REPLAY")
    if replay.get("real_trades_allowed") is not False:
        raise ValueError("UNSAFE_REPLAY_TRADING_FLAG")
    days = replay.get("days_downloaded")
    if type(days) is not list or len(days) != 1:
        raise ValueError("ONE_DAY_SNAPSHOT_ONLY")
    if days[0] != snapshot.get("asof_market_day"):
        raise ValueError("SEC_REPLAY_DATE_MISMATCH")
    cases = replay.get("cases")
    if type(cases) is not list:
        raise ValueError("MISSING_CASES")
    annotated = [annotate_case(case, snapshot) for case in cases]
    return {
        "schema": "LUCA_V03_SEC_RISK_ANNOTATION_V1",
        "asof_market_day": days[0],
        "signal_count": len(annotated),
        "cases": annotated,
        "new_signal_rules_enabled": False,
        "historical_live_alerts_proven": False,
        "real_trades_allowed": False,
        "validation_status": EXPECTED_STATUS,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("replay_json")
    parser.add_argument("snapshot_json")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    replay = json.loads(Path(args.replay_json).read_text(encoding="utf8"))
    snapshot = json.loads(Path(args.snapshot_json).read_text(encoding="utf8"))
    report = annotate_replay(replay, snapshot)
    dest = Path(args.output)
    if dest.exists():
        raise FileExistsError("NO_OVERWRITE")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print("RESULT: SEC_ASOF_FAIL_CLOSED; SIGNALS=", report["signal_count"],
          "; BUY_APPROVALS=0; NOT_VALIDATED")


if __name__ == "__main__":
    main()
