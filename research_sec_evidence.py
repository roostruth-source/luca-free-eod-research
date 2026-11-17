"""Offline SEC mention evidence: bounded excerpts, never a verified filing claim."""
import re
from research_sec_text_triage import PATTERNS, triage_sec_text


def extract_review_evidence(text, *, max_chars=2_000_000, context=90, max_hits=3):
    """Return traceable text offsets for manual review, not contract conclusions."""
    base = triage_sec_text(text, max_chars=max_chars)
    base['evidence'] = {}
    if base['reason'] == 'INVALID_OR_OVERSIZED_TEXT':
        return base
    if type(context) is not int or not 0 <= context <= 500 or type(max_hits) is not int or not 1 <= max_hits <= 20:
        base['reason'] = 'INVALID_EVIDENCE_LIMITS'
        base['flags'] = {}
        return base
    # Preserve offsets against original text, including line breaks.
    for field, patterns in PATTERNS.items():
        hits = []
        seen = set()
        for pattern in patterns:
            for match in re.finditer(pattern.replace(' ', r'\s+'), text, flags=re.IGNORECASE):
                key = (match.start(), match.end())
                if key in seen:
                    continue
                seen.add(key)
                hits.append((match.start(), match.end()))
        hits.sort()
        base['evidence'][field] = [
            {'start': start, 'end': end,
             'excerpt': text[max(0, start-context):min(len(text), end+context)]}
            for start, end in hits[:max_hits]
        ]
    base['reason'] = 'OFFLINE_EXCERPTS_REQUIRE_SEC_SOURCE_AND_TERMS_REVIEW'
    return base
