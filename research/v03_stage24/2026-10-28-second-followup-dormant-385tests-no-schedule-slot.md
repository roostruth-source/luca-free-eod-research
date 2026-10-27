# LUCA V0.3 — second 60-minute IEX followup ready, dormant, 385 offline tests

## Verified
- Offline GitHub Actions **40544701409**, https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40544701409, **385/385 tests passed**.
- Added `research/v03_stage24/second_followup_gate.py` and 16 synthetic-only tests, new **dormant** workflow `.github/workflows/luca-v03-second-followup-once.yml`, and offline CI.
- New followup workflow triggers **only** when `research/v03_stage24/second_followup_request.txt` is newly created on isolated branch, and this file **does not yet exist**.
- Before any new market API, workflow verifies GitHub second source run ID, exact workflow name, push event, research branch, completed success; downloads exact second source artifact; verifies frozen T0 hash, source date 2026-10-28 NY, forward review, timestamp provenance and HTTP evidence; requires 82 minutes to 8 hours after actual T0; blocks reruns, duplicate request history, wrong trigger.
- If signal exists, calls existing GET-only `forward_outcomes_iex.py` for hypothetical 5/15/30/60m IEX observations; if none, records NO_FROZEN_SIGNALS without fake returns. Calls existing `fixed_clock_reference.py` for all frozen symbols and `evidence_quality_gate.py` for strict quality. Outputs GitHub research artifact only, no orders, no site, no alerts.
- No second live trial or second followup has yet been executed. No actual performance/accuracy claim.

## IMPORTANT scheduling limitation
- Attempted to create a one-time **2026-10-29 00:45 Asia/Seoul** automation to conditionally initiate the followup. The automation tool returned **ERROR: current plan allows only 5 scheduled tasks**. Therefore **NO followup automation was created** and NO future followup run is promised. Existing 23:00 second-source and 23:40 result-check automations remain untouched.
- After second source run succeeds, Work or user must arrange the one-time followup request during actual maturity window; if not, do not retroactively claim prospective followup. A source run that fails or has no artifact must not be followed up.

## Safe manual trigger (only after real second run)
1. Verify actual source GitHub Actions run ID and success, artifact files, and T0 timestamp. Ensure 82min <= now-T0 <= 8h and original second request date 2026-10-28 NY.
2. Check no `research/v03_stage24/second_followup_request.txt` exists and no second followup workflow has run.
3. Create exactly one new file `research/v03_stage24/second_followup_request.txt` with actual second source run ID, newline. Never modify it after creation.
4. Confirm workflow run, review artifact `luca-v03-second-outcomes-<FOLLOWUP_RUN_ID>` only if run success. Keep no orders, D, SEC_UNVERIFIED, NOT_VALIDATED.

## Critical interpretation
- 385 tests are synthetic/offline software checks, not live prediction accuracy.
- IEX is single venue, missing minute is unknown cause, fixed clock not randomized control. The followup theoretical IEX open/close price movement is not realized profit.
- Preserve main, /api/radar, existing alerts, first live run and its followup, existing scheduled tasks.
