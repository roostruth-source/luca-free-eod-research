"""Read-only LUCA V0.3 recovery diagnostic. Never runs market APIs or orders."""
from __future__ import annotations
import datetime as dt
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

REQUEST = Path('research/v03_stage24/third_prospective_request.txt')
EXPECTED_APPROVAL_SHA256 = 'a1903e8f2ab515abc7f44fa37f745fa6ab05e2396f3592ee1a8f12acd0e258cf'
UTC = dt.timezone.utc
NY = ZoneInfo('America/New_York')

def inspect(root: Path, now: dt.datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError('timezone-aware now required')
    path = root / REQUEST
    result = {'schema':'LUCA_V03_RECOVERY_PREFLIGHT_V1', 'read_only':True,
              'orders_allowed':False, 'validation_status':'NOT_VALIDATED',
              'sec_status':'SEC_UNVERIFIED', 'all_grades':'D',
              'request_exists':path.is_file(), 'safe_to_reuse_request':False,
              'next_action':'CREATE_SEPARATE_REVIEWED_ONE_TIME_GATE'}
    if not path.is_file():
        result['reason'] = 'REQUEST_NOT_FOUND_VERIFY_GIT_HISTORY_BEFORE_ANY_ACTION'
        return result
    lines = path.read_text(encoding='utf-8').splitlines()
    if len(lines) != 8 or lines[0] != 'LUCA_V03_THIRD_PROSPECTIVE_ONCE':
        result['reason'] = 'MALFORMED_REQUEST'
        return result
    pairs = [line.split('=', 1) for line in lines[1:]]
    if any(len(p) != 2 for p in pairs):
        result['reason'] = 'MALFORMED_REQUEST'
        return result
    expected_keys = ('session_day_ny', 'expires_at_utc', 'approval_nonce',
                     'baseline_commit', 'approved_code_commit',
                     'research_only', 'orders_allowed')
    if tuple(key for key, _ in pairs) != expected_keys:
        result['reason'] = 'MALFORMED_REQUEST'
        return result
    fields = dict(pairs)
    if fields['research_only'] != 'true' or fields['orders_allowed'] != 'false':
        result['reason'] = 'UNSAFE_REQUEST'
        return result
    nonce = fields['approval_nonce']
    digest = hashlib.sha256(nonce.encode('utf-8')).hexdigest()
    result['request_approval_hash_matches_expected'] = digest == EXPECTED_APPROVAL_SHA256
    result['request_session_day_ny'] = fields.get('session_day_ny')
    try:
        expires = dt.datetime.fromisoformat(fields['expires_at_utc'])
        result['request_expired'] = expires.tzinfo is None or expires <= now
    except (KeyError, ValueError):
        result['request_expired'] = True
    local = now.astimezone(NY)
    result['within_ny_morning_window'] = local.weekday() < 5 and dt.time(9,40) <= local.time().replace(tzinfo=None) <= dt.time(11,20)
    result['reason'] = 'EXISTING_SINGLE_USE_REQUEST_MUST_NOT_BE_REPLAYED'
    return result

if __name__ == '__main__':
    print(json.dumps(inspect(Path('.'), dt.datetime.now(UTC)), sort_keys=True))
