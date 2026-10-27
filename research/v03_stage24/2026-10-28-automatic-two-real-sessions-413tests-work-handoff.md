# LUCA V0.3 — automatic first-versus-second REAL IEX coverage in dormant second followup

## Implemented
- The existing dormant `.github/workflows/luca-v03-second-followup-once.yml` now obtains authentic GitHub Actions artifact list via `gh api repos/$GITHUB_REPOSITORY/actions/runs/$RUN_ID/artifacts?per_page=100`, verifies unique exact source artifact name, non-expiry, positive artifact id/size, matching source run id, and completed successful second source workflow using `second_source_artifact_identity.py`.
- After the existing `second_followup_gate.py` verifies source, timestamps, actual HTTP GET and 82-minute maturity, the workflow invokes `second_trial_artifact_bridge.py` with the authenticated source metadata and artifact metadata. The bridge uses the durable first actual archive by default and writes `luca_v03_second_quality/two_session_coverage.json`.
- The original 5/15/30/60-minute hypothetical IEX followup and quality report remain unchanged, as do all existing live/scheduled workflow triggers. The workflow archives original source identity, artifact list and selected artifact metadata alongside the comparison.
- 8 offline artifact identity tests, including missing, duplicate, wrong run, expired, zero size, wrong workflow and malformed list.
- First CI failures 40561254812 and 40561279644 caused solely by a test fixture import typo (`ARTIFACT` vs `ART`). Fixed and rerun successfully: **GitHub Actions 40561325223, 413/413 offline tests passed**. https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40561325223
- No second prospective or followup request file created, no market GET from this change, no orders, no production changes.

## Limitations and next step
- This is dormant workflow code tested offline, **not** evidence of a successful second live source, live comparison or 60-minute outcome.
- Existing 2026-10-28 23:00 KST source and 2026-10-29 00:45 KST conditional followup automations remain the only scheduled triggers. Do not duplicate them.
- Compare first 94/168 (55.95%) and 0 patterns against second observed counts only if the authentic second source succeeds. IEX is single exchange, not full market. No fill/slippage verification, SEC_UNVERIFIED, NOT_VALIDATED, D, NO_ORDERS.
