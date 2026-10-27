# LUCA V0.3 — post-fetch UTC provenance timing verified, 319 offline tests

## Verified
- Original versus optional IEX adapter review parity **318/318** passed: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40534235530
- Optional IEX adapter now supports `recorded_at=None` and captures UTC completion time **after** the actual GET/review, rather than requiring a caller to supply a potentially premature timestamp.
- New deterministic test verifies that completion time is used, with original T0, frozen candidates, review results and D-only grade unchanged.
- **319/319 offline tests passed**: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40537973327
- Tests use synthetic API responses; they do not establish live IEX coverage or prediction accuracy.

## Work integration checkpoint
- Optional adapter and timestamp module are **not yet wired into a real live workflow**. Existing `prospective_iex_research.py` review path and `.github/workflows/luca-v03-prospective-live-once.yml` remain unchanged.
- Next implementation should be an **isolated future-only review entrypoint** using existing frozen T0 and the adapter, saving original `forward_review.json` and additional immutable `iex_timestamp_provenance.json`. Use actual completion clock (`recorded_at=None`), keep original output schema, strict time lock and no overwrite.
- Only trigger a new independent US morning T0 when its session, deduplication and user notification rules are explicitly checked. Do not repeat 2026-10-27 run 40517830351 or followup 40531637484.
- Do not change main, production /api/radar, recurring alerts or existing 5-day observations. No real orders, SEC/float unverified, NOT_VALIDATED.
