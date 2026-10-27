# LUCA V0.3 — second independent prospective trial ready but DORMANT (2026-10-28 KST)

## Verified this stage
- Previous future-only review archival CI run **40539096406**: **329/329 passed**.
- New `research/v03_stage24/second_trial_gate.py`: accepts only exact research-only 3-line future request, same NY session date and weekday, 09:40–11:20 NY local time (DST aware), push on isolated branch, GitHub run attempt 1, and exactly one git-history commit touching request path. Rejects reruns, edited request, offhours, wrong branch, wrong date, extra lines or trading enablement.
- New `research/v03_stage24/test_second_trial_gate.py`: **15 offline synthetic tests** including EDT/EST DST, weekends, reruns, stale requests and no trading.
- New `.github/workflows/luca-v03-second-prospective-once.yml`: **dormant** push trigger ONLY `research/v03_stage24/second_prospective_request.txt` (file NOT created), fetch-depth 0 to enforce single request history; validates gate BEFORE market API; runs all offline tests; uses original prospective freeze, waits 16 minutes, uses isolated `future_iex_review.review_future_session` to save original `forward_review.json` and new `iex_timestamp_provenance.json`; artifact only, 7-day retention; no site, orders, alerts, schedule or production change.
- Offline gate CI `.github/workflows/luca-v03-second-gate-ci.yml` run **40540263823**: **344/344 tests passed**, confirmed GitHub Actions https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40540263823.
- Confirmed in GitHub branch tree: `research/v03_stage24/second_prospective_request.txt` **absent**. No second live trial was run.

## Next steps for Work (not completed)
1. Inspect Work's own research scanner and avoid duplicate development. Do not modify existing live scanner or source first trial.
2. Choose a **future US regular-session weekday** after checking NYSE market holiday/calendar and user's Korea notification constraints; do not infer a holiday from weekday alone.
3. During 09:40–11:20 **America/New_York**, explicitly create the request file **once** on isolated research branch, with exact content:
   ```
   LUCA_V03_SECOND_PROSPECTIVE_ONCE
   session_day_ny=YYYY-MM-DD
   research_only=true
   ```
   Replace YYYY-MM-DD with that day's actual NY calendar date. No extra lines. The gate rejects edits, re-runs, wrong time/day and nonresearch triggers. Creation itself triggers the one-off workflow; do not create it in advance.
4. Monitor Actions success/failure and artifact. If no candidates or API errors, report failure honestly; never synthesize success or issue orders.
5. For future real evidence, compare bar timestamp coverage against the first session (94/168), but do not attribute missing IEX minutes to API failures without corroboration, and do not call 2 sessions statistically validated accuracy.
6. Preserve first original T0 run **40517830351**, followup **40531637484**, gap audit **40532482508**. No change to main, website /api/radar, other automations or notification schedule.

## Research status
All D / SEC_UNVERIFIED / float and market cap unverified / NOT_VALIDATED / NO_ORDERS. Free IEX single-venue bars are not SIP and can be sparse; 344 passing tests are software guards, not forecast accuracy.
