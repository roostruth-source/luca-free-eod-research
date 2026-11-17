"""Offline SEC filing text triage. Keywords are review prompts, never clearance."""
import re

PATTERNS = {
    'atm': (r'\bat.the.market\b', r'\b(?:sales|distribution) agreement\b'),
    'convertible_note': (r'\bconvertible (?:promissory )?notes?\b', r'\bconvertible debentures?\b'),
    'warrant': (r'\bwarrants?\b',),
    'cb_reset': (r'\breset (?:price|provision|date)\b', r'\bconversion price (?:shall|will|may) be (?:adjusted|reduced|reset)\b', r'\bvariable conversion price\b', r'\breset of (?:the )?conversion price\b'),
    'reverse_split': (r'\breverse (?:stock )?split\b',),
    'listing_compliance': (r'\bminimum bid price\b', r'\bnon.compliance (?:notice|letter)\b'),
    'float': (r'\bpublic float\b', r'\bshares held by non.affiliates\b'),
}


def triage_sec_text(text, *, max_chars=2_000_000):
    """Flag possible mentions; absence is UNKNOWN, not proof of no risk.

    Caller must separately establish SEC source authenticity, filing date,
    issuer identity, and contract terms. No network access or order execution.
    """
    result = {'status': 'NOT_VALIDATED', 'sec_status': 'SEC_UNVERIFIED',
              'orders_enabled': False, 'production_approved': False,
              'decision': 'HOLD_UNVERIFIED', 'flags': {}, 'reason': None}
    if (not isinstance(text, str) or not text.strip()
            or type(max_chars) is not int or max_chars < 1
            or len(text) > max_chars):
        result['reason'] = 'INVALID_OR_OVERSIZED_TEXT'
        return result
    normalized = re.sub(r'\s+', ' ', text).lower()
    for field, patterns in PATTERNS.items():
        result['flags'][field] = {
            'state': 'REVIEW_MENTION' if any(re.search(p, normalized) for p in patterns)
                     else 'UNKNOWN',
        }
    result['reason'] = 'TEXT_TRIAGE_ONLY_NOT_SEC_VERIFIED'
    return result
