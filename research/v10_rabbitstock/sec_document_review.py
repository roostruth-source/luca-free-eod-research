"""Bounded, read-only SEC filing text triage; never clears financing risk."""

from __future__ import annotations

from html.parser import HTMLParser
import re
import urllib.request

ARCHIVE_URL = re.compile(
    r"https://www\.sec\.gov/Archives/edgar/data/\d{1,10}/\d{18}/[A-Za-z0-9._-]{1,150}\.(?:htm|html|txt)"
)
MAX_BYTES = 2_000_000
TERMS = {
    "ATM": re.compile(r"\bat[- ]the[- ]market\b", re.I),
    "ELOC": re.compile(r"equity line of credit|equity purchase agreement", re.I),
    "CB": re.compile(r"convertible (?:note|debenture|bond)", re.I),
    "WARRANT": re.compile(r"\bwarrants?\b", re.I),
    "REVERSE_SPLIT": re.compile(r"reverse (?:stock )?split|share consolidation", re.I),
    "SHELF": re.compile(r"shelf registration|shelf offering", re.I),
    "LOCKUP": re.compile(r"lock[- ]up agreement", re.I),
}


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style"} and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def fetch_filing(url: str, opener=None) -> str:
    if not ARCHIVE_URL.fullmatch(url):
        raise ValueError("sec_archive_url_not_allowed")
    request = urllib.request.Request(url, headers={
        "User-Agent": "LUCA-Research/0.3 (read-only; github.com/roostruth-source/luca-free-eod-research)",
        "Accept": "text/html,text/plain", "Accept-Encoding": "identity",
    }, method="GET")
    with (opener or urllib.request.urlopen)(request, timeout=20) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("sec_document_too_large")
    return raw.decode("utf-8", errors="replace")


def review_text(document: str, url: str) -> dict:
    if not ARCHIVE_URL.fullmatch(url):
        raise ValueError("sec_archive_url_not_allowed")
    parser = _VisibleText()
    parser.feed(document)
    visible = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    matches = []
    for label, pattern in TERMS.items():
        match = pattern.search(visible)
        if match:
            matches.append({
                "term": label,
                "context": visible[max(0, match.start() - 80):match.end() + 100],
            })
    return {
        "source_url": url,
        "matched_terms": matches,
        "status": "TEXT_TERMS_REQUIRE_HUMAN_REVIEW" if matches else "NO_TERMS_FOUND_NOT_CLEARED",
        "supply_clearance": False,
        "NO_ORDERS": True,
    }
