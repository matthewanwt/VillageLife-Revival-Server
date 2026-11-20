"""Original-client fire, shelter, bed, and happiness rules.

Scenario-authored shelter scenery is not a player home. Only homes created by
construction receive generated beds; authored bed arrays remain authoritative.
"""
from __future__ import annotations
from villagelife.persistence.history import active_work
from .indexes import find_entity

import copy
import hashlib
import json
from functools import cached_property
from decimal import Decimal

from .catalog import OriginalDefinitions
from .daily import satisfy_wants
from .inventory import OriginalInventoryRules
from .world import OriginalWorldRules
from .shelter_removal import SERVICE as REMOVE_SHELTER, remove_shelter


SHELTER_INTERVAL = 86400
SHELTER_CAPACITIES = {0: 2, 1: 4, 2: 6, 3: 2, 4: 4, 5: 6, 6: 2, 7: 2}
# 0.2.6 gave these preplaced Woodland shelters two assignable beds.
LEGACY_WOODLAND_SHELTERS = frozenset(range(34, 42))
SERVICES = {
    'ClientUserFireService/StartFire', 'ClientUserFireService/OilFire',
    'ClientUserShelterService/AssignBedToVillager',
    'ClientUserShelterService/EmptyBed', REMOVE_SHELTER,
    'ClientUserShelterService/CollectShelterHappiness',
    'ClientUserShelterService/ResetHappinessTimer',
}


