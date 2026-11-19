"""Offline SEC contract-number leads; never verified terms or trade signals."""
import re
from decimal import Decimal, InvalidOperation
from research_sec_evidence import extract_review_evidence

NUMBER = re.compile(r'(?<![\w.])(?P<currency>\$)?(?P<number>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?P<percent>\s*%)?(?!\w|\.\d)')
PRICE_CUES = re.compile(r'\b(?:conversion|exercise|reset|floor|strike)\s+price\b', re.I)
DISCOUNT_CUES = re.compile(r'\b(?:discount|less than|of (?:the )?(?:lowest|average|closing) (?:price|vwap))\b', re.I)
ACCOUNTING_NEGATIVE = re.compile(r'\(\s*\$?\s*$')


def extract_numeric_leads(text, *, context=120, max_leads=5, max_chars=2_000_000):
    """Return bounded, unverified SEC number leads; never approve trading."""
    base = extract_review_evidence(text, context=0, max_chars=max_chars)
    base['numeric_leads'] = []
    if base['reason'] == 'INVALID_OR_OVERSIZED_TEXT':
        return base
    if (type(context) is not int or not 0 <= context <= 500 or
            type(max_leads) is not int or not 1 <= max_leads <= 30):
        base['reason'] = 'INVALID_NUMERIC_LIMITS'
        base['flags'] = {}
        base['evidence'] = {}
        return base

    leads = []
    seen = set()
    for field, hits in base['evidence'].items():
        for hit in hits:
            left = max(0, hit['start'] - context)
            right = min(len(text), hit['end'] + context)
            segment = text[left:right]
            cues = [(m.start(), m.end()) for cue in (PRICE_CUES, DISCOUNT_CUES)
                    for m in cue.finditer(segment)]
            if not cues:
                continue
            for match in NUMBER.finditer(segment):
                if min(max(a - match.end(), match.start() - b, 0)
                       for a, b in cues) > 45:
                    continue
                start, end = left + match.start(), left + match.end()
                # Reject clipped numbers, malformed comma groups and signed amounts.
                if (start > 0 and (text[start - 1].isalnum() or
                                   text[start - 1] in '.,-+−–—﹣－＋')):
                    continue
                if (end < len(text) and (text[end].isalnum() or text[end] == ',' or
                        (text[end] == '.' and end + 1 < len(text) and text[end + 1].isdigit())):
                    continue
                prefix = text[max(0, start - 12):start]
                suffix = text[end:min(len(text), end + 4)]
                # A separated sign still belongs to the amount (e.g. - $0.25).
                if re.search(r'[-+−–—﹣－＋]\s*\$?\s*, prefix):
                    continue
                if ACCOUNTING_NEGATIVE.search(prefix) and re.match(r'^\s*\)', suffix):
                    continue
                if (field, start, end) in seen:
                    continue
                try:
                    value = Decimal(match.group('number').replace(',', ''))
                except InvalidOperation:
                    continue
                kind = ('percent' if match.group('percent') else
                        'currency' if match.group('currency') else 'unclassified_number')
                if kind == 'unclassified_number' and value == value.to_integral_value() and 1900 <= value <= 2099:
                    continue
                seen.add((field, start, end))
                leads.append({'field': field, 'start': start, 'end': end,
                              'literal': text[start:end], 'kind': kind,
                              'value': str(value), 'status': 'UNVERIFIED_CONTEXT_NUMBER'})
    base['numeric_leads'] = sorted(leads, key=lambda v: (v['start'], v['field']))[:max_leads]
    base['reason'] = 'NUMERIC_LEADS_REQUIRE_ORIGINAL_SEC_CONTRACT_REVIEW'
    return base
, prefix):
                    continue
                if ACCOUNTING_NEGATIVE.search(prefix) and re.match(r'^\s*\)', suffix):
                    continue
                if (field, start, end) in seen:
                    continue
                try:
                    value = Decimal(match.group('number').replace(',', ''))
                except InvalidOperation:
                    continue
                kind = ('percent' if match.group('percent') else
                        'currency' if match.group('currency') else 'unclassified_number')
                if kind == 'unclassified_number' and value == value.to_integral_value() and 1900 <= value <= 2099:
                    continue
                seen.add((field, start, end))
                leads.append({'field': field, 'start': start, 'end': end,
                              'literal': text[start:end], 'kind': kind,
                              'value': str(value), 'status': 'UNVERIFIED_CONTEXT_NUMBER'})
    base['numeric_leads'] = sorted(leads, key=lambda v: (v['start'], v['field']))[:max_leads]
    base['reason'] = 'NUMERIC_LEADS_REQUIRE_ORIGINAL_SEC_CONTRACT_REVIEW'
    return base
