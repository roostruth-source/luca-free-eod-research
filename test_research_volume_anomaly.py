import unittest
from research_volume_anomaly import inspect_volume


def bars(n=21, last=400):
    return [{'timestamp': i, 'volume': last if i == n-1 else 100, 'close': 2.0} for i in range(n)]


class VolumeResearchTests(unittest.TestCase):
    def test_spike_and_safe_state(self):
        r = inspect_volume(bars())
        self.assertEqual(r['signal'], 'VOLUME_SPIKE')
        self.assertEqual(r['volume_ratio'], 4)
        self.assertEqual(r['status'], 'NOT_VALIDATED')
        self.assertEqual(r['sec_status'], 'SEC_UNVERIFIED')
        self.assertFalse(r['orders_enabled'])

    def test_no_spike(self):
        self.assertEqual(inspect_volume(bars(last=120))['signal'], 'NO_SPIKE')

    def test_no_future_leakage(self):
        b = bars(n=22, last=400)
        b[-2]['volume'] = 100
        self.assertEqual(inspect_volume(b[:-1])['signal'], 'NO_SPIKE')
        self.assertEqual(inspect_volume(b)['signal'], 'VOLUME_SPIKE')

    def test_missing_and_bad_data(self):
        self.assertEqual(inspect_volume(bars(3))['signal'], 'UNKNOWN')
        for bad in (float('nan'), -1, True):
            b = bars()
            b[-1]['volume'] = bad
            self.assertEqual(inspect_volume(b)['signal'], 'UNKNOWN')

    def test_chronology_and_zero_baseline(self):
        b = bars()
        b[-1]['timestamp'] = 1
        self.assertEqual(inspect_volume(b)['reason'], 'INVALID_BAR_DATA')
        b = bars()
        for x in b[:-1]: x['volume'] = 0
        self.assertEqual(inspect_volume(b)['reason'], 'ZERO_BASELINE')

    def test_invalid_params(self):
        self.assertEqual(inspect_volume(bars(), spike_ratio=float('inf'))['signal'], 'UNKNOWN')
        self.assertEqual(inspect_volume(bars(), baseline_days=2)['signal'], 'UNKNOWN')

    def test_invalid_history_parameters_fail_closed(self):
        for bad in (None, 0, 1, -1, True, 2.5, '10'):
            with self.subTest(bad=bad):
                r = inspect_volume(bars(), min_history=bad)
                self.assertEqual(r['reason'], 'INVALID_PARAMETERS')
                self.assertEqual(r['signal'], 'UNKNOWN')
                self.assertFalse(r['orders_enabled'])

    def test_mixed_timestamps_fail_closed(self):
        for bad in ('2026-11-18', None, True, {'x': 1}):
            b = bars()
            b[-1]['timestamp'] = bad
            with self.subTest(bad=bad):
                self.assertEqual(inspect_volume(b)['reason'], 'INVALID_BAR_DATA')

    def test_extreme_ratio_fail_closed(self):
        b = bars()
        b[-1]['volume'] = 1e308
        for item in b[:-1]: item['volume'] = 1e-308
        self.assertEqual(inspect_volume(b)['reason'], 'INVALID_BAR_DATA')


if __name__ == '__main__':
    unittest.main()
