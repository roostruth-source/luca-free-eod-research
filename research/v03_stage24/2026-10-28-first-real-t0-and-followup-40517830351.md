# LUCA V0.3 — 2026-10-28 00:30 KST first actual prospective session + verified followup

**REAL IEX RESEARCH DATA, NOT VALIDATED FOR TRADING.** This handoff supersedes pre-live synthetic-only status notes for the 2026-10-27 NY session.

## Verified source (actual market observation)
- Source GitHub Actions run **40517830351**, completed **success**: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40517830351
- Artifact **12740269368** `luca-v03-forward-once-40517830351` downloaded and inspected; contains `frozen_t0.json`, `forward_review.json`.
- Frozen at **2026-10-27T14:05:42.693870+00:00** (New York 10:05:42 EDT), review at **14:21:42 UTC**.
- SHA256 recomputed from frozen JSON matches stored SHA **18af8b515b034f0dea029db642132c28200eaa9c403d7cc1141e1d3430e623eb**.
- 12 frozen symbols in original order: NEXR, CLRO, AIOK, SXTP, BRAI, GPUS, JBLU, SOAR, POM, ACTU, AEYE, ARTV. Exactly same symbols/order in review.
- **94 IEX 1-minute bars** across 12 symbols; **0 pattern symbols**, **0 research signals**; first 14 eligible minutes fully covered for **1** symbol (JBLU), **11** symbols sparse. This is NOT evidence of 12 prediction failures, because missing IEX bars limit observability.
- Original workflow ran all 273 offline tests before freezing; passed. Source run is **real**, not synthetic.

## Verified one-time followup
- Source run success, branch, workflow, event, artifact hash, frozen/review consistency checked.
- At ~00:30 KST, all 60-minute horizons from fixed T0+6min reference had matured. Existing future 02:15 KST scheduled check not yet run. To advance user-requested next stage, **created `research/v03_stage24/followup_live_request.txt` exactly once with source ID `40517830351`**.
- Followup GitHub run **40531637484**: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40531637484
- Followup artifact **12747076712** `luca-v03-outcomes-40531637484` downloaded and inspected. Source metadata validates original run; includes no_signals, fixed_clock_reference, quality, one-session ledger, source attempts inventory, Korean report.
- `no_signals.json`: `NO_FROZEN_SIGNALS`; **signal-specific 5/15/30/60-minute outcomes NOT calculated**, appropriately (no invented 0% returns).
- Fixed-clock comparison for all 12 original candidates at **14:12 UTC** (10:12 ET), independent of pattern detection: **5m complete 3/12; 15m 1/12; 30m 1/12; 60m 1/12**; remainder missing IEX minutes. This is not randomized control or actual fill.
- Only **JBLU** had complete 5/15/30/60m IEX reference: hypothetical open-to-close **-0.5254%, +0.5254%, -0.5254%, -1.0508%** respectively. **This was NOT a signal, NOT a trade, NOT the scanner's return.** AIOK 5m +1.1757%, BRAI 5m -2.5954%, but no complete longer windows. Avoid promoting these as candidates.
- Quality gate: `INSUFFICIENT_FOR_PREDICTION`, 12/12 grade D, SEC_UNVERIFIED, float/market cap unknown, no real fill, spread or slippage.
- One-session ledger `sessions=1`, 12 frozen, 0 patterns, 11 sparse. Inventory: GitHub source attempts 1, GitHub success 1, failures 0; this is NOT stock-signal win rate.

## Next research priority (Work)
1. Do NOT trigger a second forward or followup request for the 2026-10-27 NY session. The 02:15 KST automation should detect existing followup request/run and **skip duplicate**; avoid repeated user notification.
2. The primary observed issue is **sparse IEX minute bars**: 11/12 incomplete initial 14-min windows, and only 1/12 complete 60-min reference. Design a separate offline data coverage analysis; DO NOT loosen rules or fill missing minutes with guessed prices.
3. To test predictive utility requires multiple independent prospective sessions including failures, and eventually reliable whole-market data and SEC/Float/dilution checks; no A/B buy approval or automation of orders.
4. No changes to production main, /api/radar, website, recurring scanner, 5-day or 20-day frozen trials, or existing alerts.

**NOT_VALIDATED / SEC_UNVERIFIED / NO_ORDERS**.
