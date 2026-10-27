# LUCA V0.3 — 2026-10-27/28 prospective one-off live research trial handoff

**Status: ARMED AS TWO ONE-OFF CHATGPT AUTOMATIONS, NOT EXECUTED YET**

## Result of this turn
- Research branch now has a read-only **source provenance gate** `research/v03_stage24/followup_bridge.py`. It refuses to reuse the wrong GitHub run, wrong workflow/branch, unsuccessful run, altered T0 freeze, or mixed prospective review.
- Additional **10 safety checks** pass. Total isolated GitHub research tests **138/138 PASSED**:
  https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40484107084
- Research-only outcome bridge `.github/workflows/luca-v03-followup-once.yml` is **dormant** until the one-time request file `research/v03_stage24/followup_live_request.txt` exists. It fetches the earlier prospective artifact using GitHub Actions read-only token, validates run provenance, then runs `forward_outcomes_iex.py` only after signal+60m+2m elapsed. No-signal case has a separate no-signal status instead of manufactured returns.
- New **two one-time scheduled automations** (separate from existing routine alerts) were successfully created, intended KST times:
  1. 2026-10-27 23:02, after US regular opens: check New York morning window then trigger `prospective_live_request.txt` on **research branch only**; this is just the T0 discovery + forward 16-minute observation request.
  2. 2026-10-28 02:15: check source run completion and artifact, only then trigger `followup_live_request.txt` with exact run ID, assess if possible, and provide one concise Korean research report. Do **not** claim the later outcome is done until Github confirms success.
- A successful *scheduled task creation* does not demonstrate that the future GitHub job will run or that any real market signals will be found. Require GitHub evidence.
- If the prospective source has no fresh candidates, is outside a valid US session, or failed, do not push a followup request; report an unavailable/insufficient evidence status. A/B trading grade remains blocked.

## Immutable controls
- `main`, deployed scanner, `/api/radar`, existing scheduled scanner, earlier 5-trading-day observational study and frozen 20-day Stage24 trial **NOT MODIFIED** by this turn.
- No GitHub Actions schedule, no real orders, no deployment. Repo branch push triggers are narrowly scoped to the one-off request files.
- IEX is not consolidated SIP. Missing bars are not filled. SEC GitHub HTTP 403 persists, and market-cap/float remain UNVERIFIED.
- `NOT_VALIDATED` / `SEC_UNVERIFIED` / `real_trades_allowed=false`.
