"""Achievement reconstruction and reward persistence."""
from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from test_original_client import fake_tables

from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.services import OriginalClientGame


def villager(ident, *, skills=(), area=1, start=1, born=None, clothing=(),
             married=None):
    person = {'id': ident, 'templateType': 'villager_type', 'templateId': 1,
              'gender': 0, 'position': {'x': 0, 'y': 0, 'areaId': area},
              'skills': [{'skilltypeId': skill, 'skillOriginType': 3}
                         for skill in skills],
              'clothing': [{'clothingSetId': value} for value in clothing],
              'startingArea': start, 'relations': []}
    if born is not None:
        person.update(bornAt=born, startAge=0)
    if married is not None:
        person['marriedAt'] = married
    return person


class OriginalAchievementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        fake_tables(root / 'tables.sqlite3')
        self.repo = SqliteSaveRepository(root / 'new.sqlite3')
        self.game = OriginalClientGame(
            self.repo, OriginalDefinitions(root / 'tables.sqlite3'))
        self.now = 1_800_000_000
        self.call_id = 0
        self.profile = self.login('achievement-device')
        self.identity = self.game.sessions.authenticate(self.profile)

    def login(self, device):
        response = self.game.login({'deviceId': device})
        self.assertEqual(response['code'], 200, response)
        return response['data']['users'][0]

    def seed(self, normal):
        def change(payload):
            payload['originalSave']['normal'] = normal
            return {}
        self.repo.mutate(self.identity.village_id,
                         operation_key='fixture:achievements:' + uuid.uuid4().hex,
                         request={}, change=change)

    def call(self, profile, service, data=None):
        self.call_id += 1
        request = {**{key: profile[key] for key in ('deviceId', 'sessionId', 'pId')},
                   'data': {'calls': [{'id': 'achievement-' + str(self.call_id),
                                       'service': service, 'data': data or {}}]}}
        with patch('time.time', return_value=self.now):
            return self.game.process(request)['data']['calls'][0]

    def records(self, profile=None):
        result = self.call(profile or self.profile,
                           'ClientAchievement/GetUserAchievements')
        self.assertEqual(result['code'], 200, result)
        return {record['GameAchievementId']: record
                for record in result['data']['result']}

    def state(self):
        return self.repo.read_village(self.identity.village_id).payload[
            'originalSave']['normal']

    def seed_full_village(self):
        created = self.now - 26 * 86400
        entities = [
            villager('m1', skills=(2, 2, 2), clothing=(11, 12), married=self.now - 1000),
            villager('m2', skills=(3, 3, 3), married=self.now - 1000),
            villager('m3', skills=(6, 6, 6)),
            villager('m4', skills=(7, 7, 7)),
            villager('m5', skills=(8, 8, 8)),
            villager('m6', skills=(9, 9, 9)),
            villager('b1', born=created + 86400),
            villager('w1', area=2, start=1),
            villager('w2', area=2, start=1),
            villager('o1'), villager('o2'), villager('o3'), villager('o4'),
        ]
        entities += [{'id': 'decor-' + str(index), 'templateType': 'decor_item',
                      'templateId': index, 'localCreated': True,
                      'position': {'x': 0, 'y': 0, 'areaId': 1}}
                     for index in range(1, 26)]
        self.seed({
            'areaId': 1, 'createdAt': created, 'revision': 1,
            'user': {'userLevelID': 10, 'userLevel': 10, 'maxAreaId': 2},
            'inventory': {'323': 100},
            'world': {'entities': entities},
            'npcMarriageRequests': [
                {'id': str(index), 'status': 'completed', 'completedAt': self.now - index}
                for index in range(1, 6)],
            'npcDateRequests': [{'id': 'date-1'}],
            'completedQuests': {f'quest-{index}': {} for index in range(1, 6)},
            'funReceipts': {f'fun-{index}': {} for index in range(1, 6)},
            'retiredVillagers': {
                'r1': villager('r1'), 'r2': villager('r2')},
            'workAreas': {
                'job-1': {'status': 'working', 'family': '4'},
                'job-2': {'status': 'working', 'family': '4'},
            },
        })

    def test_lists_derived_progress_and_levels(self):
        self.seed_full_village()
        records = self.records()
        self.assertNotIn(11, records)  # reserved definitions are not live
        expected = {
            1: (5, 1), 2: (1, 1), 3: (13, 1), 4: (5, 1), 5: (1, 1),
            13: (26, 1), 15: (2, 1), 16: (2, 1), 23: (5, 1), 24: (25, 1),
            26: (2, 1), 33: (10, 1), 35: (3, 3),
        }
        for ident, (progress, level) in expected.items():
            record = records[ident]
            self.assertEqual(record['UserGameAchievementId'], str(ident), record)
            self.assertEqual(record['ItemQuantity'], progress, record)
            self.assertEqual(record['LevelAchieved'], level, record)
            self.assertEqual(record['LevelRewardCollected'], 0, record)
            self.assertEqual(record['IsViewed'], 0, record)

    def test_new_tier_toast_is_not_repeated_without_acknowledgement(self):
        self.seed_full_village()
        first = self.records()
        self.assertEqual(first[1]['IsViewed'], 0)
        # The client acknowledges separately; if that is lost, the tier must not
        # keep popping on every menu open or area change.
        second = self.records()
        self.assertEqual(second[1]['IsViewed'], 1)
        self.assertEqual(second[1]['LevelAchieved'], 1)
        self.assertEqual(second[1]['LevelRewardCollected'], 0)

    def test_uncollected_rewards_view_and_collect(self):
        self.seed_full_village()
        records = self.records()
        pending = self.call(self.profile,
                            'ClientAchievement/GetUnReceievedUserGameAchievements')
        self.assertEqual(pending['code'], 200, pending)
        pending_ids = {record['GameAchievementId']
                       for record in pending['data']['result']}
        self.assertEqual(pending_ids, {ident for ident, record in records.items()
                                       if record['LevelAchieved'] > 0})

        viewed = self.call(self.profile, 'ClientAchievement/MarkAchievementAsViewed',
                           {'userGameAchievementId': '1'})
        self.assertEqual(viewed['code'], 200, viewed)
        self.assertEqual(self.records()[1]['IsViewed'], 1)

        collected = self.call(
            self.profile, 'ClientAchievement/CollectUserGameAchievementReward',
            {'userGameAchievementId': '1'})
        self.assertEqual(collected['code'], 200, collected)
        gems = next(item['amount'] for item in collected['data']['inventory']
                    if item['materialTypeId'] == 323)
        self.assertEqual(gems, 102)
        # The client reads the collected record and refreshed inventory from
        # the result envelope; this is what moves the HUD gem counter.
        envelope = collected['data']['result']
        self.assertEqual(envelope['UserGameAchievement']['GameAchievementId'], 1)
        self.assertEqual(envelope['UserGameAchievement']['LevelRewardCollected'], 1)
        self.assertEqual(envelope['Inventory'], collected['data']['inventory'])
        self.assertEqual(next(item['amount'] for item in envelope['Inventory']
                              if item['materialTypeId'] == 323), 102)
        record = self.records()[1]
        self.assertEqual(record['LevelRewardCollected'], 1)
        self.assertEqual(record['IsViewed'], 1)

        repeated = self.call(
            self.profile, 'ClientAchievement/CollectUserGameAchievementReward',
            {'userGameAchievementId': '1'})
        self.assertEqual(repeated['code'], 200, repeated)
        gems = next(item['amount'] for item in repeated['data']['inventory']
                    if item['materialTypeId'] == 323)
        self.assertEqual(gems, 102)
        self.assertEqual(repeated['data']['result']['Gems'], 0)
        self.assertEqual(repeated['data']['result']['Inventory'],
                         repeated['data']['inventory'])
        self.assertEqual(
            repeated['data']['result']['UserGameAchievement']['LevelRewardCollected'], 1)

        third = self.call(
            self.profile, 'ClientAchievement/CollectUserGameAchievementReward',
            {'userGameAchievementId': '35'})
        self.assertEqual(third['code'], 200, third)
        gems = next(item['amount'] for item in third['data']['inventory']
                    if item['materialTypeId'] == 323)
        self.assertEqual(gems, 111)

    def test_reward_state_is_persisted(self):
        self.seed_full_village()
        self.records()
        self.call(self.profile, 'ClientAchievement/CollectUserGameAchievementReward',
                  {'userGameAchievementId': '1'})
        state = self.state()
        self.assertEqual(state['achievements']['1'],
                         {'progress': 5, 'levelAchieved': 1,
                          'levelRewardCollected': 1, 'viewed': 1,
                          'servedLevel': 1})
        self.assertEqual(state['inventory']['323'], 102)
        self.assertIn('achievements', state['rules'])

    def test_progress_is_monotonic_when_population_drops(self):
        self.seed_full_village()
        self.records()

        def drop(payload):
            normal = payload['originalSave']['normal']
            normal['world']['entities'] = [
                entity for entity in normal['world']['entities']
                if entity.get('templateType') != 'villager_type'
                or entity['id'].startswith('m')]
            return {}

        self.repo.mutate(self.identity.village_id,
                         operation_key='fixture:drop-villagers', request={}, change=drop)
        record = self.records()[3]
        self.assertEqual(record['ItemQuantity'], 13)
        self.assertEqual(record['LevelAchieved'], 1)

    def test_villages_do_not_share_achievement_progress(self):
        self.seed_full_village()
        self.assertEqual(self.records()[3]['ItemQuantity'], 13)

        other = self.login('achievement-device-two')
        other_identity = self.game.sessions.authenticate(other)

        def seed_other(payload):
            payload['originalSave']['normal'] = {
                'areaId': 1, 'createdAt': self.now, 'revision': 1,
                'user': {'userLevelID': 1}, 'inventory': {'323': 0},
                'world': {'entities': []},
            }
            return {}

        self.repo.mutate(other_identity.village_id,
                         operation_key='fixture:other-village', request={},
                         change=seed_other)
        other_records = self.records(other)
        for ident in (1, 2, 3, 13, 24, 26, 35):
            self.assertEqual(other_records[ident]['ItemQuantity'], 0,
                             other_records[ident])
            self.assertEqual(other_records[ident]['LevelAchieved'], 0,
                             other_records[ident])
        self.assertEqual(other_records[33]['ItemQuantity'], 1)
        self.assertEqual(self.records()[3]['ItemQuantity'], 13)

    def test_unknown_and_inactive_achievements_are_rejected(self):
        self.seed_full_village()
        self.records()
        unknown = self.call(self.profile, 'ClientAchievement/MarkAchievementAsViewed',
                            {'userGameAchievementId': '999'})
        self.assertEqual(unknown['code'], 400, unknown)
        self.assertIn('Unknown achievement', unknown['message'])
        inactive = self.call(
            self.profile, 'ClientAchievement/CollectUserGameAchievementReward',
            {'userGameAchievementId': '11'})
        self.assertEqual(inactive['code'], 400, inactive)
        text = self.call(self.profile, 'ClientAchievement/MarkAchievementAsViewed',
                         {'userGameAchievementId': 'ach-1'})
        self.assertEqual(text['code'], 400, text)
        self.assertIn('not numeric', text['message'])
        missing = self.call(self.profile, 'ClientAchievement/MarkAchievementAsViewed',
                            {'userGameAchievementId': ''})
        self.assertEqual(missing['code'], 400, missing)
        self.assertIn('identifier required', missing['message'])

    def test_claims_use_the_identifier_the_client_was_given(self):
        self.seed_full_village()
        records = self.records()
        echoed = records[16]['UserGameAchievementId']
        self.assertIsInstance(echoed, str)
        collected = self.call(
            self.profile, 'ClientAchievement/CollectUserGameAchievementReward',
            {'userGameAchievementId': echoed})
        self.assertEqual(collected['code'], 200, collected)
        self.assertEqual(self.records()[16]['LevelRewardCollected'], 1)
        marked = self.call(self.profile, 'ClientAchievement/MarkAchievementAsViewed',
                           {'userGameAchievementId': records[15]['UserGameAchievementId']})
        self.assertEqual(marked['code'], 200, marked)
        self.assertEqual(self.records()[15]['IsViewed'], 1)

    def test_record_and_list_expose_every_identifier_alias(self):
        self.seed_full_village()
        result = self.call(self.profile,
                           'ClientAchievement/GetUserAchievements')
        self.assertEqual(result['code'], 200, result)
        aliases = ('Id', 'UserGameAchievementId', 'UserGameAchievementID',
                   'UserAchievementId', 'GameAchievementUserId',
                   'UserGameAchievementsId')
        for record in result['data']['result']:
            for alias in aliases:
                self.assertEqual(record[alias], str(record['GameAchievementId']),
                                 (alias, record))
        self.assertEqual(result['data']['userGameAchievements'],
                         result['data']['result'])
        self.assertEqual(result['data']['UserGameAchievements'],
                         result['data']['result'])

        pending = self.call(self.profile,
                            'ClientAchievement/GetUnReceievedUserGameAchievements')
        self.assertEqual(pending['code'], 200, pending)
        self.assertEqual(pending['data']['userGameAchievements'],
                         pending['data']['result'])
        for record in pending['data']['result']:
            for alias in aliases:
                self.assertEqual(record[alias], str(record['GameAchievementId']),
                                 (alias, record))

    def test_claim_accepts_an_alias_identifier(self):
        self.seed_full_village()
        self.records()
        for key, ident in (('Id', '16'), ('UserAchievementId', '15'),
                           ('GameAchievementUserId', '13')):
            claimed = self.call(
                self.profile, 'ClientAchievement/CollectUserGameAchievementReward',
                {key: ident})
            self.assertEqual(claimed['code'], 200, claimed)


if __name__ == '__main__':
    unittest.main()
