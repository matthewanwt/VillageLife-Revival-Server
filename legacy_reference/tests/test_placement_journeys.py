"""Placement contracts: delayed retries, stable positions and neighbouring identities."""
import copy
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import buildings
import placement
import session
import world


class PlacementJourneys(unittest.TestCase):
    def setUp(self):
        self.state = world.build_bridge_world(session.fresh_tutorial(), 1000)
        self.state['inventory'].update({'323': 1000000, '325': 1000000})

    def create(self, ident=9, key='place', x=4000, y=4000):
        return placement.operate(self.state, 'ClientUserDecorItemService/CreateUserDecorItem',
            {'decorItemId': ident, 'x': x, 'y': y, 'rotation': 0, 'areaId': 1}, key)[0]['userDecorItem']

    def move(self, item, x, key, **extra):
        return placement.operate(self.state, 'ClientUtilityService/UpdatePosition',
            {'positionId': item['position']['id'], 'x': x, 'y': 4000, 'rotation': 1, 'areaId': 1, **extra}, key)

    def test_delayed_move_replay_does_not_undo_a_newer_move_after_reload(self):
        item = self.create()
        self.move(item, 4050, 'first'); self.move(item, 4100, 'second')
        self.state = json.loads(json.dumps(self.state)); before = copy.deepcopy(self.state)
        self.assertFalse(self.move(item, 4050, 'first')[1])
        self.assertEqual(self.state, before)

    def test_accepted_noop_move_also_cannot_revert_a_later_move(self):
        item = self.create()
        data = {'positionId': item['position']['id'], 'x': 4000, 'y': 4000, 'rotation': 0, 'areaId': 1}
        placement.operate(self.state, 'ClientUtilityService/UpdatePosition', data, 'noop')
        self.move(item, 4100, 'later'); before = copy.deepcopy(self.state)
        self.assertFalse(placement.operate(self.state, 'ClientUtilityService/UpdatePosition', data, 'noop')[1])
        self.assertEqual(self.state, before)

    def test_move_receipt_reuse_with_different_content_never_mutates(self):
        item = self.create(); self.move(item, 4050, 'same'); before = copy.deepcopy(self.state)
        with self.assertRaises(ValueError): self.move(item, 4100, 'same')
        self.assertEqual(self.state, before)

    def test_missing_xy_never_moves_an_object_to_the_origin(self):
        item = self.create()
        for missing in ('x', 'y'):
            data = {'positionId': item['position']['id'], 'x': 4050, 'y': 4000, 'rotation': 0, 'areaId': 1}
            data.pop(missing); before = copy.deepcopy(self.state)
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                placement.operate(self.state, 'ClientUtilityService/UpdatePosition', data, 'bad')
            self.assertEqual(self.state, before)

    def test_foundation_list_uses_the_same_saved_position_id_as_world_projection(self):
        entity = next(e for e in self.state['world']['entities'] if e['templateType'] == 'building_task')
        entity['positionId'] = 'existing-position-identity'
        record = buildings.placement_record(entity)
        projected = copy.deepcopy(entity); placement.project_position(projected)
        self.assertEqual(record['position']['id'], projected['position']['id'])

    def test_deleted_object_move_replay_does_not_resurrect_or_error(self):
        item = self.create(); self.move(item, 4050, 'move')
        placement.operate(self.state, 'ClientUserDecorItemService/DeleteUserDecorItem', {'userDecorItemId': item['userDecorItemId']}, 'delete')
        self.state = json.loads(json.dumps(self.state)); before = copy.deepcopy(self.state)
        self.assertFalse(self.move(item, 4050, 'move')[1]); self.assertEqual(self.state, before)

    def test_adjacent_objects_keep_independent_identity_and_currency_through_move_delete(self):
        first = self.create(key='one'); second = self.create(key='two', x=4025)
        self.assertNotEqual(first['position']['id'], second['position']['id'])
        survivor = copy.deepcopy(next(e for e in self.state['world']['entities'] if e['id'] == second['userDecorItemId']))
        balances = copy.deepcopy(self.state['inventory']); self.move(first, 4100, 'move')
        placement.operate(self.state, 'ClientUserDecorItemService/DeleteUserDecorItem', {'userDecorItemId': first['userDecorItemId']}, 'delete')
        self.state = json.loads(json.dumps(self.state))
        self.assertEqual(next(e for e in self.state['world']['entities'] if e['id'] == survivor['id']), survivor)
        self.assertEqual(self.state['inventory'], balances)
        projected = world.area_content(self.state, 1, 1000)['areaJson']['entities']
        self.assertEqual(sum(e['id'] == survivor['id'] for e in projected), 1)
        self.assertFalse(any(e['id'] == first['userDecorItemId'] for e in projected))

    def test_all555_owned_decorations_create_move_delete_and_project_after_reload(self):
        base = copy.deepcopy(self.state); count = 0
        for definition in world.rows('decor_item'):
            with self.subTest(decor=definition['id']):
                self.state = copy.deepcopy(base); material = definition['material_type']
                self.state['inventory'][material] = 2; bank = {k: self.state['inventory'][k] for k in ('323', '325')}
                first = self.create(int(definition['id']), key='first')
                second = self.create(int(definition['id']), key='second', x=4025)
                self.assertEqual(self.state['inventory'][material], 0)
                self.assertEqual({k: self.state['inventory'][k] for k in bank}, bank)
                self.move(first, 4100, 'move'); before = copy.deepcopy(self.state)
                self.assertFalse(self.create_replay(definition, 'first')[1]); self.assertEqual(self.state, before)
                placement.operate(self.state, 'ClientUserDecorItemService/DeleteUserDecorItem', {'userDecorItemId': first['userDecorItemId']}, 'delete')
                self.state = json.loads(json.dumps(self.state)); before = copy.deepcopy(self.state)
                self.assertFalse(placement.operate(self.state, 'ClientUserDecorItemService/DeleteUserDecorItem', {'userDecorItemId': first['userDecorItemId']}, 'delete-again')[1])
                self.assertEqual(self.state, before)
                projected = world.area_content(self.state, 1, 1000)['areaJson']['entities']
                self.assertFalse(any(e['id'] == first['userDecorItemId'] for e in projected))
                survivor = next(e for e in projected if e['id'] == second['userDecorItemId'])
                self.assertEqual(survivor['position']['x'], 4025); self.assertEqual(survivor['position']['id'], second['position']['id'])
                self.assertEqual(self.state['inventory'][material], 0); count += 1
        self.assertEqual(count, 555)

    def create_replay(self, definition, key):
        return placement.operate(self.state, 'ClientUserDecorItemService/CreateUserDecorItem',
            {'decorItemId': int(definition['id']), 'x': 4000, 'y': 4000, 'rotation': 0, 'areaId': 1}, key)

    def test_completed_bridge_milestone_is_not_a_required_stock_item(self):
        self.assertEqual(self.state['transitionKey'], 'bridge-1-to-2')
        self.assertNotIn('130', self.state['inventory'])
        for ident in (9, 40):
            self.state['inventory'][world.by_id('decor_item', ident)['material_type']] = 0
            self.create(ident, key='ordinary-' + str(ident))
        self.assertNotIn('130', self.state['inventory'])

    def test_bridge_gate_still_rejects_unproven_transition_without_charging(self):
        self.state.pop('transitionKey'); self.state['scenarioId'] = 1
        self.state['inventory']['356'] = 0; before = copy.deepcopy(self.state)
        with self.assertRaises(ValueError): self.create()
        self.assertEqual(self.state, before)

    def test_completed_bridge_does_not_satisfy_unrelated_material_requirement(self):
        self.state['inventory']['77'] = 0; self.state['inventory']['356'] = 0
        original_rows = world.rows
        def rows(table):
            values = original_rows(table)
            if table == 'requirement_set_item':
                values.append({'requirementSet': '209', 'materialType': '77', 'quantity': '1', 'quantityUsed': '0'})
            return values
        before = copy.deepcopy(self.state)
        with patch.object(world, 'rows', side_effect=rows), self.assertRaises(ValueError): self.create()
        self.assertEqual(self.state, before)

    def test_all259_visible_decorations_charge_original_prices_once_and_refuse_poor_stock(self):
        base = copy.deepcopy(self.state); count = 0
        for definition in world.rows('decor_item'):
            if definition['hidden'] != '0': continue
            with self.subTest(decor=definition['id']):
                self.state = copy.deepcopy(base); self.state['inventory'][definition['material_type']] = 0
                bank = {k: self.state['inventory'][k] for k in ('323', '325')}
                self.create(int(definition['id']))
                for key, field in [('323', 'price_gems'), ('325', 'price_coins')]:
                    self.assertEqual(self.state['inventory'][key], bank[key] - int(definition[field]))
                before = copy.deepcopy(self.state); self.assertFalse(self.create_replay(definition, 'place')[1]); self.assertEqual(self.state, before)
                for key, field in [('323', 'price_gems'), ('325', 'price_coins')]:
                    if int(definition[field]) <= 0: continue
                    self.state = copy.deepcopy(base); self.state['inventory'][definition['material_type']] = 0
                    self.state['inventory'][key] = int(definition[field]) - 1; before = copy.deepcopy(self.state)
                    with self.assertRaises(ValueError): self.create(int(definition['id']))
                    self.assertEqual(self.state, before)
                count += 1
        self.assertEqual(count, 259)


