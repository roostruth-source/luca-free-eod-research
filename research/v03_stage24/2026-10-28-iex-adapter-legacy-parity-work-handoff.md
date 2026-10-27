# LUCA V0.3 — optional IEX provenance strict legacy parity test handoff

**Research branch only. Work owns integration; NOT_VALIDATED / SEC_UNVERIFIED / NO_ORDERS.**

## What was added
- `research/v03_stage24/test_iex_adapter_legacy_parity.py` — 10 **synthetic-only** regression tests that feed identical mock IEX GET responses into the original `fetch_after_freeze -> review` and optional `fetch_review_with_provenance` adapter. Requires **exact equality** of the original `forward_review` dictionary, preserved frozen T0, same candidate ordering, D-only grade, no buy, and no predictive performance claims.
- Tests: empty bars, sparse bars, all 15 minutes, a true synthetic detected pattern, two pages, multi-symbol order, pre-T0 rejection, duplicate bar rejection, tampered T0 rejection, recorded-at-time guard.
- `.github/workflows/luca-v03-iex-parity-ci.yml` triggers only on test/workflow changes; runs all offline research tests; no market APIs, live T0, followup, orders, alerts or schedules.
- GitHub Actions run **40534235530**: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40534235530. **Queued at time of this handoff note; do not claim pass until verified.** Previously 308/308 passed on run 40533682181; if all ten new tests pass, expected 318 tests.

## Next Work task (do not duplicate implementation)
1. Check Work's implementation for existing equivalent tests and avoid duplicate code.
2. Wait for run 40534235530 and inspect actual CI results; fix only isolated research files if needed.
3. If green, review whether the optional provenance adapter is suitable for a **new** future independently frozen prospective session, not the completed 2026-10-27 one.
4. Do not modify the old one-time source request, followup request, original T0 artifacts or production. Preserve strict time lock and IEX single-venue limitation. No prediction performance claim.

Existing real source 40517830351, followup 40531637484, gap audit 40532482508. One session, 12 frozen, 94/168 IEX minute slots, 0 observed patterns, 11/12 sparse. **No second live session has been run or scheduled here.**
