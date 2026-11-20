"""Original paired care activities, with durable completion and repeat timing."""
from __future__ import annotations
from villagelife.persistence.history import active_work

from decimal import Decimal
from functools import cached_property

from .daily import DailyLife, satisfy_wants


SERVICE = 'ClientVillagerService/PerformInteractiveActivity'


class OriginalInteractiveRules:
    def __init__(self, definitions, inventory, daily: DailyLife):
        self.defs = definitions
        self.inventory = inventory
        self.daily = daily

    @cached_property
    def activities(self) -> dict[int, dict]:
        return {int(row['id']): row for row in self.defs.rows('interactive_activity')
                if row['id'] != '0' and row['isActive'] == '1'
                and row['buildingType'] == '0' and row['relationSet'] == '0'}

    def eligible(self, person: dict, activity: dict, at: int) -> bool:
        if activity['id'] == '10':
            return self.daily.world.current_villager_type(person, at).get('name') == 'Dog Villager'
        return self.daily.in_group(person, activity['requesterVillagerSet'], at)

    def available(self, state: dict, person: dict, actors: list[dict], at: int) -> list[dict]:
        area = self.daily.world._area(person)
        return [activity for activity in self.activities.values()
                if self.eligible(person, activity, at)
                and at - state.get('interactiveLastAt', {}).get(
                    person['id'] + ':' + activity['id'], -int(activity['repeatDelaySecs'])
                ) >= int(activity['repeatDelaySecs'])
                and any(other['id'] != person['id'] and self.daily.world._area(other) == area
                        and self.daily.in_group(other, activity['supplierVillagerSet'], at)
                        for other in actors)]

    def perform(self, state: dict, data: dict, at: int) -> dict:
        raw = data.get('activityId')
        if type(raw) not in (int, str) or not str(raw).isdigit():
            raise ValueError('Interactive activity identifier required')
        activity = self.activities.get(int(raw))
        if activity is None:
            raise ValueError('Interactive activity is unavailable')
        people = {person['id']: person for person in state['world']['entities']
                  if person.get('templateType') == 'villager_type'
                  and self.daily.world._area(person) == state['areaId']}
        requester_id, supplier_id = data.get('requesterVillagerId'), data.get('supplierVillagerId')
        if not isinstance(requester_id, str) or not isinstance(supplier_id, str):
            raise ValueError('Two villager identifiers are required')
        requester = people.get(requester_id)
        supplier = people.get(supplier_id)
        if requester is None or supplier is None or requester is supplier:
            raise ValueError('Two distinct villagers in the active area are required')
        if (not self.eligible(requester, activity, at)
                or not self.daily.in_group(supplier, activity['supplierVillagerSet'], at)):
            raise ValueError('Villagers do not meet the original activity roles')

        clock = requester['id'] + ':' + activity['id']
        prior = state.get('lastInteractiveActions', {}).get(clock)
        if prior and at - prior['startedAt'] < int(activity['repeatDelaySecs']):
            if prior['supplierId'] == supplier['id']:
                return self.reply(state, requester, supplier, prior['satisfied'])
            raise ValueError('Activity repeat delay has not elapsed')
        if any(job.get('villagerId') in {requester['id'], supplier['id']}
               and job.get('status') == 'working' and job['completionTime'] > at
               for job in active_work(state)):
            raise ValueError('A villager is still working')

        deductions = {}
        stock = state['inventory']
        for row in self.defs.rows('requirement_set_item'):
            if activity['requirementSet'] == '0' or row['requirementSet'] != activity['requirementSet']:
                continue
            key = row['materialType']
            if Decimal(str(stock.get(key, 0))) < Decimal(row['quantity']):
                raise ValueError('Not enough materials for the activity')
            deductions[key] = deductions.get(key, Decimal(0)) + Decimal(row['quantityUsed'])
        for key, cost in deductions.items():
            if Decimal(str(stock.get(key, 0))) < cost:
                raise ValueError('Not enough materials for the activity')
        if activity['rewardSet'] != '0':
            raise NotImplementedError('Interactive reward set is not recovered')
        for key, cost in deductions.items():
            stock[key] = float(Decimal(str(stock.get(key, 0))) - cost)

        cap = self.daily.xp_cap(state)
        for person, role in ((requester, 'requester'), (supplier, 'supplier')):
            self.daily.spend_energy(person, int(activity[role + 'EnergyUsed']), at)
            person['xp'] = min(cap, person.get('xp', 0) + int(activity['xpReward']))
        satisfied = satisfy_wants(state, {requester['id']}, 8, at, int(activity['materialType']))
        state.setdefault('interactiveLastAt', {})[clock] = at
        saved = {'participants': [requester['id'], supplier['id'], activity['id']],
                 'supplierId': supplier['id'], 'satisfied': satisfied, 'startedAt': at,
                 'completionTime': at + int(activity['durationSecs'])}
        state.setdefault('lastInteractiveActions', {})[clock] = saved
        state.setdefault('interactiveReceipts', {})[clock + ':' + str(at)] = saved
        state['revision'] = int(state.get('revision', 0)) + 1
        return self.reply(state, requester, supplier, satisfied)

    def reply(self, state: dict, requester: dict, supplier: dict, satisfied: list[dict]) -> dict:
        result = {'inventory': self.inventory.list_items(state), 'SatisfiedWantModels': satisfied,
                  'HappinessModels': [{'VillagerStringID': person['id'], 'Xp': person.get('xp', 0)}
                                      for person in (requester, supplier)]}
        return {**result, 'result': result}
