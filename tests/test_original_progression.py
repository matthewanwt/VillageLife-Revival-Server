"""Synthetic authored-step fixtures; no original game tables or player saves."""
from copy import deepcopy
import json
import unittest

from villagelife.protocol.original_client.progression import OriginalProgressionRules


class Definitions:
    def __init__(self, assignments=False):
        self.steps = [{'id': 'checkpoint', 'order': '1', 'sequenceType': '62',
                       'persist': '410', 'dataJSON': '{}'}]
        if assignments:
            self.steps += [
                {'id': 'stock', 'order': '3', 'sequenceType': '64', 'persist': '500',
                 'dataJSON': json.dumps({'inventory': {'130': 20, '323': 1000}})},
                {'id': 'xp', 'order': '4', 'sequenceType': '114', 'persist': '500',
                 'dataJSON': json.dumps({'xp': 7})},
            ]

    def rows(self, table):
        assert table == 'seq_state_tablet_ftue'
        return self.steps


def saved(checkpoint='410', complete=False):
    return {'gameSettings': {'activeSequenceId': checkpoint, 'isFtueComplete': complete},
            'normal': {'revision': 8, 'inventory': {'130': 3, '323': 41, 'other': 9},
                       'user': {'userLevelID': 1, 'xp': 0},
                       'unknown': {'preserve': [1, 'fixture']}}}


class ProgressionAssignmentTests(unittest.TestCase):
    def test_no_pending_steps_do_not_create_or_complete_metadata(self):
        rules = OriginalProgressionRules(Definitions())
        for effects in (None, {}, {'inventoryAssignments': []},
                        {'shrineXp': [], 'unknown': {'keep': True}}):
            with self.subTest(effects=effects):
                save = saved()
                if effects is not None:
                    save['normal']['scriptEffects'] = deepcopy(effects)
                before = deepcopy(save)
                self.assertFalse(rules.sync_script_assignments(save))
                self.assertEqual(save, before)

    def test_completed_assignments_do_not_add_an_unused_list(self):
        rules = OriginalProgressionRules(Definitions(assignments=True))
        # This catalog variant has only an inventory assignment at the checkpoint.
        rules.defs.steps.pop()
        save = saved('500')
        save['normal']['scriptEffects'] = {'inventoryAssignments': ['stock'],
                                          'unknown': 'retained'}
        before = deepcopy(save)
        self.assertFalse(rules.sync_script_assignments(save))
        self.assertEqual(save, before)

    def test_missing_world_or_unknown_checkpoint_remains_unchanged(self):
        rules = OriginalProgressionRules(Definitions(assignments=True))
        for save in ({}, {'normal': None}, saved('unknown')):
            before = deepcopy(save)
            self.assertFalse(rules.sync_script_assignments(save))
            self.assertEqual(save, before)

    def test_pending_assignments_keep_original_inventory_xp_and_replay_rules(self):
        rules = OriginalProgressionRules(Definitions(assignments=True))
        for existing in (False, True):
            with self.subTest(existing_metadata=existing):
                save = saved('500')
                save['normal']['startingGemsGranted'] = 41
                if existing:
                    save['normal']['scriptEffects'] = {'unknown': {'retain': True}}
                self.assertTrue(rules.sync_script_assignments(save))
                state = save['normal']
                self.assertEqual(state['inventory'], {'130': 20, '323': 41, 'other': 9})
                self.assertEqual(state['user'], {'userLevelID': 1, 'xp': 7})
                self.assertEqual(state['revision'], 9)
                self.assertEqual(state['scriptEffects']['inventoryAssignments'], ['stock'])
                self.assertEqual(state['scriptEffects']['shrineXp'], ['xp'])
                if existing:
                    self.assertEqual(state['scriptEffects']['unknown'], {'retain': True})
                before = deepcopy(save)
                self.assertFalse(rules.sync_script_assignments(save))
                self.assertEqual(save, before)

    def test_completed_ftue_retires_assignments_without_resetting_earned_progress(self):
        rules = OriginalProgressionRules(Definitions(assignments=True))
        save = saved('-1', complete=True)
        save['normal']['user'] = {'userLevelID': 3, 'xp': 99}
        inventory = deepcopy(save['normal']['inventory'])
        self.assertTrue(rules.sync_script_assignments(save))
        self.assertEqual(save['normal']['inventory'], inventory)
        self.assertEqual(save['normal']['user'], {'userLevelID': 3, 'xp': 99})
        self.assertEqual(save['normal']['scriptEffects'],
                         {'inventoryAssignments': ['stock'], 'shrineXp': ['xp']})
        before = deepcopy(save)
        self.assertFalse(rules.sync_script_assignments(save))
        self.assertEqual(save, before)


if __name__ == '__main__':
    unittest.main()
