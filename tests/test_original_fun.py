import unittest

from villagelife.protocol.original_client.fun import OriginalFunRules
from villagelife.protocol.original_client.randomness import new_state


class FakeDefinitions:
    def __init__(self):
        self.data = {
            'villager_type': [{'id': '1', 'genderType': '1', 'minAge': '1',
                               'maxAge': '100', 'name': 'Adult'}],
            'fun_activity': [{'id': '7', 'usedBy': '9', 'itemWear': '1',
                              'materialType': '51', 'rewardSet': '0',
                              'durationSecs': '0', 'xpReward': '5',
                              'energyDeductionLevel': '1', 'energyCost': '2',
                              'unbreakable': '0'}],
            'fun_building': [{'id': '3', 'funActivity': '7'}],
            'villager_set_item': [{'villagerSet': '9', 'villagerType': '1'}],
            'user_level': [{'id': '1', 'levelNumber': '1',
                            'villagerXPCapacity': '100'}],
            'reward_set_item': [],
            'global': [{'label': 'hours_per_year', 'value': '8760'}],
        }

    def rows(self, table):
        return self.data.get(table, [])

    def item(self, table, key):
        return next(row for row in self.rows(table)
                    if str(row['id']) == str(key))


class FakeInventory:
    def list_items(self, state):
        return []


class OriginalFunTests(unittest.TestCase):
    def setUp(self):
        self.rules = OriginalFunRules(FakeDefinitions(), FakeInventory())
        self.state = {
            'areaId': 1,
            'user': {'userLevelID': 1},
            'inventory': {},
            'world': {'entities': [
                {'id': 'villager-1', 'templateType': 'villager_type',
                 'templateId': 1, 'gender': 1, 'startAge': 21,
                 'bornAt': 100, 'xp': 2, 'energyLevel': 8,
                 'position': {'areaId': 1}},
                {'id': 'building-1', 'templateType': 'fun_building',
                 'templateId': 3, 'amount': 2,
                 'position': {'areaId': 1}},
            ]},
            'wants': [{'WantId': 'want-1', 'VillagerStringID': 'villager-1',
                       'MaterialID': 51, 'wantableCategoryType': 3}],
            'revision': 0,
        }

    def test_activity_spends_use_awards_xp_energy_and_satisfies_want_once(self):
        data = {'villagerId': 'villager-1', 'funActivityId': 7,
                'userFunBuildingTypeId': 'building-1'}
        result = self.rules.perform(self.state, data, 1_000, 'operation-1', new_state())

        actor, building = self.state['world']['entities']
        self.assertEqual(actor['xp'], 7)
        self.assertEqual(actor['energyLevel'], 6)
        self.assertEqual(building['amount'], 1)
        self.assertEqual(result['SatisfiedWantModels'],
                         [{'WantId': 'want-1', 'VillagerStringID': 'villager-1'}])
        self.assertEqual(self.state['wants'], [])
        self.assertEqual(self.state['revision'], 1)

        replay = self.rules.perform(self.state, data, 1_001, 'operation-1', new_state())
        self.assertEqual(replay, result)
        self.assertEqual(actor['xp'], 7)
        self.assertEqual(building['amount'], 1)
        self.assertEqual(self.state['revision'], 1)

    def test_fractional_reward_selects_one_positive_chance_result(self):
        activity = self.rules.defs.data['fun_activity'][0]
        activity['rewardSet'] = '1866'
        self.rules.defs.data['reward_set_item'] = [
            {'setId': '1866', 'materialType': '2173', 'quantity': '1', 'chance': '0.75'},
            {'setId': '1866', 'materialType': '2174', 'quantity': '1', 'chance': '0.25'},
            {'setId': '1866', 'materialType': '2175', 'quantity': '99', 'chance': '0'},
        ]
        data = {'villagerId': 'villager-1', 'funActivityId': 7,
                'userFunBuildingTypeId': 'building-1'}

        self.rules.perform(self.state, data, 1_000, 'operation-2', new_state())

        self.assertEqual(sum(self.state['inventory'].values()), 1)
        self.assertIn(next(iter(self.state['inventory'])), {'2173', '2174'})


if __name__ == '__main__':
    unittest.main()
