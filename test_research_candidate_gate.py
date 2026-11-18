import unittest
from research_candidate_gate import evaluate_candidate
from research_risk_flags import RISK_FIELDS


def bars():
    return [{'timestamp': i, 'volume': 400 if i == 20 else 100, 'close': 2.0} for i in range(21)]


def evidence(risky=None):
    return {key: {'verified': True, 'risk': key == risky,
                  'sec_url': 'https://www.sec.gov/Archives/edgar/data/1/x.htm'}
            for key in RISK_FIELDS}


class CandidateGateTests(unittest.TestCase):
    def test_no_provenance(self):
        r = evaluate_candidate({'cohort': 'NASDAQ_7_0'}, bars(), evidence())
        self.assertEqual(r['decision'], 'HOLD_UNVERIFIED')
        self.assertIn('UNVERIFIED_UNIVERSE', r['reasons'])

    def test_china_requires_review(self):
        r = evaluate_candidate({'cohort': 'CHINA_1_0', 'universe_verified': True}, bars(), evidence())
        self.assertIn('UNVERIFIED_CHINA_LINK', r['reasons'])

    def test_missing_sec_blocks(self):
        r = evaluate_candidate({'cohort': 'NASDAQ_7_0', 'universe_verified': True}, bars(), {})
        self.assertIn('SEC_EVIDENCE_INCOMPLETE', r['reasons'])

    def test_disclosed_risk_blocks(self):
        r = evaluate_candidate({'cohort': 'NASDAQ_7_0', 'universe_verified': True}, bars(), evidence('cb_reset'))
        self.assertIn('DISCLOSED_RISK', r['reasons'])

    def test_complete_offline_is_review_only(self):
        r = evaluate_candidate({'cohort': 'NASDAQ_7_0', 'universe_verified': True}, bars(), evidence())
        self.assertEqual(r['decision'], 'RESEARCH_REVIEW_ONLY')
        self.assertEqual(r['status'], 'NOT_VALIDATED')
        self.assertEqual(r['sec_status'], 'SEC_UNVERIFIED')
        self.assertFalse(r['orders_enabled'])

    def test_spike_with_unverified_sec_host_stays_on_hold(self):
        bad = evidence()
        bad['cb_reset']['sec_url'] = 'https://www.sec.gov.evil.example/Archives/edgar/data/1/x.htm'
        r = evaluate_candidate({'cohort': 'NASDAQ_7_0', 'universe_verified': True}, bars(), bad)
        self.assertEqual(r['volume']['signal'], 'VOLUME_SPIKE')
        self.assertEqual(r['decision'], 'HOLD_UNVERIFIED')
        self.assertIn('SEC_EVIDENCE_INCOMPLETE', r['reasons'])
        self.assertEqual(r['risk']['fields']['cb_reset']['state'], 'UNKNOWN')
        self.assertFalse(r['orders_enabled'])
        self.assertFalse(r['production_approved'])

    def test_invalid_chronology_cannot_become_candidate(self):
        bad_bars = bars()
        bad_bars[-1]['timestamp'] = bad_bars[-2]['timestamp']
        r = evaluate_candidate({'cohort': 'CHINA_1_0', 'universe_verified': True,
                                'china_link_reviewed': True}, bad_bars, evidence())
        self.assertEqual(r['volume']['signal'], 'UNKNOWN')
        self.assertEqual(r['volume']['reason'], 'INVALID_BAR_DATA')
        self.assertEqual(r['decision'], 'HOLD_UNVERIFIED')
        self.assertIn('NO_CONFIRMED_VOLUME_SPIKE', r['reasons'])
        self.assertEqual(r['status'], 'NOT_VALIDATED')
        self.assertEqual(r['sec_status'], 'SEC_UNVERIFIED')
        self.assertFalse(r['orders_enabled'])

    def test_bad_inputs_do_not_approve(self):
        for candidate in (None, {}, {'cohort': 'CHINA_1_0', 'universe_verified': True, 'china_link_reviewed': True}):
            r = evaluate_candidate(candidate, [], None)
            self.assertEqual(r['decision'], 'HOLD_UNVERIFIED')
            self.assertFalse(r['orders_enabled'])


if __name__ == '__main__':
    unittest.main()
