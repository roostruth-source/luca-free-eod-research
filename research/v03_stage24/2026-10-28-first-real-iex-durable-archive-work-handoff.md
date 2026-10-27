# LUCA V0.3 — verified durable first IEX baseline and second bridge

## Why this change
Original real first IEX coverage audit GitHub Actions artifact (run 40532482508, artifact ID 12746118351) has finite retention (7 days). A manifest alone cannot reproduce per-symbol/horizon comparison after artifact expiry.

## Original evidence, independently inspected
- Original ZIP contained `coverage.json`, exactly **9648 bytes**, SHA256 **5ef17ab15ab20055e282002abcd0a4397e3066a3a3983d8436b5755f4a0ef087**.
- First live source 40517830351, frozen T0 SHA256 18af8b515b034f0dea029db642132c28200eaa9c403d7cc1141e1d3430e623eb.
- 12 symbols × 14 IEX minute slots = 168; 94 observed (55.95%); 1/12 complete; zero patterns. Fixed-clock 5m 35/60 (3 complete), 15m 93/180 (1), 30m 186/360 (1), 60m 360/720 (1).
- **Full verified row-by-row count values** and original audit metadata are now in `research/v03_stage24/first_real_iex_audit_normalized_40532482508.json`. This is a **normalized reconstruction of verified original data, not the original byte-for-byte JSON**. The SHA256 in the manifest refers ONLY to the original downloaded `coverage.json`, not to normalized copy.
- `research/v03_stage24/first_real_iex_audit_manifest_40532482508.json` stores original hash, source, counts.
- `first_iex_baseline_integrity.py` validates frozen symbol order, each first-window observed count, horizon totals, complete symbols, first source identity, manifest original hash, research-only flags. `load_verified()` loads normalized durable data with these checks.
- `second_trial_artifact_bridge.py` CLI now defaults to `load_verified()` if `--first-audit` omitted. Optional explicit original audit JSON still supported. Second real run metadata and artifacts remain REQUIRED; do not substitute synthetic second fixture.
- Synthetic regression tests include normalized durable first archive and future second comparison; no live market requests, no orders, no alerts.

## What to do after second live session
1. Wait for existing 2026-10-28 23:00 KST second-source automation and 2026-10-29 00:45 KST conditional followup automation. Do not duplicate or trigger early.
2. Verify actual second GitHub run, source artifact `frozen_t0.json`, `forward_review.json`, `iex_timestamp_provenance.json` and GitHub artifact metadata.
3. Run `second_trial_artifact_bridge.py` using real second metadata and artifact dir; **omit --first-audit** to use durable first baseline automatically.
4. Report observed IEX coverage and missing timestamps only; two sessions do not establish predictive accuracy or realized profits.

## Status
NOT_VALIDATED / SEC_UNVERIFIED / D WATCH ONLY / NO_ORDERS. First raw OHLCV and raw first-minute timestamps were never archived; normalized audit contains only verified aggregate counts, not reconstructible raw price data.
