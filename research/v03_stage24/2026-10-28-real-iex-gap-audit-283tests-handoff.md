# LUCA V0.3 — first actual 2026-10-27 NY IEX minute presence audit (2026-10-28 KST)

**Real research artifact audit, no new market query, NOT_VALIDATED, SEC_UNVERIFIED, NO_ORDERS.**

## Reproducible GitHub evidence
- Original real T0: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40517830351
- Original verified no-signal followup and 5/15/30/60-minute fixed reference: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40531637484
- **New actual artifact-only gap audit:** https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40532482508 — **success**, all research **283/283 offline tests passed**.
- New audit artifact: `luca-v03-actual-iex-coverage-40532482508` / `coverage.json`. Source run ID 40517830351 and original frozen T0 SHA256 `18af8b515b034f0dea029db642132c28200eaa9c403d7cc1141e1d3430e623eb` reverified. No guessed minutes.
- New isolated code `research/v03_stage24/iex_coverage_audit.py` and `test_iex_coverage_audit.py` (10 tests), one-time workflow `.github/workflows/luca-v03-actual-gap-audit-once.yml`; only existing original artifacts downloaded via GET. One-time request file `research/v03_stage24/real_iex_gap_audit_request.txt` (no schedule).

## Real first 14-minute observation
- 12 frozen symbols × 14 expected minute slots = **168 symbol-minute slots**, **94 actual IEX 1m bars** (55.95% presence).
- **1/12 complete** (JBLU); **11/12 sparse**. This is fraction of time slots with an IEX bar, NOT US consolidated market volume/coverage.
- Per-symbol IEX bars out of 14: NEXR 13, CLRO 9, AIOK 13, SXTP 1, BRAI 13, GPUS 3, JBLU 14, SOAR 5, POM 3, ACTU 3, AEYE 6, ARTV 11.
- First prospective pattern observed **0/12**; cannot infer 0% success or 100% failure due to gaps.

## Fixed-clock comparison (same 12 frozen candidates)
| Time horizon | Observed IEX symbol-minute slots | Slot presence | Fully observed symbols |
| --- | ---: | ---: | ---: |
| 5m | 35 / 60 | 58.33% | 3 / 12 |
| 15m | 93 / 180 | 51.67% | 1 / 12 |
| 30m | 186 / 360 | 51.67% | 1 / 12 |
| 60m | 360 / 720 | 50.00% | 1 / 12 |

## Root cause and Work next step
- **Root cause NOT determined.** IEX is a *single venue*. A missing minute may mean no IEX trades in that minute, or a data/API issue. Current archived forward files store counts, not raw bar timestamps, so this run cannot distinguish missing timestamps or API behavior. The GET API can return a valid empty series.
- Next independent development **in Work**, on research branch only: for future prospectively frozen sessions, archive *read-only IEX per-symbol timestamp/coverage provenance*, API response status, and fetch time, with strict size/privacy limits. Do not backfill pre-T0 bars as if known at T0. Do not use missing-minute interpolation or change signal thresholds to force a signal.
- Compare IEX gaps with a licensed consolidated source if available; never claim full-market accuracy from IEX-only.
- Keep a no-signal cohort; preserve SEC_UNVERIFIED, Float/market cap unknown, NOT_VALIDATED, D-only, no orders.
- The already scheduled 02:15 KST followup should detect existing `followup_live_request.txt` and successful run 40531637484 and **avoid duplicate**.
- Production main, /api/radar, deployed site, recurring alerts, existing fixed 5/20-day trials unchanged.

**This is 1 session's data quality measurement, not a validated prediction or trading result.**
