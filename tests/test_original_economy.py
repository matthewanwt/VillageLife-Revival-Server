import unittest
import uuid
from pathlib import Path

from test_original_client import fake_tables
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.economy import OriginalEconomyRules


class OriginalEconomyTests(unittest.TestCase):
    def setUp(self):
        root = Path('.test-tmp') / ('original-economy-' + uuid.uuid4().hex)
        root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(lambda: __import__('shutil').rmtree(root, ignore_errors=True))
        database = root / 'tables.sqlite'
        fake_tables(database)
        self.rules = OriginalEconomyRules(OriginalDefinitions(database))
        original_rows = self.rules.defs.rows
        rows = {
            'material_type': [
                {'id': '323', 'name': 'Gems', 'minPurchasable': '1', 'maxPurchasable': '99', 'unlockLevel': '1', 'gemsRatio': '0', 'coinsRatio': '0'},
                {'id': '325', 'name': 'Coins', 'minPurchasable': '1', 'maxPurchasable': '99', 'unlockLevel': '1', 'gemsRatio': '0', 'coinsRatio': '0'},
                {'id': '11', 'name': 'Wood', 'minPurchasable': '1', 'maxPurchasable': '10', 'unlockLevel': '1', 'gemsRatio': '2', 'coinsRatio': '3'}],
            'store_item': [{'id': '1', 'price_gems': '5', 'qty': '2', 'material_type': '11'}],
        }
        self.rules.defs.rows = lambda table: rows.get(table, original_rows(table))
        self.state = {'revision': 1, 'user': {'userLevelID': 1}, 'inventory': {'323': 20, '11': 5}}

    def test_buy_sell_and_replay_are_persistent(self):
        self.rules.buy_material(self.state, {'materialTypeId': 11, 'amount': 2}, 'buy')
        self.assertEqual(self.state['inventory']['323'], 16.0)
        self.assertEqual(self.state['inventory']['11'], 7.0)
        self.rules.buy_material(self.state, {'materialTypeId': 11, 'amount': 2}, 'buy')
        self.assertEqual(self.state['inventory']['11'], 7.0)
        self.rules.sell_material(self.state, {'materialTypeId': 11, 'amount': 2}, 'sell')
        self.assertEqual(self.state['inventory']['325'], 6.0)

    def test_store_purchase_checks_gem_balance(self):
        self.rules.buy_store_item(self.state, {'storeItemId': 1, 'multiples': 2}, 'store')
        self.assertEqual(self.state['inventory']['323'], 10.0)
        self.assertEqual(self.state['inventory']['11'], 9.0)
