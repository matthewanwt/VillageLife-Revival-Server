"""Synthetic fixtures for native gathering preview/server deadline parity."""
from copy import deepcopy
import unittest

from villagelife.protocol.original_client.work import OriginalWorkRules


class Definitions:
    def __init__(self, reduction='0.25'):
        self.reduction = reduction

    def item(self, table, ident):
        return {
            ('villager_skill', 6): {'professionMultiplier': self.reduction},
            ('task', 31): {'taskType': '3', 'workAreaType': '2', 'skillId': '6',
                          'rewardSet': '2', 'requirementSet': '0', 'duration': '120'},
            ('villager_type', 1): {'canWork': '1'},
            ('material_source', 1): {'task': '31'},
            ('material_type', 5): {'id': '5'},
        }[table, ident]

    def rows(self, table):
        if table == 'reward_set_item':
            return [{'setId': '2', 'chance': '1', 'quantity': '1', 'materialType': '5'}]
        return []


class GatheringDurationTests(unittest.TestCase):
    def test_matching_ranks_origins_and_skill_spellings(self):
        work = OriginalWorkRules(Definitions())
        task = {'taskType': '3', 'duration': '120', 'skillId': '6'}
        for spelling in ('skilltypeId', 'skillTypeId', 'type'):
            for origin in (0, 1, 2):
                for count, expected in enumerate((120, 90, 60, 30, 30)):
                    actor = {'skills': [{spelling: 6, 'skillOriginType': origin}] * count}
                    before = deepcopy(actor)
                    with self.subTest(spelling=spelling, origin=origin, count=count):
                        self.assertEqual(work._duration(task, actor), expected)
                        self.assertEqual(actor, before)

    def test_iterative_float32_rounding_before_truncation(self):
        work = OriginalWorkRules(Definitions('0.1'))
        task = {'taskType': '3', 'duration': '100', 'skillId': '6'}
        # Native repeated float subtraction yields 0.699999928..., not 0.7.
        self.assertEqual(work._duration(task, {'skills': [{'type': 6}] * 3}), 69)
        task['taskType'] = '1'
        self.assertEqual(work._duration(task, {'skills': [{'type': 6}] * 3}), 70)

    def test_only_first_18_slots_count_for_gathering(self):
        work = OriginalWorkRules(Definitions())
        actor = {'skills': [{'type': 7}] * 18 + [{'type': 6}]}
        task = {'taskType': '3', 'duration': '120', 'skillId': '6'}
        self.assertEqual(work._duration(task, actor), 120)
        task['taskType'] = '1'
        self.assertEqual(work._duration(task, actor), 90)

    def test_zero_nonmatching_and_integer_truncation(self):
        work = OriginalWorkRules(Definitions())
        task = {'taskType': '3', 'duration': '123', 'skillId': '6'}
        self.assertEqual([work._duration(task, {'skills': [{'type': 6}] * n})
                          for n in range(4)], [123, 92, 61, 30])
        self.assertEqual(work._duration(task, {'skills': [{'type': 7}]}), 123)
        task['skillId'] = '0'
        self.assertEqual(work._duration(task, {'skills': [{'type': 0}]}), 123)

    def test_start_response_saved_deadline_old_jobs_and_early_harvest(self):
        work = OriginalWorkRules(Definitions())
        old_job = {'id': 'old', 'status': 'working', 'villagerId': 'other',
                   'sourceId': 'other-source', 'completionTime': 9999}
        state = {'areaId': 1, 'world': {'entities': [
            {'id': 'actor', 'templateType': 'villager_type', 'templateId': 1,
             'position': {'areaId': 1}, 'skills': [{'type': 6}]},
            {'id': 'source', 'templateType': 'material_source', 'templateId': 1,
             'position': {'areaId': 1, 'x': 10, 'y': 20}},
        ]}, 'inventory': {}, 'workAreas': {'old': deepcopy(old_job)}}
        request = {'areaId': 1, 'taskTypeId': 31, 'villagerId': 'actor',
                   'userMaterialSourceId': 'source', 'x': 10, 'y': 20}
        result = work.start(state, 'ClientTaskService/StartGatheringTask', request, 100)
        self.assertEqual(result['completionTime'], 190)
        saved = state['workAreas'][result['workAreaId']]
        self.assertEqual(saved['completionTime'], 190)
        self.assertEqual(saved['startResponse']['completionTime'], 190)
        self.assertEqual(state['workAreas']['old'], old_job)
        self.assertEqual(state['inventory'], {})
        before = deepcopy(state)
        with self.assertRaises(ValueError):
            work.harvest(state, {'workAreaId': result['workAreaId'], 'taskTypeId': 31}, 189)
        self.assertEqual(state, before)


if __name__ == '__main__':
    unittest.main()
