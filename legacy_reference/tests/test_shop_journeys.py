"""Shop boundaries and actual authenticated save/reload journeys."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import learning
import session
import shop
import world


class ShopDefinitionJourneys(unittest.TestCase):
    def state(self):
        return {'inventory': {'323': 1000000}, 'user': {'userLevelID': 100000}, 'revision': 1}

    def test_every_store_bundle_cost_delivery_replay_and_failure(self):
        for row in world.rows('store_item'):
            for multiples in (1, 2, 100):
                with self.subTest(store=row['id'], multiples=multiples):
                    state = self.state()
                    data = {'storeItemId': int(row['id']), 'multiples': multiples}
                    cost, amount = int(row['price_gems']) * multiples, int(row['qty']) * multiples
                    reply, changed = shop.buy_store(state, data, 'bundle')
                    self.assertTrue(changed)
                    self.assertEqual(state['inventory']['323'], 1000000 - cost)
                    self.assertEqual(state['inventory'][row['material_type']], amount)
                    self.assertTrue(any(v['materialTypeId'] == int(row['material_type']) and v['amount'] == amount for v in reply['inventory']))
                    state = json.loads(json.dumps(state))
                    # Cached replies must reflect later inventory, not an old snapshot.
                    state['inventory'][row['material_type']] += 1
                    before = copy.deepcopy(state)
                    again, changed = shop.buy_store(state, data, 'bundle')
                    self.assertFalse(changed)
                    self.assertEqual(state, before)
                    self.assertEqual(next(v['amount'] for v in again['inventory'] if v['materialTypeId'] == int(row['material_type'])), amount + 1)
                    poor = self.state(); poor['inventory']['323'] = cost - 1
                    before = copy.deepcopy(poor)
                    with self.assertRaises(ValueError): shop.buy_store(poor, data, 'poor')
                    self.assertEqual(poor, before)

    def test_every_sellable_material_cost_proceeds_and_replay(self):
        count = 0
        for row in world.rows('material_type'):
            if int(row['coinsRatio'] or 0) <= 0 or row['id'] in {'323', '325'}:
                continue
            count += 1
            with self.subTest(material=row['id']):
                state = self.state(); state['inventory'].update({row['id']: 5, '325': 7})
                data = {'materialTypeId': int(row['id']), 'amount': 3}
                shop.sell(state, data, 'sale')
                self.assertEqual(state['inventory'][row['id']], 2)
                self.assertEqual(state['inventory']['325'], 7 + 3 * int(row['coinsRatio']))
                state = json.loads(json.dumps(state)); before = copy.deepcopy(state)
                self.assertFalse(shop.sell(state, data, 'sale')[1]); self.assertEqual(state, before)
                with self.assertRaises(ValueError): shop.sell(state, data, 'second-sale')
                self.assertEqual(state, before)
        self.assertEqual(count, 283)

    def test_shop_rejected_inputs_do_not_mutate(self):
        for operation, requests in [
            (shop.buy, [{'materialTypeId': 77, 'amount': v} for v in [True, 0, -1, 51, 1.5, '3', None]]),
            (shop.buy_store, [{'storeItemId': 0, 'multiples': v} for v in [True, 0, -1, 101, 1.5, '1', None]]),
            (shop.sell, [{'materialTypeId': 16, 'amount': v} for v in [True, 0, -1, 6, 1.5, '1', None]])]:
            for data in requests:
                state = self.state(); state['inventory']['16'] = 5; before = copy.deepcopy(state)
                with self.subTest(operation=operation.__name__, data=data), self.assertRaises(ValueError):
                    operation(state, data, 'bad')
                self.assertEqual(state, before)
        for operation, data in [(shop.buy, {'materialTypeId': 77, 'amount': 3}), (shop.buy_store, {'storeItemId': 0, 'multiples': 1}), (shop.sell, {'materialTypeId': 16, 'amount': 1})]:
            state = self.state(); state['inventory']['16'] = 5; before = copy.deepcopy(state)
            with self.assertRaises(ValueError): operation(state, data, '')
            self.assertEqual(state, before)

    def test_level_gate_and_reused_store_sale_receipts_are_atomic(self):
        state = self.state(); state['user']['userLevelID'] = 3; before = copy.deepcopy(state)
        with self.assertRaises(ValueError): shop.buy(state, {'materialTypeId': 16, 'amount': 1}, 'level')
        self.assertEqual(state, before)
        for operation, first, second in [
            (shop.buy_store, {'storeItemId': 0, 'multiples': 1}, {'storeItemId': 1, 'multiples': 1}),
            (shop.sell, {'materialTypeId': 16, 'amount': 1}, {'materialTypeId': 16, 'amount': 2})]:
            state = self.state(); state['inventory']['16'] = 5
            operation(state, first, 'same'); before = copy.deepcopy(state)
            with self.assertRaises(ValueError): operation(state, second, 'same')
            self.assertEqual(state, before)


class AuthenticatedShopJourney(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        scope = patch.object(session, 'STATE', Path(self.tmp.name)); scope.start(); self.addCleanup(scope.stop)
        self.profile = session.login({'deviceId': 'stage-one-shop'})['data']['users'][0]
        self.path = session.profile_path('stage-one-shop').with_suffix('.tutorial.json')
        state = world.build_bridge_world(session.fresh_tutorial(), 1000)
        state['user'].update(userLevel=4, userLevelID=4)
        state['inventory'].update({'323': 1000, '325': 0, '16': 5})
        state['inventory'].pop('178', None)
        session.atomic_json(self.path, {**session.fresh_tutorial(), 'version': 3,
            'normal': state, 'gameSettings': {'activeSequenceId': '-1', 'isFtueComplete': '1'}})

    def call(self, method, data, ident, at=1000, profile=None):
        with patch.object(session, 'wire_time', return_value=at):
            return session.process({**(profile or self.profile), 'data': {'calls': [
                {'id': ident, 'service': 'ClientMaterialService/' + method, 'data': data}]}}, native_ids=True)['data']['calls'][0]

    def saved(self): return json.loads(self.path.read_text())

    def test_buy_bundle_sell_learning_read_reload_and_second_purchase(self):
        for method, data, ident in [
            ('BuyMaterialType', {'materialTypeId': 77, 'amount': 3}, 'vines'),
            ('BuyStoreItem', {'storeItemId': 0, 'multiples': 1}, 'oil'),
            ('SellMaterialType', {'materialTypeId': 16, 'amount': 3}, 'berries'),
            ('StartLearningMaterial', {'materialTypeId': 178}, 'learn')]:
            self.assertEqual(self.call(method, data, ident)['code'], 200)
            before = self.saved()
            self.assertEqual(self.call(method, data, ident)['code'], 200)
            self.assertEqual(self.saved(), before)
        self.assertEqual(self.saved()['normal']['inventory']['323'], 988)
        self.assertEqual(self.saved()['normal']['inventory']['325'], 15)
        self.assertEqual(self.call('CompleteLearningMaterial', {'materialTypeId': 178}, 'early', 1059)['code'], 400)
        self.assertEqual(self.call('CompleteLearningMaterial', {'materialTypeId': 178}, 'done', 1060)['code'], 200)
        self.profile = session.login({'deviceId': 'stage-one-shop'})['data']['users'][0]
        reply = self.call('GetUserMaterialTypes', {}, 'read', 1061)
        item = next(v for v in reply['data']['inventory'] if v['materialTypeId'] == 178)
        self.assertTrue(item['isUnlocked']); self.assertEqual(item['amount'], 0)
        self.assertEqual(self.saved()['normal']['inventory']['323'], 988)
        self.assertEqual(self.call('BuyMaterialType', {'materialTypeId': 77, 'amount': 3}, 'vines', 1062)['code'], 200)
        self.assertEqual(self.saved()['normal']['inventory']['323'], 986)

    def test_unauthorised_transactions_do_not_change_any_saved_file(self):
        before = {p.name: p.read_bytes() for p in Path(self.tmp.name).iterdir() if p.is_file()}
        profile = {**self.profile, 'sessionId': 'invalid'}
        for method, data in [('BuyStoreItem', {'storeItemId': 0, 'multiples': 1}),
                             ('SellMaterialType', {'materialTypeId': 16, 'amount': 1}),
                             ('StartLearningMaterial', {'materialTypeId': 178})]:
            self.assertEqual(self.call(method, data, 'forbidden', profile=profile)['code'], 403)
        self.assertEqual({p.name: p.read_bytes() for p in Path(self.tmp.name).iterdir() if p.is_file()}, before)

    def test_completed_legacy_village_read_preserves_balances_and_xp(self):
        saved = self.saved(); state = saved['normal']
        state['inventory'].update({'323': 1000000, '325': 91, '77': 17, '16': 0})
        state['user']['xp'] = 806
        state.pop('scriptEffects', None)
        session.atomic_json(self.path, saved)
        before_inventory = copy.deepcopy(state['inventory'])
        self.assertEqual(self.call('GetUserMaterialTypes', {}, 'legacy-read')['code'], 200)
        after = self.saved()['normal']
        self.assertEqual(after['inventory'], before_inventory)
        self.assertEqual(after['user']['xp'], 806)
        self.assertTrue(after['scriptEffects']['inventoryAssignments'])
        before = self.saved()
        self.assertEqual(self.call('GetUserMaterialTypes', {}, 'legacy-read-again')['code'], 200)
        self.assertEqual(self.saved(), before)
