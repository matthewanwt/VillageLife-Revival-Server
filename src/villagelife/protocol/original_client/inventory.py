"""Original material inventory wire projection and unlock milestones."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from functools import cached_property
import json

from .catalog import OriginalDefinitions


class InsufficientGems(ValueError):
    def __init__(self, cost, balance):
        self.cost = cost
        self.balance = balance
        self.shortfall = cost - balance
        super().__init__(
            f'This action costs {cost:g} gems. You have {balance:g} and need {self.shortfall:g} more.')

    def reply(self):
        return {'error': 'INSUFFICIENT_GEMS', 'gemsRequired': self.cost,
                'gemsAvailable': self.balance, 'gemsShortfall': self.shortfall}


def spend_gems(state, cost):
    if (isinstance(cost, bool) or not isinstance(cost, (int, Decimal))
            or not Decimal(cost).is_finite() or cost < 0):
        raise ValueError("Invalid gem cost")
    if not cost:
        return
    try:
        balance = Decimal(str(state['inventory'].get('323', 0)))
    except InvalidOperation as exc:
        raise ValueError('Invalid gem balance') from exc
    if not balance.is_finite() or balance < 0:
        raise ValueError('Invalid gem balance')
    if balance < cost:
        raise InsufficientGems(cost, float(balance))
    remaining = balance - cost
    state['inventory']['323'] = int(remaining) if remaining == remaining.to_integral_value() else float(remaining)


class OriginalInventoryRules:
    def __init__(self, definitions: OriginalDefinitions):
        self.defs = definitions
        self._ancestors: dict[tuple[str, int], frozenset[str]] | None = None

    @cached_property
    def starter_tools(self) -> dict[str, float]:
        seed = next((json.loads(row['dataJSON'])['inventory']
                     for row in self.defs.rows('seq_state_tablet_ftue')
                     if row.get('sequenceType') == '64'
                     and 'inventory' in json.loads(row['dataJSON'])), {})
        recipes = {row['rewardSet'] for row in self.defs.rows('task') if row['taskType'] == '1'}
        craftable = {row['materialType'] for row in self.defs.rows('reward_set_item')
                     if row['setId'] in recipes and float(row['quantity']) > 0 and float(row['chance']) > 0}
        return {key: float(amount) for key, amount in seed.items()
                if float(amount) > 0 and key not in craftable
                and self.defs.item('material_type', key)['categoryId'] == '12'}

    def restore_starter_tools(self, state: dict) -> None:
        tools = self.starter_tools
        if not tools:
            return
        inventory = state.setdefault('inventory', {})
        for key, amount in tools.items():
            if inventory.get(key, 0) < amount:
                inventory[key] = amount
        # The later areas require the mastery marker, not the ordinary tool.
        # Only restore markers whose base tool is already a free, uncraftable
        # starter. Craftable tools must still earn their mastery normally.
        for key in self.starter_masteries:
            if inventory.get(key, 0) < 1:
                inventory[key] = 1

    @cached_property
    def starter_masteries(self) -> frozenset[str]:
        return frozenset(str(row['materialRequirement'])
                         for row in self.defs.rows('material_mastery')
                         if str(row.get('materialType')) in self.starter_tools)

    def _building_ancestors(self) -> dict[tuple[str, int], frozenset[str]]:
        if self._ancestors is not None:
            return self._ancestors
        foundations = {row['id']: row for row in self.defs.rows('building_task')}
        result: dict[tuple[str, int], set[str]] = {}
        for foundation in foundations.values():
            current = foundation
            building = self.defs.item('building_type', foundation['buildingType'])
            key = (building['entityRef'], int(building['entityID']))
            materials = result.setdefault(key, set())
            seen = set()
            while current['id'] not in seen:
                seen.add(current['id'])
                building = self.defs.item('building_type', current['buildingType'])
                materials.add(str(building['materialType']))
                parent = current.get('parentId', '-1')
                if parent == '-1' or parent not in foundations:
                    break
                current = foundations[parent]
        self._ancestors = {key: frozenset(value) for key, value in result.items()}
        return self._ancestors

    def milestones(self, state: dict) -> set[str]:
        found: set[str] = set()
        ancestors = self._building_ancestors()
        for entity in state.get('world', {}).get('entities', []):
            if (entity.get('templateType') == 'container_type'
                    and entity.get('position', {}).get('areaId') != state.get('areaId')):
                continue
            if entity.get('localCreated') or entity.get('sourceWorkAreaId'):
                found.update(ancestors.get((entity.get('templateType'), entity.get('templateId')), ()))
        maximum = int(state.get('user', {}).get('maxAreaId', state.get('areaId', 0)))
        found.update(material for material, area in (('231', 1), ('232', 2), ('1536', 3))
                     if maximum >= area)
        if state.get('transitionKey') == 'bridge-1-to-2':
            found.add('130')
        return found

    @cached_property
    def storage_materials(self) -> frozenset[str]:
        return frozenset(str(row['materialType']) for row in self.defs.rows('building_type')
                         if row.get('entityRef') == 'container_type')

    def storage_quantities(self, state: dict) -> dict[str, int]:
        quantities = {material: 0 for material in self.storage_materials}
        ancestors = self._building_ancestors()
        for entity in state.get('world', {}).get('entities', []):
            if (entity.get('templateType') != 'container_type'
                    or entity.get('position', {}).get('areaId') != state.get('areaId')):
                continue
            for material in ancestors.get(('container_type', entity.get('templateId')), ()):
                quantities[material] = quantities.get(material, 0) + 1
        return quantities

    def requirement_quantity(self, state: dict, material: str, milestones: set[str]) -> Decimal:
        if material == '7':
            return Decimal(str(state.get('user', {}).get('xp', 0)))
        if material in self.storage_materials:
            return Decimal(self.storage_quantities(state).get(material, 0))
        return max(Decimal(str(state.get('inventory', {}).get(material, 0))),
                   Decimal(int(material in milestones)))

    @staticmethod
    def is_unlocked(state: dict, key: str, definition: dict, milestones: set[str]) -> bool:
        if key in milestones:
            return True
        record = state.get('materialLearning', {}).get(key)
        if record is not None:
            return record['status'] == 'unlocked'
        return key in state.get('inventory', {}) or int(definition.get('learnDurationSec', '0')) == 0

    def list_items(self, state: dict) -> list[dict]:
        inventory = state.get('inventory', {})
        learning = state.get('materialLearning', {})
        milestones = self.milestones(state)
        storage = self.storage_quantities(state)
        # Explicit zeros clear the previous area's storage markers in the client.
        keys = set(inventory) | set(learning) | milestones | set(storage)
        result = []
        for raw in sorted(keys, key=int):
            ident = int(raw)
            definition = self.defs.item('material_type', ident)
            record = learning.get(str(raw))
            is_unlocked = self.is_unlocked(state, raw, definition, milestones)
            result.append({'materialTypeId': ident,
                           'amount': (storage[str(raw)] if str(raw) in storage else
                                      max(inventory.get(str(raw), 0), int(str(raw) in milestones))),
                           'isUnlocked': bool(is_unlocked),
                           'learningStartedAt': record.get('startedAt', 0) if record else 0})
        return result
