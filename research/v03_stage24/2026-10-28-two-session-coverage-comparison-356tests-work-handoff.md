# LUCA V0.3 — two independent IEX sessions comparison prepared, 356 offline tests

## Verified GitHub result
- Offline GitHub Actions run **40543438649**, https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40543438649, **356/356 tests PASSED**.
- New pure `research/v03_stage24/two_session_iex_comparison.py` and 12 synthetic-only tests, plus offline CI.
- The first baseline is **actual** source run 40517830351 and audited 94/168 one-minute IEX slots (55.95%), 1/12 complete, 0 patterns, with first audit schema/values strictly checked.
- The second session is **NOT YET RUN**. The comparison requires a second frozen T0, review and true per-symbol timestamp provenance, checks T0 hash, UTC time origin, candidate order, full observed+missing minute grid, total counts, successful actual GET pagination evidence, and D-only safety. It compares *coverage percentages* (not raw counts) because first is 14 minutes and future second can be 15 minutes.
- Difference in percentage points is **descriptive only**. Different dates/symbols/windows mean it is not proof of better feed or better prediction. No missing bar is interpreted as a zero return or proven API failure.
- No actual return, win rate, or prediction probability is calculated. NOT_VALIDATED, SEC_UNVERIFIED, NO_ORDERS.
- `.github/workflows/luca-v03-two-session-comparison-ci.yml` explicitly checks second request file absent. No live second T0, no market request, no order, no production change.

## Work next steps
1. The separate existing 2026-10-28 US morning automation is responsible for checking NY session and creating the one-time second request file, **not this offline comparison module**. Do not create or modify it now.
2. Once the second source run completes, first verify the GitHub source run metadata, correct branch, push event, successful conclusion, unique run ID and that its artifact actually belongs to the run. The comparator itself accepts an integer second run ID and does **not** independently authenticate GitHub run metadata. Never pass unverified metadata.
3. Obtain original real first audit JSON from artifact run 40532482508 and real second frozen/review/provenance JSON. Do not substitute synthetic fixtures.
4. Only then execute `compare(first_audit,second_frozen,second_review,second_provenance,verified_second_run_id)`, save immutable comparison output, and report genuine numbers, caveats and lack of statistical validation.
5. Avoid duplicating Work's development, preserve main, /api/radar, existing alerts and 5-day observations, and do not rerun first source or followup.
