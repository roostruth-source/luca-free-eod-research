# LUCA V0.3 — second real IEX research Korean auto-report (offline-tested)

## Implemented
- `research/v03_stage24/second_korean_research_report.py` creates a concise Korean markdown report only after authentic completed second source metadata, matching frozen T0/review/IEX timestamp provenance, strict first-vs-second comparison and quality gate.
- Shows first 94/168 (55.95%) versus actual second observed/expected IEX 1m bars, coverage percentage point difference, per-symbol initial pattern/missing bar state, any matured 5/15/30/60m followup status, and important non-trading limitations.
- Never claims improved predictive accuracy, actual trade fills or that missing IEX minutes are API errors. Source metadata, comparison and first durable baseline are checked; manipulated data fails closed.
- Dormant `.github/workflows/luca-v03-second-followup-once.yml` automatically writes `luca_v03_second_korean_report/report.md` into the 2nd followup artifact after existing strict verification and 60m observation. Korean report is **no-notification** and **continue-on-error**, so it cannot invalidate the underlying actual source/followup archive if the optional human report fails.
- 8 new offline tests for Korean coverage, honest no-signal, missing data, tampering, unsafe grades.
- Initial CI failures were a syntax typo and inaccurate synthetic fixture assumptions, fixed before handoff. Latest GitHub Actions **40562081620 SUCCESS 421/421 tests**: https://github.com/roostruth-source/luca-free-eod-research/actions/runs/40562081620

## Next
- Wait for the pre-existing scheduled second live source and conditional 60min followup. Neither request file has been created by this code work. No duplicate automation.
- After a genuine successful source/followup, read the new `luca_v03_second_korean_report/report.md` artifact and present the **real numbers**, explicitly noting any missing horizons.
- All D / SEC_UNVERIFIED / NOT_VALIDATED / NO_ORDERS; IEX is one exchange, no consolidated US market or execution costs.
