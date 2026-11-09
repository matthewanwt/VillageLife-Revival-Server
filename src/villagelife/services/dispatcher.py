"""Application command bus: one use-case boundary regardless of client platform."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from villagelife.core.errors import InvalidAction, NotImplementedRule
from villagelife.core.validation import require_native
from villagelife.core.rules import NoVerifiedRules
from .areas import AreaService, UnverifiedAreaRules
from .buildings import BuildingService, UnverifiedBuildingRules
from .families import FamilyService, UnverifiedFamilyRules
from .jobs import JobService


@dataclass
class ActionDispatcher:
    store: Any
    area: AreaService
    building: BuildingService
    family: FamilyService
    jobs: JobService

    @classmethod
    def safe_default(cls, store):
        return cls(store, AreaService(UnverifiedAreaRules()),
                   BuildingService(UnverifiedBuildingRules()),
                   FamilyService(UnverifiedFamilyRules()), JobService(NoVerifiedRules()))

    def execute(self, village_id: str, *, name: str, payload: dict[str, Any],
                operation_key: str, expected_revision: int | None = None):
        if not isinstance(payload, dict):
            raise InvalidAction('Action payload must be an object')
        current = self.store.read_village(village_id)
        require_native(current)
        if name not in {'area.change', 'area.unlock', 'building.construct',
                        'building.work.start', 'building.work.collect',
                        'family.relationship', 'family.lifecycle', 'jobs.collect'}:
            raise NotImplementedRule(f'Client action not yet supported: {name}')

        def change(world: dict[str, Any]) -> dict[str, Any]:
            if name == 'area.change':
                return self.area.change_area(world, payload.get('areaId'))
            if name == 'area.unlock':
                return self.area.unlock(world, payload.get('areaId'))
            if name.startswith('building.'):
                return self.building.execute(world, name.partition('.')[2], payload)
            if name == 'family.relationship':
                return self.family.relationship(world, payload)
            if name == 'family.lifecycle':
                return self.family.lifecycle(world, payload)
            if name == 'jobs.collect':
                return self.jobs.collect(world, payload.get('jobId', ''))
            raise NotImplementedRule(name)

        return self.store.mutate(village_id, operation_key=operation_key, request={'action': name, 'payload': payload},
                                 change=change, expected_revision=expected_revision)
