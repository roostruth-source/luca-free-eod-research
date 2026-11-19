import unittest
from research_sec_numeric_leads import extract_numeric_leads


class NumericLeadTests(unittest.TestCase):
    def test_reset_price_and_discount_leads(self):
        text = 'Variable conversion price resets at $0.25 with a 50% discount.'
        result = extract_numeric_leads(text)
        self.assertEqual(result['sec_status'], 'SEC_UNVERIFIED')
        self.assertFalse(result['orders_enabled'])
        leads = result['numeric_leads']
        self.assertTrue(any(x['literal'] == '$0.25' and x['kind'] == 'currency' for x in leads))
        self.assertTrue(any(x['literal'] == '50%' and x['kind'] == 'percent' for x in leads))
        self.assertTrue(all(text[x['start']:x['end']] == x['literal'] for x in leads))

    def test_no_keyword_no_numeric_leads(self):
        self.assertEqual(extract_numeric_leads('Revenue rose by 50%.')['numeric_leads'], [])

    def test_missing_explicit_unit_remains_unclassified(self):
        result = extract_numeric_leads('Variable conversion price is 0.25.')
        self.assertTrue(all(x['kind'] != 'currency' for x in result['numeric_leads']))

    def test_invalid_limits_fail_closed(self):
        for kwargs in ({'context': True}, {'context': -1}, {'max_leads': 0},
                       {'max_leads': 1.5}):
            result = extract_numeric_leads('variable conversion price $0.25', **kwargs)
            self.assertEqual(result['decision'], 'HOLD_UNVERIFIED')
            self.assertEqual(result['numeric_leads'], [])
            self.assertEqual(result['flags'], {})

    def test_oversize_rejected(self):
        result = extract_numeric_leads('warrant ' * 100, max_chars=10)
        self.assertEqual(result['reason'], 'INVALID_OR_OVERSIZED_TEXT')
        self.assertEqual(result['numeric_leads'], [])

    def test_unrelated_distant_numbers_not_treated_as_terms(self):
        text = 'Variable conversion price is $0.25. ' + ('ordinary narrative words ' * 5) + '2026 revenue was 9000.'
        leads = extract_numeric_leads(text, context=300)['numeric_leads']
        self.assertTrue(any(x['literal'] == '$0.25' for x in leads))
        self.assertFalse(any(x['literal'] in ('2026', '9000') for x in leads))

    def test_calendar_year_near_conversion_price_is_not_a_term(self):
        result = extract_numeric_leads('In 2026 the variable conversion price is $0.25.')
        literals = [x['literal'] for x in result['numeric_leads']]
        self.assertIn('$0.25', literals)
        self.assertNotIn('2026', literals)

    def test_explicit_currency_year_sized_number_kept_for_review(self):
        result = extract_numeric_leads('Variable conversion price is $2,026.')
        self.assertTrue(any(x['literal'] == '$2,026' for x in result['numeric_leads']))

    def test_calendar_year_suppression_does_not_hide_percent(self):
        result = extract_numeric_leads('Variable conversion price with 20% discount in 2026.')
        literals = [x['literal'] for x in result['numeric_leads']]
        self.assertIn('20%', literals)
        self.assertNotIn('2026', literals)

    def test_signed_negative_price_not_misread_as_positive(self):
        result = extract_numeric_leads('Variable conversion price is -0.25.')
        self.assertFalse(any(x['literal'] == '0.25' for x in result['numeric_leads']))

    def test_unicode_signed_price_not_misread_as_unsigned(self):
        for sign in ('−', '–', '—', '﹣', '－', '＋'):
            with self.subTest(sign=sign):
                result = extract_numeric_leads('Variable conversion price is ' + sign + '0.25.')
                self.assertFalse(any(x['literal'] == '0.25' for x in result['numeric_leads']))
                self.assertEqual(result['sec_status'], 'SEC_UNVERIFIED')
                self.assertFalse(result['orders_enabled'])

    def test_spaced_signed_amounts_not_reported_as_positive(self):
        for amount in ('- $0.25', '+ $0.25', '− $0.25', '– 0.25', '＋ $0.25'):
            with self.subTest(amount=amount):
                result = extract_numeric_leads('Variable conversion price is ' + amount + '.')
                self.assertEqual(result['numeric_leads'], [])
                self.assertEqual(result['decision'], 'HOLD_UNVERIFIED')
                self.assertEqual(result['sec_status'], 'SEC_UNVERIFIED')
                self.assertFalse(result['orders_enabled'])

    def test_accounting_negative_currency_not_reported_positive(self):
        # Parentheses commonly represent negative values in financial documents.
        result = extract_numeric_leads('Variable conversion price is ($0.25).')
        self.assertFalse(any(x['literal'] == '$0.25' for x in result['numeric_leads']))
        self.assertEqual(result['sec_status'], 'SEC_UNVERIFIED')
        self.assertFalse(result['orders_enabled'])

    def test_spaced_accounting_negative_not_reported_as_positive(self):
        for amount in ('($ 0.25)', '( $0.25 )', '( 0.25 )'):
            with self.subTest(amount=amount):
                result = extract_numeric_leads('Variable conversion price is ' + amount + '.')
                self.assertEqual(result['numeric_leads'], [])
                self.assertEqual(result['sec_status'], 'SEC_UNVERIFIED')
                self.assertFalse(result['orders_enabled'])

    def test_clipped_number_at_context_boundary_not_reported(self):
        text = 'Variable conversion price is $0.25 and unrelated 123456789.'
        result = extract_numeric_leads(text, context=8)
        self.assertFalse(any(x['literal'] in ('123', '1234', '12345') for x in result['numeric_leads']))
        self.assertEqual(result['sec_status'], 'SEC_UNVERIFIED')
        self.assertFalse(result['orders_enabled'])

    def test_malformed_grouping_not_extracted_as_fragments(self):
        # Malformed comma groups must not be parsed as partial prices.
        for amount in ('1,23', '12,34', '1,234,56', '1234,567'):
            with self.subTest(amount=amount):
                result = extract_numeric_leads('Variable conversion price is $' + amount + '.')
                self.assertEqual(result['numeric_leads'], [])
                self.assertEqual(result['decision'], 'HOLD_UNVERIFIED')
                self.assertEqual(result['sec_status'], 'SEC_UNVERIFIED')
                self.assertFalse(result['orders_enabled'])

    def test_valid_grouped_currency_preserved(self):
        result = extract_numeric_leads('Variable conversion price is $1,234.56.')
        self.assertTrue(any(x['literal'] == '$1,234.56' for x in result['numeric_leads']))

    def test_bounded_output(self):
        text = 'Variable conversion price ' + ' '.join('$0.25' for _ in range(40))
        result = extract_numeric_leads(text, max_leads=2)
        self.assertLessEqual(len(result['numeric_leads']), 2)


if __name__ == '__main__':
    unittest.main()
