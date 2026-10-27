"""One-time, read-only diagnostic for OFFICIAL SEC data endpoints.

No proxy, mirror, scraping bypass, orders, retries or production changes.
No confidential tokens. Known CIKs are from previously cited SEC primary filings.
"""
from __future__ import annotations
import json
import pathlib
import urllib.error
import urllib.request

ENDPOINTS = {
    "official_ticker_map": "https://www.sec.gov/files/company_tickers.json",
    "official_data_submissions_GPUS": "https://data.sec.gov/submissions/CIK0000896493.json",
    "official_data_submissions_LAES": "https://data.sec.gov/submissions/CIK0001951222.json",
}
UA = "LUCA-Research/0.3 (public research; https://github.com/roostruth-source/luca-free-eod-research)"
MAX_READ = 200_000


def diagnose(opener=None):
    opener = opener or urllib.request.urlopen
    out = {}
    for label, url in ENDPOINTS.items():
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        }, method="GET")
        try:
            with opener(req, timeout=15) as response:
                status = getattr(response, "status", 200)
                body = response.read(MAX_READ)
            # Partial bytes are enough to identify whether an endpoint is reachable;
            # do not claim to have parsed or verified a full SEC submission.
            out[label] = {"status": "REACHABLE_PARTIAL_NOT_PARSED" if status == 200 else "HTTP_"+str(status),
                          "http_code": status, "bytes_sampled": len(body)}
        except urllib.error.HTTPError as exc:
            out[label] = {"status": "HTTP_"+str(exc.code), "http_code": exc.code,
                          "bytes_sampled": 0}
        except Exception as exc:
            out[label] = {"status": "ERROR_"+type(exc).__name__,
                          "http_code": None, "bytes_sampled": 0}
    return {
        "schema": "LUCA_V03_SEC_OFFICIAL_ACCESS_DIAGNOSTIC_V1",
        "source": "OFFICIAL_SEC_ONLY",
        "endpoints": out,
        "sec_filing_verified": False,
        "sec_risk_cleared": False,
        "validation_status": "NOT_VALIDATED",
        "real_trades_allowed": False,
        "note": "A reachable endpoint does not establish as-of completeness, mapping or safety.",
    }


def main():
    out = diagnose()
    folder = pathlib.Path("luca_v03_sec_diagnostic")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/"official_sec_access.json"
    if path.exists():
        raise FileExistsError("NO_OVERWRITE")
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2)+"\n", encoding="utf8")
    for name, item in out["endpoints"].items():
        print("SEC_ACCESS "+name+" "+item["status"])
    print("NOT_VALIDATED; NO_ORDERS; SEC_NOT_CLEARED")


if __name__ == "__main__":
    main()
