import unittest
from research_sec_evidence import extract_review_evidence


class EvidenceTests(unittest.TestCase):
    def test_offsets_and_newlines(self):
        text = 'Intro\nvariable conversion price\nplus warrants'
        result = extract_review_evidence(text, context=4)
        for field in ('cb_reset', 'warrant'):
            self.assertEqual(result['flags'][field]['state'], 'REVIEW_MENTION')
            hit = result['evidence'][field][0]
            self.assertIn(text[hit['start']:hit['end']], hit['excerpt'])
        self.assertEqual(result['sec_status'], 'SEC_UNVERIFIED')
        self.assertFalse(result['orders_enabled'])

    def test_no_match_is_not_clearance(self):
        result = extract_review_evidence('Routine annual report.')
        self.assertTrue(all(v['state'] == 'UNKNOWN' for v in result['flags'].values()))
        self.assertTrue(all(not hits for hits in result['evidence'].values()))

    def test_invalid_limits_fail_closed(self):
        for kw in ({'context': True}, {'context': -1}, {'max_hits': 0}, {'max_hits': 1.5}):
            result = extract_review_evidence('warrant', **kw)
            self.assertEqual(result['decision'], 'HOLD_UNVERIFIED')
            self.assertEqual(result['flags'], {})

    def test_bounded_and_sorted(self):
        result = extract_review_evidence('warrant ' * 40, context=0, max_hits=2)
        self.assertEqual(len(result['evidence']['warrant']), 2)
        self.assertLess(result['evidence']['warrant'][0]['start'], result['evidence']['warrant'][1]['start'])

    def test_oversized_text(self):
        result = extract_review_evidence('warrant' * 100, max_chars=10)
        self.assertEqual(result['reason'], 'INVALID_OR_OVERSIZED_TEXT')
        self.assertEqual(result['evidence'], {})


if __name__ == '__main__':
    unittest.main()
