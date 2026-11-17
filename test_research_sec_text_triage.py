import unittest
from research_sec_text_triage import triage_sec_text, PATTERNS


class SecTextTriageTests(unittest.TestCase):
    def test_mentions_require_review_not_clearance(self):
        r = triage_sec_text('Convertible notes with a reset price and warrants; reverse stock split.')
        for field in ('convertible_note', 'cb_reset', 'warrant', 'reverse_split'):
            self.assertEqual(r['flags'][field]['state'], 'REVIEW_MENTION')
        self.assertEqual(r['flags']['atm']['state'], 'UNKNOWN')
        self.assertEqual(r['decision'], 'HOLD_UNVERIFIED')
        self.assertEqual(r['sec_status'], 'SEC_UNVERIFIED')
        self.assertFalse(r['orders_enabled'])

    def test_all_categories_are_never_clear(self):
        r = triage_sec_text('No relevant disclosure identified.')
        self.assertEqual(set(r['flags']), set(PATTERNS))
        self.assertTrue(all(v['state'] == 'UNKNOWN' for v in r['flags'].values()))

    def test_whitespace_and_case(self):
        r = triage_sec_text('AT-THE-MARKET\n sales agreement; PUBLIC   FLOAT; minimum bid price')
        for key in ('atm', 'float', 'listing_compliance'):
            self.assertEqual(r['flags'][key]['state'], 'REVIEW_MENTION')

    def test_bad_input_fails_closed(self):
        for text in (None, '', '   ', 1, 'x' * 30):
            r = triage_sec_text(text, max_chars=20)
            self.assertEqual(r['decision'], 'HOLD_UNVERIFIED')
            self.assertEqual(r['flags'], {})
            self.assertEqual(r['reason'], 'INVALID_OR_OVERSIZED_TEXT')

    def test_invalid_limit(self):
        for limit in (True, 0, -1, 1.5):
            self.assertEqual(triage_sec_text('warrant', max_chars=limit)['flags'], {})


if __name__ == '__main__':
    unittest.main()
