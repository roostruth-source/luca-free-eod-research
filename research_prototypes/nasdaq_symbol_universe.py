"""Download NasdaqTrader listed-symbol directory for a broad *listing* universe.

NOT a verified microcap universe: listings contain neither market cap nor float.
No orders, no SEC verification. Network failures must fail closed.
"""
import csv
import io
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCE = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
USER_AGENT = "LUCAResearch/1.0 (public listing research)"
MAX_BYTES = 2_000_000
ALLOWED = re.compile(r"^[A-Z]{1,6}$")

def parse_directory(body):
    lines = body.decode("utf-8-sig").splitlines()
    if not lines or not lines[0].startswith("Symbol|Security Name|"):
        raise ValueError("unexpected NasdaqTrader header")
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter="|")
    symbols = set()
    for row in reader:
        sym = (row.get("Symbol") or "").strip().upper()
        if sym.startswith("File Creation Time"):
            continue
        if (not ALLOWED.fullmatch(sym)
                or row.get("Test Issue") != "N"
                or row.get("ETF") != "N"
                or row.get("NextShares") == "Y"):
            continue
        # These are Nasdaq-listed, non-ETF symbols; NOT necessarily common stock
        # or microcaps. Exclude explicit warrant/unit/preferred naming patterns.
        name = (row.get("Security Name") or "").lower()
        if any(term in name for term in ("warrant", " units", " unit ", "preferred",
                                         "depositary share", "rights", "etn")):
            continue
        symbols.add(sym)
    if len(symbols) < 100:
        raise ValueError("suspiciously small Nasdaq symbol universe")
    return sorted(symbols)

def fetch_directory(url=SOURCE):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=25) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Nasdaq directory too large")
    return data

def main():
    symbols = parse_directory(fetch_directory())
    # The existing EOD collector has a 2,000-symbol curated-list limit. Select
    # deterministic first 2,000 as a bounded *partial* listing sample; never
    # mislabel it as complete or microcap filtered.
    sample = symbols[:2000]
    target = Path("research_prototypes/watchlist_symbols.txt")
    target.write_text("# NasdaqTrader non-ETF listing SAMPLE; NOT verified microcaps\n"
                      + "\n".join(sample) + "\n", encoding="utf-8")
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE,
        "source_count": len(symbols),
        "sample_count": len(sample),
        "status": "PARTIAL_LISTING_SAMPLE_NOT_MICROCAP_VERIFIED",
        "float_verified": False, "market_cap_verified": False,
        "sec_verified": False, "orders_enabled": False,
    }
    Path("research_prototypes/watchlist_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print("Nasdaq listing sample:", len(sample), "of", len(symbols))

if __name__ == "__main__":
    main()
