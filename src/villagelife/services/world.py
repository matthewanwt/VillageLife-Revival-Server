"""World object identity invariants for NEW native saves, not rendering rules."""
from typing import Any
from villagelife.core.errors import InvalidAction, NotFound


class WorldService:
    def get_entity(self, world: dict[str, Any], entity_id: str) -> dict[str, Any]:
        try:
            return world['entities'][entity_id]
        except (KeyError, TypeError):
            raise NotFound('Unknown entity') from None

    def add_entity(self, world: dict[str, Any], entity_id: str,
                   entity: dict[str, Any]) -> None:
        if not entity_id or not isinstance(entity, dict):
            raise InvalidAction('Stable entity ID and object data required')
        entities = world.setdefault('entities', {})
        if entity_id in entities:
            raise InvalidAction('Entity already exists')
        entities[entity_id] = dict(entity)

    def move_entity(self, world: dict[str, Any], entity_id: str, position: dict[str, Any],
                    *, policy) -> None:
        """Movement permissions and projection are original game rules."""
        if not policy.may_move(world, entity_id, position):
            raise InvalidAction('Movement not permitted by original rules')
        self.get_entity(world, entity_id)['position'] = dict(position)
