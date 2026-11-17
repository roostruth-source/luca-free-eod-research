"""Research-only evidence gate; URL shape is not SEC document verification."""
from typing import Mapping
from urllib.parse import urlsplit

RISK_FIELDS = (
    'atm', 'convertible_note', 'warrant', 'cb_reset',
    'reverse_split', 'listing_compliance', 'float',
)


def _sec_archive_url(url):
    """Reject lookalike hosts, credentials, query strings and non-filing paths."""
    if not isinstance(url, str) or any(ord(c) < 33 or ord(c) > 126 for c in url):
        return False
    try:
        parsed = urlsplit(url)
        parts = parsed.path.split('/')
        return (parsed.scheme == 'https' and parsed.netloc == 'www.sec.gov'
                and not parsed.query and not parsed.fragment
                and len(parts) >= 6 and parts[:4] == ['', 'Archives', 'edgar', 'data']
                and parts[4].isdigit() and bool(parts[-1])
                and all(part not in ('', '.', '..') for part in parts[4:]))
    except ValueError:
        return False


def assess(evidence: Mapping[str, object]) -> dict:
    """Only explicitly reviewed primary-source fields may be classified.

    This does not fetch SEC filings or establish independent SEC verification.
    """
    if not isinstance(evidence, Mapping):
        evidence = {}
    results = {}
    for field in RISK_FIELDS:
        item = evidence.get(field)
        valid = (isinstance(item, dict)
                 and item.get('verified') is True
                 and type(item.get('risk')) is bool
                 and _sec_archive_url(item.get('sec_url')))
        results[field] = {
            'state': ('RISK' if item['risk'] else 'CLEAR') if valid else 'UNKNOWN',
            'sec_url': item['sec_url'] if valid else None,
        }
    return {
        'status': 'NOT_VALIDATED',
        'sec_status': 'SEC_UNVERIFIED',
        'orders_enabled': False,
        'production_approved': False,
        'fields': results,
        'unknown_fields': [k for k, v in results.items() if v['state'] == 'UNKNOWN'],
    }
