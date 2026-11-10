"""Original material inventory wire projection and unlock milestones."""
from __future__ import annotations

from .catalog import OriginalDefinitions


class OriginalInventoryRules:
    def __init__(self, definitions: OriginalDefinitions):
        self.defs = definitions
        self._ancestors: dict[tuple[str, int], frozenset[str]] | None = None

    def _building_ancestors(self) -> dict[tuple[str, int], frozenset[str]]:
        if self._ancestors is not None:
            return self._ancestors
        foundations = {row['id']: row for row in self.defs.rows('building_task')}
        result: dict[tuple[str, int], set[str]] = {}
        for foundation in foundations.values():
            current = foundation
            seen = set()
            while current['id'] not in seen:
                seen.add(current['id'])
                building = self.defs.item('building_type', current['buildingType'])
                key = (building['entityRef'], int(building['entityID']))
                result.setdefault(key, set()).add(str(building['materialType']))
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
            if entity.get('localCreated') or entity.get('sourceWorkAreaId'):
                found.update(ancestors.get((entity.get('templateType'), entity.get('templateId')), ()))
        maximum = int(state.get('user', {}).get('maxAreaId', state.get('areaId', 0)))
        found.update(material for material, area in (('231', 1), ('232', 2), ('1536', 3))
                     if maximum >= area)
        return found

    def list_items(self, state: dict) -> list[dict]:
        inventory = state.get('inventory', {})
        learning = state.get('materialLearning', {})
        milestones = self.milestones(state)
        keys = set(inventory) | set(learning) | milestones
        result = []
        for raw in sorted(keys, key=int):
            ident = int(raw)
            definition = self.defs.item('material_type', ident)
            record = learning.get(str(raw))
            is_unlocked = (record['status'] == 'unlocked' if record else
                           str(raw) in inventory or str(raw) in milestones or
                           int(definition.get('learnDurationSec', '0')) == 0)
            result.append({'materialTypeId': ident,
                           'amount': max(inventory.get(str(raw), 0), int(str(raw) in milestones)),
                           'isUnlocked': bool(is_unlocked),
                           'learningStartedAt': record.get('startedAt', 0) if record else 0})
        return result
