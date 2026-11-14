"""Source-backed villager fun actions and durable fun-building wear."""
from __future__ import annotations

import copy
from decimal import Decimal

from .catalog import OriginalDefinitions
from .inventory import OriginalInventoryRules
from .daily import DailyLife
from .randomness import randbelow


class OriginalFunRules:
    SERVICE = 'ClientVillagerService/PerformFunActivity'

    def __init__(self, definitions: OriginalDefinitions,
                 inventory: OriginalInventoryRules | None = None):
        self.defs = definitions
        self.inventory = inventory or OriginalInventoryRules(definitions)
        self.daily = DailyLife(definitions)
        self.world = self.daily.world

    def initialize(self, entity: dict) -> bool:
        if entity.get('templateType') != 'fun_building' or 'amount' in entity:
            return False
        building = self.defs.item('fun_building', entity['templateId'])
        activity = self.defs.item('fun_activity', building['funActivity'])
        uses = int(activity['itemWear'])
        if uses == -1 and activity.get('unbreakable', '0') == '1':
            # The original native world loader expects a positive amount for a
            # usable building; use a local sentinel for authored unbreakables.
            uses = 1_000_000_000
            entity['counterPolicy'] = 'local positive wire sentinel for unbreakable activity'
        elif uses <= 0:
            raise NotImplementedError('Nonpositive fun-use counter is not recovered')
        entity['amount'] = uses
        entity['funCounterEvidence'] = (
            'authored fun_activity.itemWear; native loader reads amount and '
            'completion decrements one use')
        return True

    def migrate(self, state: dict) -> bool:
        changed = False
        for entity in state.get('world', {}).get('entities', []):
            changed = self.initialize(entity) or changed
        if changed:
            state['revision'] = int(state.get('revision', 0)) + 1
            state.setdefault('rules', {})['fun_building_wear'] = {
                'evidence': 'original fun_activity.itemWear and native amount field',
                'status': 'authored wear counter; migrated once'}
        return changed

    def _actor(self, state: dict, ident: object) -> dict:
        actor = next((item for item in state.get('world', {}).get('entities', [])
                      if item.get('id') == ident and
                      item.get('templateType') == 'villager_type'), None)
        if actor is None:
            raise ValueError('Unknown villager')
        if self.world._area(actor) != state['areaId']:
            raise ValueError('Villager is in another area')
        return actor

    def _eligible(self, actor: dict, activity: dict, at: int) -> bool:
        kind = str(self.world.current_villager_type(actor, at)['id'])
        return any(row['villagerSet'] == activity['usedBy'] and
                   str(row['villagerType']) == kind
                   for row in self.defs.rows('villager_set_item'))

    def _reply(self, state: dict, actor: dict, building: dict | None,
               satisfied: list[dict]) -> dict:
        happiness = {'VillagerStringId': actor['id'],
                     'VillagerStringID': actor['id'],
                     'Xp': actor.get('xp', 0)}
        return {
            'user': copy.deepcopy(state['user']),
            'inventory': self.inventory.list_items(state),
            'HappinessModel': happiness,
            'SatisfiedWantModels': copy.deepcopy(satisfied),
            'userFunBuildingType': ({'id': building['id'],
                                     'amount': building.get('amount', 0)}
                                    if building else {}),
        }

    def perform(self, state: dict, data: dict, at: int,
                receipt_key: str, rng: dict) -> dict:
        actor = self._actor(state, data.get('villagerId'))
        activity_id = data.get('funActivityId')
        if isinstance(activity_id, bool) or not isinstance(activity_id, int):
            raise ValueError('Fun activity identifier required')
        building_id = data.get('userFunBuildingTypeId')
        building = next((item for item in state.get('world', {}).get('entities', [])
                         if item.get('id') == building_id and
                         item.get('templateType') == 'fun_building'), None)

        receipt = state.get('funReceipts', {}).get(receipt_key)
        if receipt:
            if (receipt['actor'] != actor['id'] or
                    receipt['activity'] != activity_id or
                    receipt['building'] != building_id):
                raise ValueError('Fun call identifier reused for different inputs')
            return self._reply(state, actor, building, receipt['satisfied'])

        activity = self.defs.item('fun_activity', activity_id)
        portable = building_id is None
        if portable:
            if any(str(row['funActivity']) == str(activity_id)
                   for row in self.defs.rows('fun_building')):
                raise ValueError('Saved fun building required')
            material = str(activity['materialType'])
            if Decimal(str(state.get('inventory', {}).get(material, 0))) <= 0:
                raise ValueError('Portable fun item is not owned')
        else:
            if building is None:
                raise ValueError('Saved fun building required')
            if self.world._area(building) != state['areaId']:
                raise ValueError('Fun building is in another area')
            definition = self.defs.item('fun_building', building['templateId'])
            if int(definition['funActivity']) != activity_id:
                raise ValueError('Activity does not match fun building')
            self.initialize(building)
        if not self._eligible(actor, activity, at):
            raise ValueError('This age group cannot use that activity')
        if any(job.get('villagerId') == actor['id'] and
               job.get('status') == 'working' and
               int(job.get('completionTime', 0)) > at
               for job in state.get('workAreas', {}).values()):
            raise ValueError('Villager is still working')
        if building is not None and int(building.get('amount', 0)) <= 0:
            raise ValueError('Fun building has no uses remaining')

        last = state.get('lastFunAt', {}).get(actor['id'])
        if last is not None and at - int(last) < int(activity['durationSecs']):
            # The client sends completion after its activity animation. Ignore
            # duplicate callbacks inside that authored duration without spend.
            return self._reply(state, actor, building, [])

        rewards = ([row for row in self.defs.rows('reward_set_item')
                    if row['setId'] == activity['rewardSet']]
                   if activity.get('rewardSet', '0') != '0' else [])
        # reward_set_item chance is authored as a probability/weight. For the
        # 75/25 activity reward set, one mutually-exclusive item is awarded.
        # Guaranteed chance-1 rows remain additive when a set also contains a
        # probabilistic choice.
        guaranteed = [row for row in rewards if Decimal(row['chance']) == 1]
        uncertain = [row for row in rewards if Decimal(row['chance']) not in (0, 1)]
        selected = []
        if uncertain:
            scale = 1_000_000_000
            weights = [int(Decimal(row['chance']) * scale) for row in uncertain]
            total = sum(weights)
            if any(weight < 0 for weight in weights) or total <= 0:
                raise ValueError('Invalid original fun reward chances')
            ticket = randbelow(rng, total)
            for row, weight in zip(uncertain, weights):
                if ticket < weight:
                    selected.append(row)
                    break
                ticket -= weight
            if not selected:
                raise ValueError('Original fun reward selection failed')
        # A set with multiple chance-1 rows represents a guaranteed bundle.
        selected = guaranteed + selected
        level = next((row for row in self.defs.rows('user_level')
                      if int(row['levelNumber']) ==
                      int(state['user']['userLevelID'])), None)
        if level is None:
            raise ValueError('Unknown original user level')

        actor['xp'] = min(int(level['villagerXPCapacity']),
                          int(actor.get('xp', 0)) + int(activity['xpReward']))
        if int(state['user']['userLevelID']) >= int(activity['energyDeductionLevel']):
            cost = int(activity['energyCost'])
            if cost:
                self.daily.recover_energy(actor, at)
                actor['energyLevel'] = max(0, int(actor.get('energyLevel', 0)) - cost)
                actor['energyTimeStamp'] = at
        if activity.get('unbreakable', '0') != '1':
            if building is not None:
                building['amount'] -= 1
            elif int(activity['itemWear']) > 0:
                material = str(activity['materialType'])
                current = Decimal(str(state['inventory'].get(material, 0)))
                state['inventory'][material] = float(max(
                    Decimal(0), current - Decimal(1) / Decimal(activity['itemWear'])))
        if portable:
            state.setdefault('rules', {})['portable_fun'] = {
                'evidence': 'native no-building activity path and authored itemWear',
                'status': 'local reconstruction; owned item wear, XP, energy and eligibility'}
        for reward in selected:
            key = str(reward['materialType'])
            state['inventory'][key] = float(
                Decimal(str(state['inventory'].get(key, 0))) +
                Decimal(str(reward['quantity'])))

        wants = [want for want in state.get('wants', [])
                 if want.get('VillagerStringID') == actor['id'] and
                 int(want.get('MaterialID', -1)) == int(activity['materialType']) and
                 int(want.get('wantableCategoryType', -1)) == 3]
        satisfied = [{'WantId': want['WantId'],
                      'VillagerStringID': actor['id']} for want in wants]
        completed_ids = {want['WantId'] for want in wants}
        state['wants'] = [want for want in state.get('wants', [])
                          if want.get('WantId') not in completed_ids]
        state.setdefault('needSatisfiedAt', {})[actor['id'] + ':3'] = at
        state.setdefault('lastFunAt', {})[actor['id']] = at
        state.setdefault('funReceipts', {})[receipt_key] = {
            'actor': actor['id'], 'activity': activity_id,
            'building': building_id, 'satisfied': copy.deepcopy(satisfied),
            'completedAt': at}
        state['revision'] = int(state.get('revision', 0)) + 1
        return self._reply(state, actor, building, satisfied)