class AuthenticatedPlacementJourney(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        scope = patch.object(session, 'STATE', Path(self.tmp.name)); scope.start(); self.addCleanup(scope.stop)
        self.profile = session.login({'deviceId': 'placement-journey'})['data']['users'][0]
        self.path = session.profile_path('placement-journey').with_suffix('.tutorial.json')
        state = world.build_bridge_world(session.fresh_tutorial(), 1000)
        state['inventory'].update({'323': 1000000, '325': 1000000, '356': 0})
        session.atomic_json(self.path, {**session.fresh_tutorial(), 'version': 3, 'normal': state,
            'gameSettings': {'activeSequenceId': '-1', 'isFtueComplete': '1'}})

    def call(self, service, data, ident):
        with patch.object(session, 'wire_time', return_value=1000):
            return session.process({**self.profile, 'data': {'calls': [{'id': ident, 'service': service, 'data': data}]}}, native_ids=True)['data']['calls'][0]

    def test_native_saved_route_move_retry_delete_and_reload(self):
        created = self.call('ClientUserDecorItemService/CreateUserDecorItem', {'decorItemId': 9, 'x': 4000, 'y': 4000, 'rotation': 0, 'areaId': 1}, 'place')
        self.assertEqual(created['code'], 200); item = created['data']['userDecorItem']
        first = {'positionId': item['position']['id'], 'x': 4050, 'y': 4000, 'rotation': 1, 'areaId': 1}
        second = {**first, 'x': 4100, 'rotation': 0}
        for data, ident in [(first, 'move-one'), (second, 'move-two'), (first, 'move-one')]:
            self.assertEqual(self.call('ClientUtilityService/UpdatePosition', data, ident)['code'], 200)
        saved = json.loads(self.path.read_text())['normal']; entity = next(e for e in saved['world']['entities'] if e['id'] == item['userDecorItemId'])
        self.assertEqual(entity['position']['x'], 4100)
        self.assertEqual(saved['inventory']['325'], 999980)
        self.assertEqual(self.call('ClientUserDecorItemService/DeleteUserDecorItem', {'userDecorItemId': item['userDecorItemId']}, 'delete')['code'], 200)
        before = self.path.read_bytes()
        self.assertEqual(self.call('ClientUtilityService/UpdatePosition', first, 'move-one')['code'], 200)
        self.assertEqual(self.path.read_bytes(), before)
        area = self.call('ClientStartupService/GetAreaContent', {'areaId': 1}, 'area')['data']['areaJson']['entities']
        self.assertFalse(any(e['id'] == item['userDecorItemId'] for e in area))
