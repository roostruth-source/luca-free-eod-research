# LUCA V0.3 mobile demo — offline only

This guide uses the existing mobile calculator and viewer without any live market API.

1. Prepare a local JSON evidence file with schema `LUCA_V03_IEX_RAW_OHLCV_EVIDENCE_V1`. Synthetic test data must be labeled synthetic.
2. Run `python research/v03_stage24/mobile_outcomes.py --raw RAW.json --output report.md --json-output report.json`.
3. Open `research/v03_stage24/mobile_outcomes_viewer.html` on a browser and choose `report.json`.
4. Check that 5/15/30/60-minute values appear and missing prices show **확인 불가**.

**Safety:** NOT_VALIDATED; SEC_UNVERIFIED; no orders. A 35-minute raw capture cannot substantiate a 60-minute result. The mobile HTML has been statically checked in GitHub CI, but actual iPhone interaction remains unverified. Do not interpret synthetic demonstration values as real returns.

**No third prospective trial, no approval Secret, no live price calls.**
