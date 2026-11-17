"""Synthetic collection acknowledgement fixtures; no assets or player saves."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from villagelife.protocol.original_client import collection
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.services import OriginalClientGame
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from test_original_client import fake_tables


class CollectionAcknowledgementTests(unittest.TestCase):
    def test_awarded_states_become_collected_without_another_reward(self):
        for status in (1, 2, 3):
            with self.subTest(status=status):
                state = {'villagerCollection': {'123': status, '124': 0, '125': 3},
                         'inventory': {'323': 77}, 'world': {'entities': []},
                         'opaque': {'retained': [1, 2]}}
                expected = deepcopy(state)
                expected['villagerCollection']['123'] = 3
                self.assertEqual(collection.collect_villager(state, {'VillagerBaseId': 123}), {})
                self.assertEqual(state, expected)
                self.assertEqual(collection.collect_villager(state, {'VillagerBaseId': 123}), {})
                self.assertEqual(state, expected)

    def test_invalid_or_unawarded_identifier_does_not_create_collection(self):
        for request in ({}, {'VillagerBaseId': True}, {'VillagerBaseId': '123'},
                        {'VillagerBaseId': -1}, {'VillagerBaseId': 999}, {'VillagerBaseId': 124}):
            for state in ({'inventory': {'323': 77}}, {'villagerCollection': {'123': 2, '124': 0}}):
                with self.subTest(request=request, state=state):
                    before = deepcopy(state)
                    with self.assertRaises(ValueError):
                        collection.collect_villager(state, request)
                    self.assertEqual(state, before)

    def test_unknown_saved_status_is_not_silently_repaired(self):
        for status in (True, '2', None, 4, -1):
            state = {'villagerCollection': {'123': status}}
            before = deepcopy(state)
            with self.assertRaises(ValueError):
                collection.collect_villager(state, {'VillagerBaseId': 123})
            self.assertEqual(state, before)

    def test_authenticated_acknowledgement_replay_and_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tables = root/'tables.sqlite'; fake_tables(tables)
            defs = OriginalDefinitions(tables)
            path = root/'synthetic.sqlite'
            repo = SqliteSaveRepository(path)
            game = OriginalClientGame(repo, defs)
            identity, profile, _ = game.sessions.login('synthetic-collection-device')
            def seed(payload):
                payload['originalSave'] = {
                    'normal': {'areaId': 1, 'revision': 1,
                               'user': {'userLevelID': 1, 'xp': 0},
                               'inventory': {'323': 77}, 'world': {'entities': []},
                               'villagerCollection': {'123': 2, '124': 0},
                               'opaque': {'keep': True}}}
                return {}
            repo.mutate(identity.village_id, operation_key='synthetic-seed', request={}, change=seed)
            request = {'deviceId': 'synthetic-collection-device', 'pId': profile['pId'],
                       'sessionId': profile['sessionId'], 'data': {'calls': [{
                           'id': 'collect-1', 'service': 'ClientVillagerService/CollectVillager',
                           'data': {'VillagerBaseId': 123}}]}}
            response = game.process(request)
            self.assertEqual(response['data']['calls'][0]['code'], 200, response)
            saved = repo.read_village(identity.village_id)
            self.assertEqual(game.process(request)['data']['calls'], response['data']['calls'])
            self.assertEqual(repo.read_village(identity.village_id), saved)
            reopened = SqliteSaveRepository(path)
            normal = reopened.read_village(identity.village_id).payload['originalSave']['normal']
            self.assertEqual(normal['villagerCollection'], {'123': 3, '124': 0})
            self.assertEqual(normal['inventory'], {'323': 77})
            self.assertEqual(normal['world']['entities'], [])
            self.assertEqual(normal['opaque'], {'keep': True})
            self.assertEqual(collection.read_collection(normal)['VillagerCollection'], '{"123":2,"124":0}')
            before_rejected = reopened.read_village(identity.village_id)
            invalid = deepcopy(request)
            invalid['data']['calls'][0].update(id='unawarded', data={'VillagerBaseId': 124})
            self.assertEqual(game.process(invalid)['data']['calls'][0]['code'], 400)
            self.assertEqual(reopened.read_village(identity.village_id), before_rejected)


if __name__ == '__main__':
    unittest.main()
