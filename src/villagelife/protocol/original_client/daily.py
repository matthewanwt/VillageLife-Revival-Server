"""Shared daily-life rules for saved original-client villagers."""
from __future__ import annotations

from functools import cached_property

from .world import OriginalWorldRules


def satisfy_wants(state: dict, villagers: set[str], category: int, at: int,
                  material: int | None = None) -> list[dict]:
    kept, satisfied = [], []
    for want in state.get('wants', []):
        ident = want.get('VillagerStringID')
        if (ident in villagers and want.get('wantableCategoryType') == category
                and (material is None or want.get('MaterialID') == material)):
            satisfied.append({'WantId': want['WantId'], 'VillagerStringID': ident})
            state.setdefault('needSatisfiedAt', {})[f'{ident}:{category}'] = at
        else:
            kept.append(want)
    if satisfied:
        state['wants'] = kept
    return satisfied


class DailyLife:
    def __init__(self, definitions):
        self.defs = definitions
        self.world = OriginalWorldRules(definitions)

    @cached_property
    def groups(self) -> dict[str, set[str]]:
        result = {}
        for row in self.defs.rows('villager_set_item'):
            result.setdefault(row['villagerSet'], set()).add(row['villagerType'])
        return result

    def in_group(self, person: dict, group: str, at: int) -> bool:
        kind = self.world.current_villager_type(person, at)
        return str(kind.get('id', person['templateId'])) in self.groups.get(group, ())

    def xp_cap(self, state: dict) -> int:
        level = next((row for row in self.defs.rows('user_level')
                      if int(row['levelNumber']) == int(state['user']['userLevelID'])), None)
        if level is None:
            raise ValueError('Unknown original user level')
        return int(level['villagerXPCapacity'])

    def project_energy(self, entities: list[dict], at: int) -> None:
        for person in entities:
            if person.get('templateType') == 'villager_type':
                self.recover_energy(person, at)

    @cached_property
    def energy_period(self) -> int:
        return next((int(row['value']) for row in self.defs.rows('global')
                     if row['label'] == 'energyReplenishDelaySec'), 0)

    def recover_energy(self, person: dict, at: int) -> None:
        if 'energyLevel' not in person:
            return
        kind = self.world.current_villager_type(person, at)
        if 'maxEnergy' not in kind:
            return
        maximum = int(kind['maxEnergy'])
        period = self.energy_period
        updated = int(person.get('energyTimeStamp', at))
        if period <= 0 or at < updated:
            return
        elapsed = (at - updated) // period
        person['energyLevel'] = min(maximum, int(person['energyLevel']) + elapsed)
        person['energyTimeStamp'] = (at if person['energyLevel'] == maximum
                                     else updated + elapsed * period)

    def spend_energy(self, person: dict, cost: int, at: int) -> None:
        if not cost:
            return
        self.recover_energy(person, at)
        if person.get('energyLevel', 0) < cost:
            raise ValueError('Villager needs more energy for this activity')
        person['energyLevel'] -= cost
        person['energyTimeStamp'] = at
