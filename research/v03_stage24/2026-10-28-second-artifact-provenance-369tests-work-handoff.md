# LUCA V0.3 — second GitHub run/artifact provenance bridge verified

## Results
- Offline GitHub Actions run **40543885200** https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40543885200: **369/369 tests passed**.
- Added `research/v03_stage24/second_trial_artifact_bridge.py` and 13 synthetic tests. It checks second run GitHub metadata: exact second workflow name, isolated branch, push event, completed success, new distinct run ID. If supplied, checks actual GitHub artifact metadata: `luca-v03-second-prospective-{run_id}`, not expired, artifact workflow_run.id matches run ID.
- It calls `two_session_iex_comparison.compare` only after metadata checks, revalidates second T0 hash and timestamp grid via comparator, and writes comparison output using create-new `x` mode, no overwrite.
- The bridge itself does **not** fetch or authenticate metadata from GitHub. Its caller (Work/automation) must obtain actual GitHub API response and artifact metadata, not a self-written fixture. It deliberately labels first audit artifact source verification as external/not yet verified.
- The comparison does **not** report profits, returns or a prediction hit rate. It only describes IEX one-minute bar presence and missing timestamp counts.
- Second live trial is still **NOT RUN**. Request file remains absent; existing one-time automations are responsible for its future session and subsequent check. This stage performed no live API requests and no trades.

## Work instructions
1. Do not create a duplicate second trial, schedule or code path. Wait for existing one-time second prospective workflow and its run ID.
2. Check the actual GitHub Actions run and artifact metadata (via GitHub API or `gh`), download real second artifacts `frozen_t0.json`, `forward_review.json`, `iex_timestamp_provenance.json`.
3. Retrieve first *real* IEX coverage audit JSON from audit run **40532482508** (source run **40517830351**), not from synthetic test fixtures.
4. Supply the verified source and artifact metadata and real JSONs to `second_trial_artifact_bridge.py`. If any source missing, failed or incomplete, report it; do not fabricate a comparison.
5. Preserve existing first/second T0, no production changes, no alerts/orders. NOT_VALIDATED / SEC_UNVERIFIED / D WATCH ONLY / NO_ORDERS.
