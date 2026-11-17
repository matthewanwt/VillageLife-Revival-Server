"""Synthetic gem debit boundaries; no original tables, assets or player data."""
from copy import deepcopy
from decimal import Decimal
import unittest

from villagelife.protocol.original_client.inventory import InsufficientGems, spend_gems


class GemDebitTests(unittest.TestCase):
    def test_invalid_costs_never_grant_or_change_currency(self):
        for cost in (-5, Decimal('-0.25'), Decimal('NaN'), Decimal('Infinity'),
                     float('nan'), float('inf'), 0.0, 1.5, True, False, None, '5'):
            with self.subTest(cost=repr(cost)):
                state = {'inventory': {'323': 10, '8': 7}, 'opaque': {'keep': [1, 2]}}
                before = deepcopy(state)
                with self.assertRaises(ValueError):
                    spend_gems(state, cost)
                self.assertEqual(state, before)

    def test_zero_and_valid_integer_or_decimal_costs_keep_exact_balances(self):
        for cost, expected in ((0, 10), (Decimal('0'), 10), (3, 7), (Decimal('0.25'), 9.75)):
            with self.subTest(cost=cost):
                state = {'inventory': {'323': 10, '8': 7}, 'opaque': {'keep': [1, 2]}}
                spend_gems(state, cost)
                self.assertEqual(state, {'inventory': {'323': expected, '8': 7},
                                         'opaque': {'keep': [1, 2]}})

    def test_insufficient_integer_price_preserves_state_and_error_response(self):
        state = {'inventory': {'323': 10}, 'opaque': {'keep': True}}
        before = deepcopy(state)
        with self.assertRaises(InsufficientGems) as caught:
            spend_gems(state, 11)
        self.assertEqual(caught.exception.reply(), {'error': 'INSUFFICIENT_GEMS',
                         'gemsRequired': 11, 'gemsAvailable': 10.0, 'gemsShortfall': 1.0})
        self.assertEqual(state, before)


if __name__ == '__main__':
    unittest.main()
