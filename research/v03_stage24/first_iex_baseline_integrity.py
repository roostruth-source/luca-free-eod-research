"""Integrity gate for archived REAL first IEX coverage rows (not trade signals).

The normalized JSON is reconstructed from the verified original GitHub Actions
coverage.json artifact. It is NOT byte-for-byte identical to that original.
The manifest records the ORIGINAL raw artifact SHA256 separately.
"""
from __future__ import annotations
import json
from pathlib import Path

FIRST_ID=40517830351
AUDIT_ID=40532482508
T0_HASH="18af8b515b034f0dea029db642132c28200eaa9c403d7cc1141e1d3430e623eb"
ORIGINAL_SHA256="5ef17ab15ab20055e282002abcd0a4397e3066a3a3983d8436b5755f4a0ef087"
SYMBOLS=("NEXR","CLRO","AIOK","SXTP","BRAI","GPUS","JBLU","SOAR","POM","ACTU","AEYE","ARTV")
COUNTS=(13,9,13,1,13,3,14,5,3,3,6,11)
HORIZONS=(5,15,30,60)
REFERENCE_COUNTS=(35,93,186,360)
REFERENCE_COMPLETE=(3,1,1,1)


def verify_first_normalized(doc,manifest):
    if type(doc) is not dict or type(manifest) is not dict:
        raise ValueError("INVALID_FIRST_ARCHIVE")
    if (doc.get("schema")!="LUCA_V03_IEX_COVERAGE_AUDIT_V1" or
        doc.get("source_run_id")!=FIRST_ID or
        doc.get("frozen_t0_sha256")!=T0_HASH or
        doc.get("frozen_symbols")!=12):
        raise ValueError("FIRST_SOURCE_IDENTITY_DRIFT")
    if (manifest.get("schema")!="LUCA_V03_FIRST_REAL_AUDIT_MANIFEST_V1" or
        manifest.get("source_run_id")!=FIRST_ID or
        manifest.get("audit_run_id")!=AUDIT_ID or
        manifest.get("artifact_uncompressed_sha256")!=ORIGINAL_SHA256 or
        manifest.get("artifact_uncompressed_bytes")!=9648 or
        manifest.get("frozen_t0_sha256")!=T0_HASH):
        raise ValueError("FIRST_ORIGINAL_ARTIFACT_MANIFEST_DRIFT")
    if (doc.get("initial")!={"observed_iex_bars":94,"expected_symbol_minutes":168,
                             "iex_minute_presence_pct":55.95,
                             "fully_observed_symbols":1,"sparse_symbols":11}):
        raise ValueError("FIRST_INITIAL_SUMMARY_DRIFT")
    rows=doc.get("rows")
    if type(rows) is not list or len(rows)!=12 or [r.get("symbol") for r in rows]!=list(SYMBOLS):
        raise ValueError("FIRST_SYMBOL_ORDER_DRIFT")
    if (manifest.get("frozen_symbols")!=list(SYMBOLS) or
        manifest.get("initial_bars")!=list(COUNTS)):
        raise ValueError("FIRST_MANIFEST_ROW_DRIFT")
    if [r.get("initial_iex_minutes") for r in rows]!=list(COUNTS):
        raise ValueError("FIRST_INITIAL_ROWS_DRIFT")
    if any(r.get("initial_expected_minutes")!=14 or
           r.get("initial_complete") is not (r["initial_iex_minutes"]==14)
           for r in rows):
        raise ValueError("FIRST_INITIAL_COMPLETENESS_DRIFT")
    references=doc.get("fixed_clock_reference")
    if type(references) is not list or len(references)!=4:
        raise ValueError("FIRST_REFERENCE_SUMMARY_DRIFT")
    for i,n in enumerate(HORIZONS):
        expected={"minutes":n,"observed_iex_bars":REFERENCE_COUNTS[i],
                  "expected_symbol_minutes":n*12,
                  "iex_minute_presence_pct":round(100*REFERENCE_COUNTS[i]/(n*12),2),
                  "fully_observed_symbols":REFERENCE_COMPLETE[i]}
        if references[i]!=expected:
            raise ValueError("FIRST_REFERENCE_SUMMARY_DRIFT")
        observed=complete=0
        for row in rows:
            rr=row.get("reference")
            if type(rr) is not list or len(rr)!=4:
                raise ValueError("FIRST_REFERENCE_ROWS_DRIFT")
            x=rr[i]
            if type(x) is not dict or x.get("minutes")!=n or x.get("expected")!=n:
                raise ValueError("FIRST_REFERENCE_ROWS_DRIFT")
            count=x.get("iex_bars")
            if type(count) is not int or not 0<=count<=n or x.get("complete") is not (count==n):
                raise ValueError("FIRST_REFERENCE_ROWS_DRIFT")
            observed+=count
            complete+=count==n
        if observed!=REFERENCE_COUNTS[i] or complete!=REFERENCE_COMPLETE[i]:
            raise ValueError("FIRST_REFERENCE_ROWS_DRIFT")
    if (doc.get("no_signal_outcomes_because_no_pattern") is not True or
        doc.get("missing_bar_cause_unknown") is not True or
        doc.get("raw_bar_timestamps_not_in_source_artifact") is not True or
        doc.get("prediction_accuracy_verified") is not False or
        doc.get("sec_status")!="SEC_UNVERIFIED" or
        doc.get("validation_status")!="NOT_VALIDATED" or
        doc.get("real_trades_allowed") is not False):
        raise ValueError("UNSAFE_FIRST_ARCHIVE")
    return {"source_run_id":FIRST_ID,"audit_run_id":AUDIT_ID,
            "original_artifact_sha256":ORIGINAL_SHA256,
            "original_raw_file_archived":False,
            "normalized_rows_archived":True,
            "rows_verified":12,
            "observed_first_iex_minutes":94,
            "not_prediction_accuracy":True,
            "validation_status":"NOT_VALIDATED","real_trades_allowed":False}


def load_verified(root=None):
    root=Path(root) if root is not None else Path(__file__).resolve().parent
    first=json.loads((root/"first_real_iex_audit_normalized_40532482508.json").read_text(encoding="utf8"))
    manifest=json.loads((root/"first_real_iex_audit_manifest_40532482508.json").read_text(encoding="utf8"))
    verify_first_normalized(first,manifest)
    return first
