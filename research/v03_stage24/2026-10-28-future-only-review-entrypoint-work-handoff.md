# LUCA V0.3 — future-only IEX review integration checkpoint

## What changed in research branch
- New `research/v03_stage24/future_iex_review.py` exposes `review_future_session(directory, now=None, opener=None)`.
- It reads a **pre-existing immutable T0 freeze**, checks same 16-minute timing gate, refuses missing candidates and existing review artifacts **before any HTTP**, calls optional GET provenance adapter once, validates frozen hash and bar counts, and archives both the unchanged `forward_review.json` and additional `iex_timestamp_provenance.json`. On failure, avoids a partially published provenance artifact where possible.
- New `research/v03_stage24/test_future_iex_review.py`: 10 synthetic tests, including no duplicate GET, unchanged T0, empty IEX response, missing credentials, tampered T0, failed pagination, and no extra files.
- Offline-only CI `.github/workflows/luca-v03-future-review-ci.yml` run https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40539096406 (check result before claiming success).
- The existing **live one-time workflow remains untouched**. No new live session, no schedule, no alerts, no orders.

## Important Work integration caveats
- This entrypoint is **a callable module**, not yet connected to any live workflow. Review and reuse Work's existing implementation if it already exists.
- No robust atomic two-file transaction exists here; in an unexpected process termination between writes, one file may exist. A future production-quality version should write both files in a dedicated immutable per-run artifact directory and validate/recover partial results. Existing fail-closed checks prevent duplicate HTTP if a file exists.
- No 2026-10-27 old artifacts can be retroactively given timestamp-level detail. Missing IEX minute still means **unknown cause**; IEX single venue, not SIP.
- Any future independent actual trial must preserve freeze, original signal logic, data access terms, notification restrictions, and research-only separation.
- Validation: software-only, NOT_VALIDATED, SEC_UNVERIFIED, all D, NO_ORDERS.
