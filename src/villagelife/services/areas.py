"""Area transitions are policy-driven, not hardcoded to the three known areas."""
from typing import Any, Protocol
from villagelife.core.errors import InvalidAction, NotImplementedRule


class AreaRules(Protocol):
    def can_unlock(self, world: dict[str, Any], area_id: int) -> bool: ...
    def initialize(self, world: dict[str, Any], area_id: int) -> None: ...


class UnverifiedAreaRules:
    def can_unlock(self, world, area_id):
        raise NotImplementedRule('Original area level/unlock rules not mapped yet')
    def initialize(self, world, area_id):
        raise NotImplementedRule('Original Riverside/Mountain scenario not fully verified')


class AreaService:
    def __init__(self, rules: AreaRules):
        self.rules = rules

    def change_area(self, world: dict[str, Any], area_id: int) -> dict[str, Any]:
        if not isinstance(area_id, int) or isinstance(area_id, bool) or area_id <= 0:
            raise InvalidAction('Valid numeric area ID required')
        if area_id not in world.get('unlockedAreas', []):
            raise InvalidAction('Area is locked')
        if area_id != world.get('currentAreaId'):
            self.rules.initialize(world, area_id)
            world['currentAreaId'] = area_id
        return {'currentAreaId': world['currentAreaId']}

    def unlock(self, world: dict[str, Any], area_id: int) -> dict[str, Any]:
        if area_id in world.get('unlockedAreas', []):
            return {'unlockedAreas': list(world['unlockedAreas'])}
        if not self.rules.can_unlock(world, area_id):
            raise InvalidAction('Area unlock requirements not satisfied')
        self.rules.initialize(world, area_id)
        world.setdefault('unlockedAreas', []).append(area_id)
        return {'unlockedAreas': list(world['unlockedAreas'])}
