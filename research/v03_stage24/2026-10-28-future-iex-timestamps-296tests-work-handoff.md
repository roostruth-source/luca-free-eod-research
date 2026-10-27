# LUCA V0.3 — 2026-10-28 optional future IEX minute-timestamp provenance (Work handoff)

**Research-only optional module; NOT integrated into live T0; NOT_VALIDATED / SEC_UNVERIFIED / NO_ORDERS.**

## Why
First real NY 2026-10-27 T0 had 12 symbols, 94/168 possible IEX minute bars, 11/12 sparse. Counts alone cannot identify which minutes are missing, whether GET pagination was complete, or whether IEX simply had no trades. No evidence that missing minutes equal HTTP failures. This module is for **future prospective observations only**. It cannot reconstruct past missing timestamps.

## Implemented and verified
- `research/v03_stage24/iex_timestamp_provenance.py`: optional pure function `build_minute_provenance(frozen, review, bars, recorded_at, api_evidence=None)`, with immutable `write_new`.
- It requires the **original T0 freeze and matching prospective review**, rejects candidate drift, changed counts, duplicate/out-of-window timestamps, future or stale recording time, unsafe trading grade, bad pagination/HTTP evidence. Output is bounded to <=12 symbols, <=35-minute windows, <=100kB and records **only observed/missing UTC minute timestamps**, not OHLCV prices.
- HTTP provenance is explicitly **not captured** unless future caller passes actual GET-only HTTP 200 page statuses and terminal page token absent. A valid API response does **not** prove market-wide coverage or no trades; missing cause remains unknown.
- 13 new synthetic-only tests. **296/296 research tests passed** on GitHub https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40533022442.
- `.github/workflows/luca-v03-iex-timestamps-ci.yml` is offline-only, no live source trigger, no schedule, no orders, no alerts.
- No edits to existing source `prospective_iex_research.py`, T0 workflow, followup workflow, production main, `/api/radar`, or fixed observation runs.

## Work integration plan (do NOT claim completed)
1. Review whether Work already has timestamp provenance; avoid duplicate implementation.
2. On a **future independent prospectively frozen session**, call the pure helper with original in-memory bars **after** `review()` and before bars are discarded, after actual GET completes. Preserve original T0 selection and unchanged signal rules.
3. To capture HTTP evidence, instrument GET pagination to retain only status codes and terminal page token, not secrets, credentials or full raw response. Pass `api_evidence` only when actually observed, never synthesize.
4. Save timestamp provenance as an **additional artifact**. Validate hashes and bar-count consistency with existing `frozen_t0.json` and `forward_review.json`. Do not mutate existing immutable original evidence.
5. If no new market observation has run, do not report this module as a solved data gap or an improved predictive accuracy.

## Already completed actual runs (do not rerun)
- Real T0 source **40517830351**, followup **40531637484**, actual gap audit **40532482508**.
- `research/v03_stage24/followup_live_request.txt` already exists and records original source ID; the scheduled 02:15 KST automation must skip duplicate.
- All grades D, SEC/float/market cap unverified, prediction not validated, no real orders.
