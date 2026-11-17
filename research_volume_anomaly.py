"""Offline-only volume-first research flags. Not a trading signal."""
from math import isfinite
from statistics import median


def inspect_volume(bars, *, baseline_days=20, spike_ratio=3.0, min_history=10):
    """Compare latest completed bar with prior bars only (no look-ahead)."""
    result = {'status': 'NOT_VALIDATED', 'sec_status': 'SEC_UNVERIFIED',
              'orders_enabled': False, 'production_approved': False,
              'signal': 'UNKNOWN', 'volume_ratio': None, 'reason': None}
    if not isinstance(bars, (list, tuple)) or len(bars) < min_history + 1:
        result['reason'] = 'INSUFFICIENT_HISTORY'
        return result
    if not isinstance(baseline_days, int) or isinstance(baseline_days, bool) or baseline_days < min_history or min_history < 2:
        result['reason'] = 'INVALID_PARAMETERS'
        return result
    if not isinstance(spike_ratio, (int, float)) or isinstance(spike_ratio, bool) or not isfinite(spike_ratio) or spike_ratio <= 1:
        result['reason'] = 'INVALID_PARAMETERS'
        return result
    window = bars[-(baseline_days + 1):]
    if len(window) < min_history + 1:
        result['reason'] = 'INSUFFICIENT_HISTORY'
        return result
    try:
        volumes = []
        for bar in window:
            if not isinstance(bar, dict):
                raise ValueError('bad bar')
            v, c = bar['volume'], bar['close']
            if isinstance(v, bool) or isinstance(c, bool) or not isinstance(v, (int, float)) or not isinstance(c, (int, float)):
                raise ValueError('bad types')
            if not isfinite(v) or not isfinite(c) or v < 0 or c <= 0:
                raise ValueError('bad values')
            volumes.append(v)
        times = [bar.get('timestamp') for bar in window]
        if any(t is not None for t in times) and (any(t is None for t in times) or len(set(times)) != len(times) or times != sorted(times)):
            raise ValueError('bad chronology')
    except (KeyError, TypeError, ValueError):
        result['reason'] = 'INVALID_BAR_DATA'
        return result
    base = median(volumes[:-1])
    if base <= 0:
        result['reason'] = 'ZERO_BASELINE'
        return result
    ratio = volumes[-1] / base
    result['volume_ratio'] = round(ratio, 4)
    result['signal'] = 'VOLUME_SPIKE' if ratio >= spike_ratio else 'NO_SPIKE'
    result['reason'] = 'OFFLINE_ONLY_NOT_VERIFIED'
    return result
