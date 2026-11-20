import hashlib
import unittest

from villagelife.protocol.original_client.habitats import OriginalHabitatRules


class FakeDefinitions:
    def rows(self, table):
        return []

    def item(self, table, ident):
        raise KeyError((table, ident))


def local_bed(shelter_id, index, occupant=''):
    digest = hashlib.sha256((shelter_id + ':' + str(index)).encode()).hexdigest()[:24]
    return {'id': 'local-bed-' + digest, 'shelterSlotID': 12 + index,
            'villagerId': occupant}


class OriginalHabitatTests(unittest.TestCase):
    def setUp(self):
        self.rules = OriginalHabitatRules(FakeDefinitions())

    def test_capacity_is_per_buildable_shelter_template(self):
        state = {'areaId': 1, 'world': {'entities': [
            {'id': 'home-0', 'templateType': 'shelter', 'templateId': 0,
             'localCreated': True, 'beds': []},
            {'id': 'home-1', 'templateType': 'shelter', 'templateId': 1,
             'localCreated': True, 'beds': []},
            {'id': 'home-2', 'templateType': 'shelter', 'templateId': 2,
             'localCreated': True, 'beds': []},
        ]}}

        self.rules.migrate(state, 100)

        homes = state['world']['entities']
        self.assertEqual([len(home['beds']) for home in homes], [2, 4, 6])
        self.assertEqual([[bed['shelterSlotID'] for bed in home['beds']]
                          for home in homes], [list(range(12, 14)),
                                               list(range(12, 16)),
                                               list(range(12, 18))])

    def test_authored_capacity_expands_saved_home_and_preserves_existing_beds(self):
        class Definitions(FakeDefinitions):
            def rows(self, table):
                return {
                    'building_type': [{'id':'1', 'entityRef':'shelter', 'entityID':'44'}],
                    'building_task': [{'buildingType':'1', 'taskId':'1'}],
                    'task': [{'id':'1', 'taskType':'2', 'benefitType':'2', 'benefitAmount':'4'}],
                }.get(table, [])

        existing = {'id':'preserved-bed', 'shelterSlotID':12, 'villagerId':'resident'}
        home = {'id':'authored-capacity-home', 'templateType':'shelter', 'templateId':44,
                'localCreated':True, 'beds':[existing], 'happinessCollectedAt':123}
        rules = OriginalHabitatRules(Definitions())
        self.assertTrue(rules.initialize(home))
        self.assertEqual(home['beds'][0], existing)
        self.assertEqual([bed['shelterSlotID'] for bed in home['beds']], [12, 13, 14, 15])
        self.assertEqual(home['happinessCollectedAt'], 123)
        self.assertFalse(rules.initialize(home))

    def test_authored_shelter_scenery_gets_no_fabricated_slots(self):
        occupied_actor = {'id': 'villager-1', 'templateType': 'villager_type',
                          'shelterBedId': '', 'position': {'areaId': 1}}
        scenery = {'id': 'scene-house', 'templateType': 'shelter',
                   'templateId': 42, 'serverPersisted': True,
                   'position': {'areaId': 1},
                   'beds': [local_bed('scene-house', 0),
                            local_bed('scene-house', 1)]}
        authored_home = {'id': 'scenario-home', 'templateType': 'shelter',
                         'templateId': 10, 'serverPersisted': True,
                         'position': {'areaId': 1},
                         'beds': [{'id': 'authored-bed-a', 'shelterSlotID': 31,
                                   'villagerId': ''}]}
        state = {'areaId': 1, 'world': {'entities': [occupied_actor, scenery,
                                                       authored_home]}}

        self.rules.migrate(state, 100)

        self.assertNotIn('beds', scenery)
        self.assertEqual(authored_home['beds'], [
            {'id': 'authored-bed-a', 'shelterSlotID': 31, 'villagerId': ''}])

    def test_unknown_buildable_capacity_is_not_guessed(self):
        home = {'id': 'home-unknown', 'templateType': 'shelter',
                'templateId': 13, 'localCreated': True,
                'beds': [local_bed('home-unknown', 0),
                         local_bed('home-unknown', 1)]}
        state = {'areaId': 1, 'world': {'entities': [home]}}

        self.rules.migrate(state, 100)

        self.assertEqual(home['beds'], [])

    def test_import_restores_special_woodland_bed_after_old_cleanup(self):
        occupied = local_bed('special', 1, 'resident')
        shelter = {'id': 'special', 'templateType': 'shelter', 'templateId': 34,
                   'position': {'areaId': 1}, 'beds': [occupied], 'happinessCollectedAt': 123}
        state = {'world': {'entities': [shelter]}}
        self.assertTrue(self.rules.migrate(state, 200, legacy_import=True))
        self.assertEqual(shelter['beds'][0], occupied)
        self.assertEqual(shelter['beds'][1], local_bed('special', 0))
        self.assertEqual(shelter['happinessCollectedAt'], 123)
        self.assertFalse(self.rules.migrate(state, 201, legacy_import=True))

    def test_imported_hero_bed_survives_timer_reset_and_assignment(self):
        person = {'id': 'worker', 'templateType': 'villager_type', 'position': {'areaId': 1}}
        shelter = {'id': 'hero', 'templateType': 'shelter', 'templateId': 34, 'position': {'areaId': 1}}
        state = {'areaId': 1, 'world': {'entities': [person, shelter]}}
        self.rules.migrate(state, 100, legacy_import=True)
        bed_id = shelter['beds'][0]['id']
        self.rules.operate(state, 'ClientUserShelterService/ResetHappinessTimer',
                           {'userShelterId': 'hero'}, 101, legacy_import=True)
        self.rules.operate(state, 'ClientUserShelterService/AssignBedToVillager',
                           {'villagerId': 'worker', 'shelterBedId': bed_id}, 102, legacy_import=True)
        self.assertEqual(person['shelterBedId'], bed_id)
        self.assertEqual(shelter['beds'][0]['villagerId'], 'worker')
        self.assertEqual(len(shelter['beds']), 2)

    def test_synthetic_cleanup_never_discards_an_existing_occupant(self):
        actor = {'id': 'villager-1', 'templateType': 'villager_type',
                 'shelterBedId': 'occupied-bed', 'position': {'areaId': 1}}
        scenery = {'id': 'scene-house', 'templateType': 'shelter',
                   'templateId': 42, 'serverPersisted': True,
                   'position': {'areaId': 1},
                   'beds': [local_bed('scene-house', 0, 'villager-1'),
                            local_bed('scene-house', 1)]}
        state = {'areaId': 1, 'world': {'entities': [actor, scenery]}}

        self.rules.migrate(state, 100)

        self.assertEqual(len(scenery['beds']), 1)
        self.assertEqual(scenery['beds'][0]['villagerId'], 'villager-1')

    def test_assign_and_empty_keep_bed_and_villager_links_consistent(self):
        actor = {'id': 'villager-1', 'templateType': 'villager_type',
                 'shelterBedId': '', 'position': {'areaId': 1}}
        shelter = {'id': 'home-1', 'templateType': 'shelter',
                   'templateId': 1, 'localCreated': True, 'beds': [],
                   'position': {'areaId': 1}}
        state = {'areaId': 1, 'world': {'entities': [actor, shelter]},
                 'revision': 0}
        self.rules.migrate(state, 100)
        bed_id = shelter['beds'][2]['id']

        assigned, _ = self.rules.operate(
            state, 'ClientUserShelterService/AssignBedToVillager',
            {'villagerId': 'villager-1', 'shelterBedId': bed_id}, 101, 'assign-1')
        self.assertEqual(assigned, {})
        self.assertEqual(actor['shelterBedId'], bed_id)
        self.assertEqual(shelter['beds'][2]['villagerId'], 'villager-1')

        emptied, _ = self.rules.operate(
            state, 'ClientUserShelterService/EmptyBed',
            {'shelterBedId': bed_id}, 102, 'empty-1')
        self.assertEqual(emptied, {})
        self.assertEqual(actor['shelterBedId'], '')
        self.assertEqual(shelter['beds'][2]['villagerId'], '')


if __name__ == '__main__':
    unittest.main()
