# LUCA V0.3 — 2026-10-28 future IEX GET provenance adapter handoff (308 tests)

**Research only, optional future integration; NOT_VALIDATED, SEC_UNVERIFIED, NO_ORDERS.**

## Concrete progress
- Added `research/v03_stage24/iex_provenance_adapter.py`, a pure optional adapter `fetch_review_with_provenance(frozen, review_time, key, secret, recorded_at, opener=None)`. It reuses existing `fetch_after_freeze` and `review` without modifying original selection/signal rules. Captures **actual GET response HTTP status** and **actual pagination completion** (never assumes success); builds `iex_timestamp_provenance` from the same observed bars.
- Rejected HTTP non-200, unavailable HTTP status, duplicate/invalid pagination, duplicate bar, pre-T0 bar, tampered T0, and wrong feed/orders. Missing IEX minute remains **cause unknown** even when GET succeeded.
- Added `research/v03_stage24/test_iex_provenance_adapter.py` with 12 synthetic tests, and offline-only CI `.github/workflows/luca-v03-iex-provenance-adapter-ci.yml`.
- **308/308 offline tests passed**, verified actual GitHub Actions https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40533682181.
- First CI attempt 40533569732 had **one test-fixture issue**: duplicate-bar guard fired before repeated-token guard; fixed fixture with disjoint bars, reran successfully. No production incident.
- No live API used by this CI, no new market observation or alert. No edit to source/followup workflow, `main`, site, /api/radar, existing observation schedule.

## Work integration — not yet performed
1. Check Work's existing features for overlap before adopting this research-only optional adapter.
2. On a **new independent** prospectively frozen T0, after the 16-minute wait, optionally replace the original review-only fetch path with `fetch_review_with_provenance` using the same frozen T0 and the same review-time rules. Preserve the original review JSON schema and D-only grade.
3. Pass `recorded_at` as the **actual UTC timestamp after HTTP fetch/review**, not a synthetic or prefetch time. Save the returned provenance with `write_new` as an **additional** immutable artifact, never overwrite `frozen_t0.json` or `forward_review.json`.
4. In a future CI integration test, compare the original review result and the adapter review result for byte-equivalent semantic fields under identical synthetic API responses; fail closed on discrepancies.
5. A successful IEX GET does not prove there were no trades on all US exchanges. Missing minute causes need independent evidence (ideally SIP or other reliable source).
6. Do not rerun 2026-10-27 T0 40517830351, followup 40531637484, or gap audit 40532482508. No second actual observation has been scheduled by this step.

## Current validation
One real observation (12 symbols, 94/168 IEX minute slots, 0 patterns, 11/12 sparse). 308 offline tests are software safety checks, **not prediction accuracy**. No live buy approval.
