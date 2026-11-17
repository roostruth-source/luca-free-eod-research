"""Research-only evidence gate; never infers SEC verification from keywords."""
from typing import Mapping

RISK_FIELDS = (
    'atm', 'convertible_note', 'warrant', 'cb_reset',
    'reverse_split', 'listing_compliance', 'float',
)


def assess(evidence: Mapping[str, object]) -> dict:
    """Only explicitly reviewed primary-source fields may be classified.

    This does not fetch data or generate buy/sell signals.
    """
    results = {}
    for field in RISK_FIELDS:
        item = evidence.get(field)
        valid = (isinstance(item, dict)
                 and item.get('verified') is True
                 and type(item.get('risk')) is bool
                 and isinstance(item.get('sec_url'), str)
                 and item['sec_url'].startswith('https://www.sec.gov/Archives/'))
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
