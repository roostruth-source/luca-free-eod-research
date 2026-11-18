"""Offline-only volume-first research flags. Not a trading signal."""
from math import isfinite
from statistics import median


def inspect_volume(bars, *, baseline_days=20, spike_ratio=3.0, min_history=10):
    """Compare latest completed bar with prior bars only (no look-ahead)."""
    result = {'status': 'NOT_VALIDATED', 'sec_status': 'SEC_UNVERIFIED',
              'orders_enabled': False, 'production_approved': False,
              'signal': 'UNKNOWN', 'volume_ratio': None, 'reason': None}
    # Extremely large Python integers can raise OverflowError in isfinite().
    # Treat malformed thresholds as unverified rather than crashing the scan.
    try:
        valid_ratio = (type(spike_ratio) in (int, float)
                       and isfinite(spike_ratio) and spike_ratio > 1)
    except (OverflowError, TypeError, ValueError):
        valid_ratio = False
    if (type(min_history) is not int or min_history < 2
            or type(baseline_days) is not int or baseline_days < min_history
            or not valid_ratio):
        result['reason'] = 'INVALID_PARAMETERS'
        return result
    if not isinstance(bars, (list, tuple)) or len(bars) < min_history + 1:
        result['reason'] = 'INSUFFICIENT_HISTORY'
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
            if type(v) not in (int, float) or type(c) not in (int, float):
                raise ValueError('bad types')
            if not isfinite(v) or not isfinite(c) or v < 0 or c <= 0:
                raise ValueError('bad values')
            volumes.append(v)
        times = [bar.get('timestamp') for bar in window]
        if any(t is not None for t in times):
            if any(t is None or isinstance(t, bool) for t in times):
                raise ValueError('bad chronology')
            if any(type(t) not in (str, int, float) for t in times):
                raise ValueError('unsupported timestamp type')
            if any(type(t) is not type(times[0]) for t in times):
                raise ValueError('mixed chronology types')
            if any((type(t) in (int, float) and not isfinite(t))
                   or (type(t) is str and not t.strip()) for t in times):
                raise ValueError('nonfinite or empty timestamp')
            if any(a >= b for a, b in zip(times, times[1:])):
                raise ValueError('unordered chronology')
    except (KeyError, TypeError, ValueError, OverflowError):
        result['reason'] = 'INVALID_BAR_DATA'
        return result
    try:
        base = median(volumes[:-1])
        if base <= 0:
            result['reason'] = 'ZERO_BASELINE'
            return result
        ratio = volumes[-1] / base
        if not isfinite(ratio):
            result['reason'] = 'INVALID_BAR_DATA'
            return result
        result['volume_ratio'] = round(ratio, 4)
    except (OverflowError, ZeroDivisionError, ValueError):
        result['reason'] = 'INVALID_BAR_DATA'
        return result
    result['signal'] = 'VOLUME_SPIKE' if ratio >= spike_ratio else 'NO_SPIKE'
    result['reason'] = 'OFFLINE_ONLY_NOT_VERIFIED'
    return result
