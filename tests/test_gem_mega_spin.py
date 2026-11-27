"""Synthetic opt-in purchase/replay fixtures without game assets or player saves."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from test_original_client import fake_tables
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.services import OriginalClientGame


SERVICE = 'ClientFortune/GetGemMegaSpinResult'


class GemMegaSpinTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        tables = root / 'tables.sqlite'
        fake_tables(tables)
        self.defs = OriginalDefinitions(tables)
        rows = self.defs.rows
        fixtures = {
            'WofSet': [{'id': '1', 'CurrencyPayment': '766'}],
            'WofSetItem': [{'id': '1', 'WofSet': '1', 'Chance': '1', 'SlotIndex': '3',
                            'MaterialType': '323', 'Quantity': '7', 'ShouldMultiply': '0'}],
        }
        self.defs.rows = lambda table: fixtures.get(table, rows(table))
        self.path = root / 'save.sqlite'
        self.repo = SqliteSaveRepository(self.path)
        self.game = OriginalClientGame(self.repo, self.defs, enable_gem_mega_spin=True)
        self.profile = self.game.login({'deviceId': 'synthetic-mega-device'})['data']['users'][0]
        self.identity = self.game.sessions.authenticate(self.profile)
        self.normal = {'areaId': 1, 'user': {'userLevelID': 1, 'NextDailySpinAt': 987654},
                       'inventory': {'323': 100}, 'world': {'entities': []}, 'revision': 1}

        def seed(payload):
            payload['originalSave']['normal'] = deepcopy(self.normal)
            payload['originalSave']['rng'] = {'algorithm': 'sha256-counter-v1', 'seed': 'ab' * 32, 'counter': 0}
            payload['hybridExtensions'] = {'optionalRewards': {'claimed': ['synthetic-existing']}}
            return {}

        self.repo.mutate(self.identity.village_id, operation_key='fixture', request={}, change=seed)

    def call(self, data, call_id='first', game=None, profile=None):
        response = (game or self.game).process({**(profile or self.profile), 'data': {'calls': [
            {'id': call_id, 'service': SERVICE, 'data': data},
        ]}})
        return response['data']['calls'][0]

    def saved(self):
        return deepcopy(self.repo.read_village(self.identity.village_id).payload)

    def test_debit_reward_and_intent_replay_survive_new_engine_session(self):
        request = {'intentId': '1' * 32, 'confirmedGemCost': 20}
        result = self.call(request)
        self.assertEqual(result['code'], 200, result)
        after = self.saved()
        self.assertEqual(after['originalSave']['normal']['inventory']['323'], 87)
        self.assertEqual(after['originalSave']['normal']['user'], self.normal['user'])
        self.assertEqual(after['hybridExtensions']['optionalRewards']['claimed'], ['synthetic-existing'])
        self.assertEqual(after['originalSave']['rng']['counter'], 1)
        retry = self.call(request, 'changed-transport-id')
        self.assertEqual(retry['code'], 200, retry)
        self.assertEqual(retry['data'], result['data'])
        self.assertEqual(self.saved()['originalSave'], after['originalSave'])
        engine = OriginalClientGame(SqliteSaveRepository(self.path), self.defs, enable_gem_mega_spin=True)
        profile = engine.login({'deviceId': 'synthetic-mega-device'})['data']['users'][0]
        replay = self.call(request, 'reopen-retry', engine, profile)
        self.assertEqual(replay['code'], 200, replay)
        self.assertEqual(self.saved()['originalSave']['normal']['inventory']['323'], 87)
        self.assertEqual(self.saved()['originalSave']['rng']['counter'], 1)

    def test_disabled_and_invalid_confirmation_never_purchase(self):
        ordinary = OriginalClientGame(self.repo, self.defs)
        before = self.saved()['originalSave']
        result = self.call({'intentId': '1' * 32, 'confirmedGemCost': 20}, game=ordinary)
        self.assertEqual(result['code'], 501, result)
        for data in ({}, {'intentId': '1' * 32, 'confirmedGemCost': True},
                     {'intentId': '1' * 32, 'confirmedGemCost': 19},
                     {'intentId': 'bad', 'confirmedGemCost': 20}):
            with self.subTest(data=data):
                result = self.call(data, json.dumps(data))
                self.assertEqual(result['code'], 400, result)
                self.assertEqual(self.saved()['originalSave'], before)

    def test_failed_draw_rolls_back_gems_and_random_counter(self):
        def fail(*args):
            args[-1]['counter'] += 1
            raise ValueError('Synthetic invalid reward definition')

        self.game.economy._draw_wheel = fail
        before = self.saved()['originalSave']
        result = self.call({'intentId': '2' * 32, 'confirmedGemCost': 20})
        self.assertEqual(result['code'], 400, result)
        self.assertEqual(self.saved()['originalSave'], before)

    def test_insufficient_balance_returns_existing_error(self):
        def empty_wallet(payload):
            payload['originalSave']['normal']['inventory']['323'] = 19
            return {}

        self.repo.mutate(self.identity.village_id, operation_key='poor-wallet', request={}, change=empty_wallet)
        before = self.saved()['originalSave']
        result = self.call({'intentId': '3' * 32, 'confirmedGemCost': 20})
        self.assertEqual(result['code'], 400, result)
        self.assertEqual(result['data']['error'], 'INSUFFICIENT_GEMS')
        self.assertEqual(self.saved()['originalSave'], before)
