"""Publish a third-trial archive and leave a machine-readable success/failure file.

The status file is outside the immutable archive so it can be uploaded as a
seven-day fallback even when branch write permission or ``git push`` fails.
Success is recorded only after the remote research-branch ref is read back and
matches the pushed commit.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import re
import shutil
import subprocess

from third_durable_archive import verify_archive


BRANCH = "research/v03-stage24-evidence"
ARCHIVE_PATH = Path("research/v03_stage24/third_archives")
STATUS_SCHEMA = "LUCA_V03_THIRD_ARCHIVE_PUBLISH_STATUS_V1"
UTC = dt.timezone.utc


class PublishFailed(RuntimeError):
    pass


class CommandFailed(RuntimeError):
    def __init__(self, stage, message):
        super().__init__(message)
        self.stage = stage


def _safe_message(value):
    text = re.sub(r"https://[^\s/@]+:[^\s/@]+@", "https://REDACTED@", str(value))
    return " ".join(text.split())[:400]


def _write_status(path, document):
    target = Path(path)
    if target.exists():
        raise FileExistsError("PUBLISH_STATUS_ALREADY_EXISTS")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf8") as output:
        json.dump(document, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")


def _base_status(run_id, raw_present):
    return {
        "schema": STATUS_SCHEMA,
        "run_id": str(run_id),
        "recorded_at_utc": dt.datetime.now(UTC).isoformat(),
        "raw_ohlcv_present_in_actions_fallback": raw_present is True,
        "long_term_archive_committed": False,
        "remote_ref_verified": False,
        "validation_status": "NOT_VALIDATED",
        "sec_status": "SEC_UNVERIFIED",
        "all_grades": "D",
        "real_trades_allowed": False,
        "orders_allowed": False,
    }


def record_failure(status_path, run_id, reason, raw_present=False):
    document = _base_status(run_id, raw_present)
    document.update({
        "status": "FAILED",
        "failure_stage": "PREPARE_DURABLE_ARCHIVE",
        "failure_reason": _safe_message(reason),
    })
    _write_status(status_path, document)
    return document


def _run(run_command, args, cwd, stage, accepted=(0,)):
    result = run_command(
        args, cwd=str(cwd), text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=45)
    if result.returncode not in accepted:
        detail = result.stderr or result.stdout or "command failed"
        raise CommandFailed(stage, _safe_message(detail))
    return result


def publish_archive(repo_root, archive_root, run_id, status_path,
                    run_command=subprocess.run):
    repo = Path(repo_root)
    source = Path(archive_root) / str(run_id)
    raw = source / "iex_raw_ohlcv_evidence.json"
    status = _base_status(run_id, raw.is_file())
    stage = "VALIDATE_ARCHIVE"
    try:
        if not str(run_id).isdecimal():
            raise ValueError("BAD_RUN_ID")
        manifest_path = source / "durable_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf8"))
        archive_status = manifest.get("archive_status")
        if archive_status not in {"COMPLETE_REPLAY_VERIFIED", "INCOMPLETE_FAIL_CLOSED"}:
            raise ValueError("BAD_DURABLE_ARCHIVE_STATUS")
        complete = archive_status == "COMPLETE_REPLAY_VERIFIED"
        verify_archive(source, require_complete=complete)

        stage = "SYNC_RESEARCH_BRANCH"
        _run(run_command, ["git", "config", "user.name", "luca-v03-evidence-bot"], repo, stage)
        _run(run_command, ["git", "config", "user.email",
                           "luca-v03-evidence-bot@users.noreply.github.com"], repo, stage)
        _run(run_command, ["git", "fetch", "origin", BRANCH], repo, stage)
        _run(run_command, ["git", "checkout", BRANCH], repo, stage)
        _run(run_command, ["git", "pull", "--ff-only", "origin", BRANCH], repo, stage)

        stage = "COPY_CREATE_ONLY_ARCHIVE"
        target = repo / ARCHIVE_PATH / str(run_id)
        if target.exists():
            raise FileExistsError("LONG_TERM_ARCHIVE_ALREADY_EXISTS")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)

        stage = "COMMIT_ARCHIVE"
        relative = str(ARCHIVE_PATH / str(run_id))
        _run(run_command, ["git", "add", "--", relative], repo, stage)
        changed = _run(
            run_command, ["git", "diff", "--cached", "--quiet"], repo,
            stage, accepted=(0, 1))
        if changed.returncode != 1:
            raise ValueError("ARCHIVE_NOT_STAGED")
        _run(run_command, [
            "git", "commit", "-m",
            f"research: preserve immutable third IEX evidence run {run_id} [skip ci]",
        ], repo, stage)
        head = _run(
            run_command, ["git", "rev-parse", "HEAD"], repo, stage).stdout.strip()
        if len(head) != 40 or any(char not in "0123456789abcdef" for char in head):
            raise ValueError("BAD_LOCAL_PUBLISH_COMMIT")

        stage = "PUSH_RESEARCH_BRANCH"
        _run(run_command, ["git", "push", "origin", f"HEAD:{BRANCH}"], repo, stage)
        stage = "VERIFY_REMOTE_REF"
        remote = _run(
            run_command,
            ["git", "ls-remote", "origin", f"refs/heads/{BRANCH}"],
            repo, stage).stdout.split()
        if len(remote) < 2 or remote[0] != head or remote[1] != f"refs/heads/{BRANCH}":
            raise ValueError("REMOTE_REF_DID_NOT_MATCH_PUSHED_COMMIT")

        status.update({
            "status": "SUCCESS",
            "failure_stage": None,
            "failure_reason": None,
            "long_term_archive_committed": True,
            "remote_ref_verified": True,
            "published_commit": head,
            "archive_path": relative,
        })
        _write_status(status_path, status)
        return status
    except Exception as exc:
        status.update({
            "status": "FAILED",
            "failure_stage": getattr(exc, "stage", stage),
            "failure_reason": _safe_message(exc),
        })
        _write_status(status_path, status)
        raise PublishFailed(status["failure_stage"] + ":" + status["failure_reason"]) from exc


def verify_success_status(path):
    document = json.loads(Path(path).read_text(encoding="utf8"))
    if (document.get("schema") != STATUS_SCHEMA or
            document.get("status") != "SUCCESS" or
            document.get("long_term_archive_committed") is not True or
            document.get("remote_ref_verified") is not True or
            document.get("raw_ohlcv_present_in_actions_fallback") is not True or
            document.get("validation_status") != "NOT_VALIDATED" or
            document.get("sec_status") != "SEC_UNVERIFIED" or
            document.get("all_grades") != "D" or
            document.get("real_trades_allowed") is not False or
            document.get("orders_allowed") is not False):
        raise ValueError("LONG_TERM_ARCHIVE_NOT_CONFIRMED")
    return document


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--archive-root")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--record-failure")
    parser.add_argument("--raw-present", action="store_true")
    parser.add_argument("--verify-status", action="store_true")
    args = parser.parse_args()
    if args.verify_status:
        result = verify_success_status(args.status)
    elif args.record_failure:
        result = record_failure(
            args.status, args.run_id, args.record_failure, args.raw_present)
    else:
        if not args.archive_root:
            parser.error("--archive-root is required for publication")
        result = publish_archive(
            args.repo_root, args.archive_root, args.run_id, args.status)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
