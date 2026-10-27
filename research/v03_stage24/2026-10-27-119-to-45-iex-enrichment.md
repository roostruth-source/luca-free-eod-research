# LUCA V0.3 Stage — automatic discovery to explicit IEX price enrichment
Date: 2026-10-27 KST (before US regular session).

## Executed, not simulated
- GitHub Actions read-only research run: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40464749679
- **50/50 offline unit tests passed.**
- GET-only Alpaca screener requests succeeded; **119 unique discovered symbols** without manually entering tickers.
- GET-only batch snapshot requests with **feed=iex** succeeded for **119/119 symbols**.
- **45/119** had a last recorded IEX trade price in **$0.20–$20**. These are *price-band matches*, **not market-cap or float-qualified microcaps**.
- **0** were approved as fresh IEX regular-session research watches because collection occurred outside US regular hours. This is **correct**: no stale or premarket prices are passed off as current-session live signals.
- Artifact ID **12716590445** (7-day retention), containing the actual enrichment JSON; report does not publish unverified trading alerts.

## Data integrity boundaries
- IEX single-exchange snapshots are **not SIP**, not full-market quotes and not sufficient to prove order-book liquidity.
- Price, quote spread, timestamps and age are annotated; quote spreads are only populated if timestamps are recent enough.
- Market capitalization, outstanding shares, public float, SEC filings, and corporate-action adjustment are **not independently verified**. No A/B approval or buy recommendation.
- Screener endpoints favor already-active/moving stocks; **this is not yet an early-spike prediction model** and is not exhaustive US-stock coverage.
- Current result is **one-time** evidence, not a new scheduled unattended scan.
- Historical Stage24 frozen 20-day sample and original rules remain separate and untouched.
- `NOT_VALIDATED`, `real_trades_allowed=false`, `SEC_UNVERIFIED` maintained.
- Existing production main, site, /api/radar, scheduled automations, and five-day test not intentionally modified by this research work.

## Next concrete step
1. Verify current session/market calendar and recent IEX bar completeness in regular trading hours, without creating duplicate scheduled notifications.
2. Add independent market-cap / public-float **unknown-aware** enrichment (do not infer microcap from low share price).
3. Integrate SEC as-of acceptance-time, ATM/convertibles/warrants/EFFECT checks with fail-closed reporting for research candidates.
4. Only after historical and prospective verification consider safe unattended scheduling and A/B grades.
