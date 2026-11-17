import unittest
from research_risk_flags import RISK_FIELDS, assess


class ResearchRiskFlagsTests(unittest.TestCase):
    def test_missing_evidence_is_unknown_and_orders_blocked(self):
        report = assess({})
        self.assertEqual(set(report['unknown_fields']), set(RISK_FIELDS))
        self.assertEqual(report['status'], 'NOT_VALIDATED')
        self.assertEqual(report['sec_status'], 'SEC_UNVERIFIED')
        self.assertFalse(report['orders_enabled'])
        self.assertFalse(report['production_approved'])

    def test_keywords_and_unverified_claims_never_clear_risk(self):
        report = assess({'atm': {'verified': False, 'risk': False,
                                 'sec_url': 'https://www.sec.gov/Archives/example'}})
        self.assertEqual(report['fields']['atm']['state'], 'UNKNOWN')

    def test_non_sec_url_never_counts_as_primary_evidence(self):
        report = assess({'warrant': {'verified': True, 'risk': False,
                                     'sec_url': 'https://example.com/press-release'}})
        self.assertEqual(report['fields']['warrant']['state'], 'UNKNOWN')

    def test_explicit_primary_source_risk_is_flagged(self):
        report = assess({'cb_reset': {'verified': True, 'risk': True,
                                      'sec_url': 'https://www.sec.gov/Archives/edgar/data/1/filing.htm'}})
        self.assertEqual(report['fields']['cb_reset']['state'], 'RISK')
        self.assertIn('float', report['unknown_fields'])

    def test_boolean_risk_required(self):
        report = assess({'reverse_split': {'verified': True, 'risk': 'false',
                                          'sec_url': 'https://www.sec.gov/Archives/edgar/data/1/x.htm'}})
        self.assertEqual(report['fields']['reverse_split']['state'], 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
