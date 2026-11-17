"""LUCA research release gate. Offline tests never authorize trading."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

BLOCKERS = [
    "MARKET_UNIVERSE_NOT_VERIFIED",
    "SEC_CONTRACT_TERMS_NOT_VERIFIED",
    "POINT_IN_TIME_FLOAT_NOT_VERIFIED",
    "CORPORATE_ACTIONS_NOT_VERIFIED",
    "DELISTED_SYMBOL_COVERAGE_NOT_VERIFIED",
    "OUT_OF_SAMPLE_PERFORMANCE_NOT_VERIFIED",
    "EXECUTION_COSTS_NOT_VERIFIED",
]


def check(root, output):
    root = Path(root).resolve()
    try:
        run = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-q"],
            cwd=root, capture_output=True, text=True, timeout=120, check=False,
        )
        log = (run.stdout + "\n" + run.stderr)[-5000:]
        match = re.search(r"Ran\s+(\d+)\s+tests?\s+in\s+", log)
        test_count = int(match.group(1)) if match else 0
        passed = run.returncode == 0 and test_count > 0
        error = None if passed else ("NO_TESTS_DISCOVERED" if test_count == 0 else "OFFLINE_TESTS_FAILED")
        exit_code = run.returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        log = str(exc)[-5000:]
        test_count, passed, exit_code, error = 0, False, -1, "TEST_RUNNER_ERROR"

    report = {
        "status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "orders_enabled": False,
        "production_approved": False,
        "tests_passed": passed,
        "tests_discovered": test_count,
        "test_exit_code": exit_code,
        "test_error": error,
        "release_blockers": BLOCKERS,
        "test_output": log,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="release_status.json")
    args = parser.parse_args()
    result = check(args.root, args.output)
    print("TESTS_OK" if result["tests_passed"] else "TESTS_FAILED", "PRODUCTION_BLOCKED")
    sys.exit(0 if result["tests_passed"] else 1)
