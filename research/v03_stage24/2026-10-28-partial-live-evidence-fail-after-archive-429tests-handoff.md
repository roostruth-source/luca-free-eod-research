# LUCA V0.3 — partial evidence must survive a second live followup API failure

## Actual change
The dormant `.github/workflows/luca-v03-second-followup-once.yml` previously stopped immediately if the later IEX market GET or fixed-clock benchmark GET failed. This could leave the completed authentic second source and successfully collected partial data unarchived or without a readable quality report.

Now:
1. **Strict source identity, immutable T0, timestamp provenance, maturity, and two-session coverage comparison remain mandatory fail-closed BEFORE any new market GET.** No trading, no changes to the source workflow.
2. Three independent downstream steps — signal 5/15/30/60m IEX outcomes, fixed-clock reference, and quality JSON — have `id` and `continue-on-error: true` so the other independent evidence can still be measured and the original source archived.
3. `second_followup_step_status.py` writes explicit `step_status.json` with GitHub step `success/failure/skipped/cancelled` outcomes, no fake zero-return assumption and no trading approval.
4. Existing Korean report (optional) can describe missing/unavailable evidence rather than invented results. `upload-artifact` still executes `if: always()` and includes `luca_v03_second_quality/` with the status.
5. **After archive**, a final step checks original step outcomes and deliberately fails the GitHub workflow if ANY essential signal/reference/quality step failed or was skipped. This preserves a truthful failure status and partial artifacts simultaneously. If the earlier mandatory provenance gate failed, no downstream GET is attempted and workflow remains failed.

## Verification
- Eight new synthetic/offline tests check success/failure/skipped statuses, safe language, and the fail-after-archive ordering.
- Initial test failure was an assertion expecting a separate `if` rather than the real shell `||` OR chain. Corrected the test.
- **GitHub Actions 40562541256 SUCCESS; 429/429 offline tests passed**: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40562541256

## Limitations / next actual step
- No second live run yet, no live partial API failure has been observed, and 429 tests are NOT prediction accuracy.
- Do not create a second source/followup request or new schedule. Existing 2026-10-28 23:00 KST and 2026-10-29 00:45 KST automations own those tasks.
- If actual followup fails, inspect archived `step_status.json`, raw API error logs, source provenance and quality report before deciding on future tests; never re-trigger the same once-only source or claim no pattern as no opportunity.
- D / NOT_VALIDATED / SEC_UNVERIFIED / NO_ORDERS; IEX is not consolidated SIP.
