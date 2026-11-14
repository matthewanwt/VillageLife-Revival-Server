"""Original-client material unlock timers and paid completion."""
from __future__ import annotations

from functools import lru_cache
from .timers import gem_price

from .catalog import OriginalDefinitions
from .inventory import OriginalInventoryRules, spend_gems
from .world import OriginalWorldRules


START = 'ClientMaterialService/StartLearningMaterial'
COMPLETE = 'ClientMaterialService/CompleteLearningMaterial'
SKIP = 'ClientMaterialService/SkipLearningMaterial'
SERVICES = {START, COMPLETE, SKIP}


class OriginalLearningRules:
    def __init__(self, definitions: OriginalDefinitions, inventory: OriginalInventoryRules):
        self.defs = definitions
        self.inventory = inventory
        self.world = OriginalWorldRules(definitions)

    @lru_cache(maxsize=512)
    def _requirements(self, material: str) -> tuple[dict, ...]:
        # Native lookup matches the first authored task rewarding this material.
        reward_sets = {row['setId'] for row in self.defs.rows('reward_set_item')
                       if row['materialType'] == material}
        task = next((row for row in self.defs.rows('task') if row['id'] != '0'
                     and row['rewardSet'] in reward_sets), None)
        if task is None or task.get('levelRequirement', '0') == '0':
            return ()
        return tuple(row for row in self.defs.rows('requirement_set_item')
                     if row['requirementSet'] == task['levelRequirement'])

    def _skip_price(self, remaining: int) -> int:
        return gem_price(self.world, remaining)

    def _reply(self, state: dict, record: dict) -> dict:
        return {'result': {'UpdatedTime': record.get('startedAt', 0),
                           'Gem': state['inventory'].get('323', 0)},
                'inventory': self.inventory.list_items(state)}

    def apply(self, state: dict, service: str, data: dict, at: int) -> dict:
        ident = data.get('materialTypeId')
        if type(ident) is not int or ident <= 0:
            raise ValueError('Material identifier required')
        material = self.defs.item('material_type', ident)
        duration = int(material['learnDurationSec'])
        if duration <= 0:
            raise ValueError('Material does not require learning')
        key = str(ident)
        learning = state.get('materialLearning', {})
        record = learning.get(key)
        milestones = self.inventory.milestones(state)
        if self.inventory.is_unlocked(state, key, material, milestones):
            return self._reply(state, record or {})
        if service == START:
            if record:
                return self._reply(state, record)
            if int(material['unlockLevel']) > int(state['user']['userLevelID']):
                raise ValueError('Learning requires a higher village level')
            parent = int(material['parentID'])
            if parent > 0 and not self.inventory.is_unlocked(
                    state, str(parent), self.defs.item('material_type', parent), milestones):
                raise ValueError('Learn the parent material first')
            if int(material['area']) > state['areaId']:
                raise ValueError('Material belongs to an unavailable area')
            for requirement in self._requirements(key):
                amount = self.inventory.requirement_quantity(
                    state, requirement['materialType'], milestones)
                if amount < float(requirement['quantity']):
                    raise ValueError('Learning prerequisite is not met')
            seasonal = int(material['seasonal']) != 0
            limit = int(self.world.global_value('learningMaxSeasonal' if seasonal else 'learningMax'))
            active = sum(item['status'] == 'learning' and item['seasonal'] == seasonal
                         for item in learning.values())
            if active >= limit:
                raise ValueError('All learning slots in this category are occupied')
            # Starting learning is free in the native dialog.
            record = {'status': 'learning', 'startedAt': at, 'duration': duration,
                      'seasonal': seasonal, 'gemsSpent': 0}
            state.setdefault('materialLearning', {})[key] = record
        else:
            if record is None:
                raise ValueError('Start learning this material first')
            remaining = max(0, record['startedAt'] + record['duration'] - at)
            if service == COMPLETE and remaining:
                raise ValueError('Learning timer has not finished')
            cost = self._skip_price(remaining) if service == SKIP else 0
            spend_gems(state, cost)
            record.update(status='unlocked', completedAt=at, gemsSpent=cost)
        state['revision'] = int(state.get('revision', 0)) + 1
        return self._reply(state, record)
