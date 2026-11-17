"""Offline research-only cohort gate. No network, orders or predictive claims."""
from research_volume_anomaly import inspect_volume
from research_risk_flags import assess, RISK_FIELDS

COHORTS = ('NASDAQ_7_0', 'CHINA_1_0')


def evaluate_candidate(candidate, bars, evidence):
    """Require explicit universe provenance; never infer China ties from a ticker."""
    result = {
        'status': 'NOT_VALIDATED', 'sec_status': 'SEC_UNVERIFIED',
        'orders_enabled': False, 'production_approved': False,
        'decision': 'HOLD_UNVERIFIED', 'cohort': None, 'reasons': [],
    }
    if not isinstance(candidate, dict):
        result['reasons'].append('INVALID_CANDIDATE')
        return result
    cohort = candidate.get('cohort')
    if cohort not in COHORTS or type(cohort) is not str:
        result['reasons'].append('UNVERIFIED_COHORT')
        return result
    result['cohort'] = cohort
    if candidate.get('universe_verified') is not True:
        result['reasons'].append('UNVERIFIED_UNIVERSE')
    if cohort == 'CHINA_1_0' and candidate.get('china_link_reviewed') is not True:
        result['reasons'].append('UNVERIFIED_CHINA_LINK')
    volume = inspect_volume(bars)
    risk = assess(evidence) if isinstance(evidence, dict) else assess({})
    result['volume'] = volume
    result['risk'] = risk
    if volume['signal'] != 'VOLUME_SPIKE':
        result['reasons'].append('NO_CONFIRMED_VOLUME_SPIKE')
    if risk['unknown_fields']:
        result['reasons'].append('SEC_EVIDENCE_INCOMPLETE')
    if any(risk['fields'][field]['state'] == 'RISK' for field in RISK_FIELDS):
        result['reasons'].append('DISCLOSED_RISK')
    # Even a fully documented offline flag is never a validated trade signal.
    if not result['reasons']:
        result['decision'] = 'RESEARCH_REVIEW_ONLY'
    return result