class OriginalHabitatRules:
    def __init__(self, definitions: OriginalDefinitions,
                 inventory: OriginalInventoryRules | None = None):
        self.defs = definitions
        self.inventory_rules = inventory or OriginalInventoryRules(definitions)
        self.world = OriginalWorldRules(definitions)

    def _item(self, table: str, ident) -> dict:
        try:
            return self.defs.item(table, ident)
        except KeyError as exc:
            raise ValueError(f'Unknown {table} identifier') from exc

    @cached_property
    def capacities(self) -> dict[int, int]:
        buildings = {row['id']: row for row in self.defs.rows('building_type')
                     if row['entityRef'] == 'shelter'}
        tasks = {row['id']: row for row in self.defs.rows('task')}
        counts: dict[int, set[int]] = {}
        for foundation in self.defs.rows('building_task'):
            building = buildings.get(foundation['buildingType'])
            if building is None:
                continue
            task = tasks.get(foundation['taskId'], {})
            if task.get('taskType') in {'2', '6'} and task.get('benefitType') == '2':
                capacity = int(task['benefitAmount'])
                if capacity > 0:
                    counts.setdefault(int(building['entityID']), set()).add(capacity)
        return {**SHELTER_CAPACITIES,
                **{ident: next(iter(values)) for ident, values in counts.items() if len(values) == 1}}

    @staticmethod
    def _generated_bed_id(entity_id: str, index: int) -> str:
        return 'local-bed-' + hashlib.sha256(
            (str(entity_id) + ':' + str(index)).encode()).hexdigest()[:24]

    def initialize(self, entity: dict, *, legacy_import: bool = False) -> bool:
        changed = False
        legacy_capacity = None
        if entity.get('templateType') == 'fire_type':
            defaults = {'isBurning': 0, 'startsAt': 0, 'endsAt': 0, 'oilAppliedAt': 0}
        elif entity.get('templateType') == 'shelter':
            if (legacy_import and self.world._area(entity) == 1
                    and int(entity.get('templateId', -1)) in LEGACY_WOODLAND_SHELTERS):
                legacy_capacity = 2
            is_home = bool(entity.get('localCreated') or entity.get('sourceWorkAreaId') or legacy_capacity)
            if not is_home:
                # Earlier builds incorrectly gave every authored shelter prop
                # two local beds. Remove only our identifiable, empty synthetic
                # rows; never discard a real bed or occupant.
                beds = entity.get('beds', [])
                kept = []
                removed = False
                for index, bed in enumerate(beds):
                    generated_id = self._generated_bed_id(entity['id'], index)
                    if bed.get('id') == generated_id and not bed.get('villagerId'):
                        changed = True
                        removed = True
                    else:
                        kept.append(bed)
                if removed:
                    if kept:
                        entity['beds'] = kept
                    else:
                        entity.pop('beds', None)
                if kept:
                    if 'happinessCollectedAt' not in entity:
                        entity['happinessCollectedAt'] = 0
                        changed = True
                elif not any(bed.get('villagerId') for bed in kept):
                    if entity.pop('happinessCollectedAt', None) is not None:
                        changed = True
                return changed
            defaults = {'happinessCollectedAt': 0, 'beds': []}
        else:
            return False
        for key, value in defaults.items():
            if key not in entity:
                entity[key] = value
                changed = True
        if entity['templateType'] == 'shelter':
            beds = entity['beds']
            capacity = legacy_capacity or self.capacities.get(int(entity.get('templateId', -1)))
            kept = [bed for index, bed in enumerate(beds)
                    if (bed.get('id') != self._generated_bed_id(entity['id'], index)
                        or bed.get('villagerId')
                        or (capacity is not None and index < capacity))]
            if len(kept) != len(beds):
                entity['beds'] = beds = kept
                changed = True
            used_slots = {bed.get('shelterSlotID') for bed in beds}
            used_ids = {bed.get('id') for bed in beds}
            slot = 12
            index = 0
            while capacity is not None and len(beds) < capacity:
                while slot in used_slots:
                    slot += 1
                while self._generated_bed_id(entity['id'], index) in used_ids:
                    index += 1
                bed_id = self._generated_bed_id(entity['id'], index)
                beds.append({'id': bed_id, 'shelterSlotID': slot, 'villagerId': ''})
                used_slots.add(slot)
                used_ids.add(bed_id)
                changed = True
        return changed

    def migrate(self, state: dict, at: int, *, legacy_import: bool = False) -> bool:
        changed = False
        for entity in state.get('world', {}).get('entities', []):
            changed = self.initialize(entity, legacy_import=legacy_import) or changed
        if changed:
            state.setdefault('rules', {})['habitats'] = {
                'evidence': 'original fire_task, shelter, fire_type and task tables; native bed/fire calls',
                'bed_layout': 'authored bed arrays or explicitly known buildable capacities; scenario scenery excluded',
                'status': 'unknown shelter templates do not receive guessed bed slots'}
        return changed

    def entity(self, state: dict, ident, kind: str) -> dict:
        if not isinstance(ident, str) or not ident:
            raise ValueError('Object identifier required')
        found = find_entity(state, ident, kind)
        if found is None:
            raise ValueError('Unknown ' + kind + ' in this village')
        if self.world._area(found) != state['areaId']:
            raise ValueError('Object is in another area')
        return found

    def inventory(self, state: dict) -> list[dict]:
        return self.inventory_rules.list_items(state)

    def _fire_response(self, state: dict, fire: dict) -> dict:
        keys = ('id', 'isBurning', 'startsAt', 'endsAt', 'oilAppliedAt')
        return {'userFire': {key: copy.deepcopy(fire[key]) for key in keys},
                'userMaterialTypes': self.inventory(state), 'SatisfiedWantModels': []}

    def sync(self, state: dict, at: int) -> bool:
        changed = False
        for fire in state['world']['entities']:
            if (fire.get('templateType') != 'fire_type' or not fire.get('isBurning')
                    or at < fire.get('endsAt', 0)):
                continue
            fire['isBurning'] = 0
            for key, amount in fire.pop('activeReward', {}).items():
                state['inventory'][key] = max(0, state['inventory'].get(key, 0) - amount)
            changed = True
        return changed

    def _spend(self, state: dict, requirements: list[dict]) -> None:
        deductions: dict[str, Decimal] = {}
        for requirement in requirements:
            if requirement.get('villagers', 'undefined') not in {'undefined', '0', ''}:
                raise NotImplementedError('Additional fire villager requirements are not recovered')
            key = str(requirement['materialType'])
            available = Decimal(str(state['inventory'].get(key, 0)))
            if available < Decimal(requirement['quantity']):
                raise ValueError('Missing fire material: ' + key)
            deductions[key] = deductions.get(key, Decimal(0)) + Decimal(requirement['quantityUsed'])
        for key, amount in deductions.items():
            if Decimal(str(state['inventory'].get(key, 0))) < amount:
                raise ValueError('Insufficient fire materials')
        for key, amount in deductions.items():
            state['inventory'][key] = float(Decimal(str(state['inventory'].get(key, 0))) - amount)

    def _start_fire(self, state: dict, data: dict, at: int) -> tuple[dict, bool]:
        fire = self.entity(state, data.get('userFireId'), 'fire_type')
        person = self.entity(state, data.get('villagerId'), 'villager_type')
        if not self.world.can_work(person, at):
            raise ValueError('Villager cannot light a fire at this life stage')
        if fire.get('isBurning') and at < fire.get('endsAt', 0):
            return self._fire_response(state, fire), False
        if any(job.get('villagerId') == person['id'] and job.get('status') == 'working'
               and at < job.get('completionTime', 0) for job in active_work(state)):
            raise ValueError('Villager is working')
        if any(entity.get('lightingVillagerId') == person['id']
               and at < entity.get('lightingCompleteAt', 0)
               for entity in state['world']['entities']):
            raise ValueError('Villager is lighting another fire')
        task_row = next((row for row in self.defs.rows('fire_task')
                         if row['fireType'] == str(fire['templateId'])), None)
        if task_row is None:
            raise NotImplementedError('No original fire task for this fire')
        task = self._item('task', task_row['taskId'])
        rewards = [row for row in self.defs.rows('reward_set_item')
                   if row['setId'] == task['rewardSet']]
        if not rewards or any(Decimal(row['chance']) != 1 for row in rewards):
            raise NotImplementedError('Fire reward probability rule is not recovered')
        requirements = [row for row in self.defs.rows('requirement_set_item')
                        if row['requirementSet'] == task['requirementSet']]
        self._spend(state, requirements)
        fire.update(isBurning=1, startsAt=at,
                    endsAt=at + int(task_row['burnDuration']), oilAppliedAt=0,
                    lightingVillagerId=person['id'],
                    lightingCompleteAt=at + int(task['duration']), activeReward={})
        for reward in rewards:
            key = str(reward['materialType'])
            amount = float(reward['quantity'])
            state['inventory'][key] = state['inventory'].get(key, 0) + amount
            fire['activeReward'][key] = fire['activeReward'].get(key, 0) + amount
        result = self._fire_response(state, fire)
        people = {entity['id'] for entity in state['world']['entities']
                  if entity.get('templateType') == 'villager_type'
                  and self.world._area(entity) == state['areaId']}
        result['SatisfiedWantModels'] = satisfy_wants(state, people, 4, at)
        return result, True

    def _oil_fire(self, state: dict, data: dict, at: int) -> tuple[dict, bool]:
        fire = self.entity(state, data.get('userFireId'), 'fire_type')
        if not fire.get('isBurning') or at >= fire.get('endsAt', 0):
            raise ValueError('Light this fire before adding oil')
        duration = int(self.world.global_value('oilBurnDuration'))
        maximum = int(self.world.global_value('oilMaxBurnDuration'))
        if fire['endsAt'] - at + duration > maximum:
            raise ValueError('Fire burn-time limit reached')
        cost = int(self._item('fire_type', fire['templateId'])['oilQuantity'])
        if state['inventory'].get('8', 0) < cost:
            raise ValueError('Not enough oil')
        state['inventory']['8'] -= cost
        fire['endsAt'] += duration
        fire['oilAppliedAt'] = at
        return self._fire_response(state, fire), True

    def _bed(self, state: dict, ident) -> tuple[dict, dict]:
        if not isinstance(ident, str) or not ident:
            raise ValueError('Bed identifier required')
        for shelter in state['world']['entities']:
            if shelter.get('templateType') == 'shelter':
                for bed in shelter.get('beds', []):
                    if bed.get('id') == ident:
                        if self.world._area(shelter) != state['areaId']:
                            raise ValueError('Shelter is in another area')
                        return shelter, bed
        raise ValueError('Unknown bed in this village')

    def _assign(self, state: dict, data: dict, at: int) -> tuple[dict, bool]:
        person = self.entity(state, data.get('villagerId'), 'villager_type')
        shelter, target = self._bed(state, data.get('shelterBedId'))
        if target.get('villagerId') not in {'', None, person['id']}:
            raise ValueError('Bed is occupied')
        if person.get('shelterBedId') == target['id'] and target.get('villagerId') == person['id']:
            return {}, False
        old_id = person.get('shelterBedId')
        if old_id:
            old_shelter, old_bed = self._bed(state, old_id)
            old_bed['villagerId'] = ''
            if not any(bed.get('villagerId') for bed in old_shelter.get('beds', [])):
                old_shelter['happinessCollectedAt'] = 0
        occupied = any(bed.get('villagerId') for bed in shelter.get('beds', []))
        target['villagerId'] = person['id']
        person['shelterBedId'] = target['id']
        if not occupied:
            shelter['happinessCollectedAt'] = at
        satisfied = satisfy_wants(state, {person['id']}, 6, at)
        return ({'SatisfiedWantModels': satisfied} if satisfied else {}), True

    def _empty(self, state: dict, data: dict) -> tuple[dict, bool]:
        shelter, bed = self._bed(state, data.get('shelterBedId'))
        ident = bed.get('villagerId')
        if not ident:
            return {}, False
        person = self.entity(state, ident, 'villager_type')
        self.release_bed(person, shelter, bed)
        return {}, True

    @staticmethod
    def release_bed(person: dict, shelter: dict, bed: dict) -> None:
        person['shelterBedId'] = ''
        bed['villagerId'] = ''
        if not any(value.get('villagerId') for value in shelter.get('beds', [])):
            shelter['happinessCollectedAt'] = 0

    def _happiness(self, state: dict, data: dict, at: int,
                   reset: bool = False) -> tuple[dict, bool]:
        shelter = self.entity(state, data.get('userShelterId'), 'shelter')
        stamp = int(shelter.get('happinessCollectedAt', 0))
        if reset:
            changed = not stamp and any(bed.get('villagerId') for bed in shelter.get('beds', []))
            if changed:
                shelter['happinessCollectedAt'] = at
            return {'userShelter': {'id': shelter['id'],
                                    'happinessCollectedAt': shelter['happinessCollectedAt']}}, changed
        occupants = sum(bool(bed.get('villagerId')) for bed in shelter.get('beds', []))
        if occupants == 0:
            raise ValueError('Shelter has no occupants')
        if at - stamp < SHELTER_INTERVAL:
            raise ValueError('Shelter happiness is not ready')
        reward = int(self._item('shelter', shelter['templateId'])['happinessReward']) * occupants
        state['user']['xp'] += reward
        shelter['happinessCollectedAt'] = at
        return {'userShelter': {'id': shelter['id'], 'happinessCollectedAt': at},
                'xp': reward}, True

    def operate(self, state: dict, service: str, data: dict, at: int,
                receipt_key: str | None = None, *, legacy_import: bool = False) -> tuple[dict, bool]:
        migrated = self.migrate(state, at, legacy_import=legacy_import)
        expired = self.sync(state, at)
        prechanged = migrated or expired
        key = service + ':' + receipt_key if receipt_key else None
        signature = json.dumps(data, sort_keys=True, separators=(',', ':'))
        receipt = state.get('habitatReceipts', {}).get(key) if key else None
        if receipt:
            if receipt['request'] != signature:
                raise ValueError('Request identifier reused for another habitat action')
            if prechanged:
                state['revision'] = int(state.get('revision', 0)) + 1
                state['updatedAt'] = at
            return copy.deepcopy(receipt['response']), prechanged
        if service.endswith('/StartFire'):
            response, action_changed = self._start_fire(state, data, at)
        elif service.endswith('/OilFire'):
            response, action_changed = self._oil_fire(state, data, at)
        elif service.endswith('/AssignBedToVillager'):
            response, action_changed = self._assign(state, data, at)
        elif service == REMOVE_SHELTER:
            response, action_changed = remove_shelter(state, data, self.defs)
        elif service.endswith('/EmptyBed'):
            response, action_changed = self._empty(state, data)
        else:
            response, action_changed = self._happiness(
                state, data, at, service.endswith('/ResetHappinessTimer'))
        if key:
            state.setdefault('habitatReceipts', {})[key] = {
                'request': signature, 'response': copy.deepcopy(response)}
            action_changed = True
        changed = prechanged or action_changed
        if changed:
            state['revision'] = int(state.get('revision', 0)) + 1
            state['updatedAt'] = at
        return response, changed
