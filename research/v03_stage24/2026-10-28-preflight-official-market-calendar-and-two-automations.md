# LUCA V0.3 — 2026-10-28 second prospective live-trial preflight

## Independently checked before market session
- **NYSE official 2026 holiday calendar**: Wednesday **2026-10-28** is NOT a listed exchange holiday or early close. Source: https://www.nyse.com/trade/hours-calendars and Nasdaq 2026 calendar https://nasdaqtrader.com/Trader.aspx?id=Calendar. An extraordinary closure or outage could still occur; do not claim exchange was open without actual live confirmation.
- GitHub research branch `research/v03-stage24-evidence` checked: `research/v03_stage24/second_prospective_request.txt` ABSENT; `research/v03_stage24/second_followup_request.txt` ABSENT; no second live source or second live followup run seen at check time.
- Source GitHub workflow `.github/workflows/luca-v03-second-prospective-once.yml` has dormant request-file-only trigger, no schedule; NY time guard 09:40–11:20 EDT, unique first push request history, first attempt only, GET-only read, freeze, 16-minute wait, post-T0 review and original bar timestamp provenance. If missing candidates or API error, fail honestly.
- Existing automation **6ae0d3bae9108191a8177d081b2e1768** enabled, `2026-10-28 23:00 Asia/Seoul` (2026-10-28 10:00 EDT), responsible for checking and triggering the unique source request. Do not duplicate.
- Existing automation **6ae0d3cabfc48191a9cf1d69349f7639** enabled, `2026-10-29 00:45 Asia/Seoul` (2026-10-28 11:45 EDT), checks actual source success, artifacts, T0 +82min to 8h, then conditionally creates a unique followup request. Do not duplicate. If source T0 is unexpectedly after 10:23 EDT, maturity will not hold at 11:45 and followup must NOT run.
- Last full offline regression `40544701409` 385/385 PASS. This is software test coverage, not live research result or predictive validation.

## Next evidence to verify after actual run
1. GitHub second source run id, success, real artifact containing frozen_t0.json, forward_review.json, iex_timestamp_provenance.json.
2. Real T0 time, number of frozen symbols, observed/expected IEX bars, completeness and true HTTP GET status.
3. Followup workflow run id, successful or failed outcome; 5/15/30/60m results if real source and data maturity conditions hold.
4. Real first source run 40517830351 (94/168 1m IEX bars, 1/12 complete, 0 patterns) vs second source via validated comparator. No claim of improved prediction based on two sessions.

## Invariants
Research branch only; preserve production main, /api/radar, existing alerts and original first live records. All D, SEC_UNVERIFIED, NOT_VALIDATED, NO_ORDERS. Missing IEX minutes have unknown cause; no live fill/profit claim.
