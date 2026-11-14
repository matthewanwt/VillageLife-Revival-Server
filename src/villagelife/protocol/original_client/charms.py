"""Original free and paid baby charms, persisted before the reveal."""
from __future__ import annotations

import copy
import math
import uuid
from decimal import Decimal

from .birth_skills import parent_shields
from .family import pregnant
from .inventory import spend_gems
from .native_ids import reserve_ids
from .relationships import actor, add_relation, touch

PURCHASE = 'ClientFortune/Gacha'
CONSUME = 'ClientFortune/ConsumeGacha'
SERVICES = {PURCHASE, CONSUME}


class OriginalBabyCharmRules:
    def __init__(self, family, economy):
        self.family = family
        self.defs = family.defs
        self.choose = economy._choose

    def pack(self, raw, *, hud=False):
        if isinstance(raw, bool) or not str(raw).isdecimal():
            raise ValueError('Original baby charm identifier required')
        item = self.defs.item('runeSetItem', raw)
        group = self.defs.item('runeSet', item['runeSet'])
        if item['isHUD'] != ('1' if hud else '0') or int(group['HudOrder' if hud else 'conceptionOrder']) < 0:
            raise ValueError('Charm pack is unavailable in this screen')
        if not 1 <= int(item['runeAmount']) <= 3:
            raise ValueError('Invalid original baby charm quantity')
        return item, group

    @staticmethod
    def price(item, group, at):
        cost = Decimal(item['gemCost'])
        if int(group['SaleStartEpoch']) <= at < int(group['SaleEndEpoch']):
            cost *= 1 - Decimal(group['discount'])
        return math.floor(cost)

    def reward(self, set_id, rng):
        row = self.choose([r for r in self.defs.rows('runeRewardPoolProb')
                           if r['runeRewardSet'] == set_id], 'probability', rng)
        kind, pool = row['poolType'], row['pool']
        if kind == '1':
            reward = self.choose([r for r in self.defs.rows('gachaRewardSet') if r['pool'] == pool],
                                 'probability', rng)
            items = [r for r in self.defs.rows('gachaRewardSetItem') if r['setId'] == reward['id']]
            return [{'Material': {'MaterialId': int(r['materialType']), 'Quantity': float(r['quantity'])}}
                    for r in items]
        if kind not in {'0', '2'}:
            raise ValueError('Unknown original baby charm reward type')
        seed = self.choose([r for r in self.defs.rows('gachaVillager') if r['pool'] == pool
                            and (kind == '0' or r['partnerID'] != '0')], 'probability', rng)
        ids = [int(seed['id'])]
        if kind == '2':
            ids.append(int(seed['partnerID']))
        return [{'Villagers': [{'villagerBaseId': ident} for ident in ids]}]

    def draw(self, item, group, rng):
        bonus_fields = ('noBonusProb', 'X1BonusProb', 'X2BonusProb', 'X3BonusProb')
        bonuses = [{'count': i, 'weight': group[field]} for i, field in enumerate(bonus_fields)]
        packs = []
        for _ in range(int(item['runeAmount'])):
            rewards = self.reward(group['mainRuneRewardSetId'], rng)
            for _ in range(self.choose(bonuses, 'weight', rng)['count']):
                rewards.extend(self.reward(group['bonusRuneRewardSet'], rng))
            packs.append(rewards)
        return packs

    def _award_villager(self, state, base_id, at):
        seed = self.defs.item('gachaVillager', base_id)
        ages = [int(age) for age in seed['ageRange'].split(',')]
        index = next((i for i, age in enumerate(ages) if age >= 18), 0)
        age = ages[index]
        kinds = [self.defs.item('villager_type', ident) for ident in seed['villagerType'].split(',')]
        kind = next((row for row in kinds if int(row['minAge']) <= age <= int(row['maxAge'])),
                    kinds[index])
        area = state['areaId']
        entities = state['world']['entities']
        position = next((entity['position'] for entity in entities
                         if entity.get('templateType') in {'shrine', 'workshop'}
                         and self.family.world._area(entity) == area), {'x': 1600, 'y': 3500, 'areaId': area})
        valid = {row['id'] for row in self.defs.rows('villager_skill')} - {'0'}
        skills = []
        for ident in seed.get('skills', '').split(','):
            if ident in valid and sum(skill['skilltypeId'] == int(ident) for skill in skills) < 3:
                skills.append({'skilltypeId': int(ident), 'skillOriginType': 0})
        person = {
            'id': 'local-gacha-' + uuid.uuid4().hex, 'refId': '', 'name': seed['name'],
            'templateType': 'villager_type', 'templateId': int(kind['id']), 'serverPersisted': True,
            'villagerBaseId': int(base_id), 'collectionBaseId': int(base_id), 'startingArea': area,
            'birthType': 0, 'specialType': 0, 'energyLevel': int(kind['maxEnergy']), 'energyTimeStamp': at,
            'startAge': 0, 'bornAt': at - age * self.family.world.seconds_per_year, 'updatedAt': at,
            'pregnant': 'false', 'pregnancyTryCount': 0, 'pregnancyStartTime': 0,
            'gender': int(seed['genderType']), 'xp': 0, 'rarity': int(seed['star']), 'shelterBedId': '',
            'position': {'x': position['x'] + 40, 'y': position['y'], 'areaId': area, 'rotation': 0},
            'equipment': seed['equipment'], 'genetics': '', 'relations': [], 'skills': skills,
            'wants': [], 'clothing': [], 'isCommunityVillager': 'false', 'retireAt': 0, 'retireEventID': 0,
        }
        entities.append(person)
        collection = state.setdefault('villagerCollection', {})
        key = str(base_id)
        collection[key] = max(2, collection.get(key, 0))
        return person

    def open_villager_charm(self, state, service, data, at, owner, rng):
        item, group = self.pack(data.get('CharmSetID'), hud=True)
        results = self.draw(item, group, rng)
        previews = [entry for pack in results for reward in pack for entry in reward.get('Villagers', [])]
        if len(previews) > max(0, self.family.places(state)):
            raise ValueError('Not enough population capacity for this villager charm')
        inventory = state['inventory']
        if service == CONSUME:
            material, amount = group['materialType'], int(item['runeAmount'])
            if material == '0' or inventory.get(material, 0) < amount:
                raise ValueError('Not enough owned charms')
            inventory[material] -= amount
        else:
            cost = self.price(item, group, at)
            if cost <= 0:
                raise ValueError('This pack requires an earned charm')
            spend_gems(state, cost)
        awards = []
        for pack in results:
            for reward in pack:
                if 'Material' in reward:
                    material = reward['Material']
                    key = str(material['MaterialId'])
                    inventory[key] = inventory.get(key, 0) + material['Quantity']
                else:
                    people = [self._award_villager(state, entry['villagerBaseId'], at)
                              for entry in reward['Villagers']]
                    if len(people) == 2:
                        add_relation(people[0], people[1], 2)
                        add_relation(people[1], people[0], 2)
                    awards.extend(zip(reward['Villagers'], people))
        if awards:
            registry = reserve_ids(state, owner, [])
            for preview, person in awards:
                preview.update(VillagerId=int(registry[person['id']]), BornAt=person['bornAt'])
        touch(state, at)
        return {'result': results}

    def operate(self, state, service, data, at, owner, rng):
        target = data.get('VillagerStringId')
        if not target:
            return self.open_villager_charm(state, service, data, at, owner, rng)
        mother = actor(state, target)
        record = state.get('pregnancies', {}).get(mother['id'], {})
        if record.get('status') != 'pregnant' or not pregnant(mother):
            raise ValueError('An active saved pregnancy is required for baby charms')
        item, group = self.pack(data.get('CharmSetID'))
        saved = record.get('charmChoice')
        if saved:
            if item['id'] != saved['sku']:
                raise ValueError('This pregnancy already has a baby charm choice')
            return copy.deepcopy(saved['response'])
        if record['designFinalized'] and record['kind'] != 1:
            raise ValueError('This pregnancy already has a paid design choice')
        cost = self.price(item, group, at)
        if service == CONSUME and cost:
            raise ValueError('This baby charm requires its gem purchase')
        spend_gems(state, cost)
        results = self.draw(item, group, rng)
        rewards = [reward for pack in results for reward in pack]
        previews = [value for reward in rewards for value in reward.get('Villagers', [])]
        if not previews:
            raise ValueError('The authored baby charm draw did not include a child')
        if self.family.places(state, mother['id']) < len(previews):
            raise ValueError('Not enough population capacity for these babies')
        plans = []
        for preview in previews:
            seed = self.defs.item('gachaVillager', preview['villagerBaseId'])
            plans.append(self.family.plan(int(seed['genderType']), rng, seed))
        registry = reserve_ids(state, owner, [plan['id'] for plan in plans])
        for preview, plan in zip(previews, plans, strict=True):
            preview.update(VillagerId=int(registry[plan['id']]), BornAt=at)
        for reward in rewards:
            if 'Material' in reward:
                material = reward['Material']
                ident = str(material['MaterialId'])
                state['inventory'][ident] = state['inventory'].get(ident, 0) + material['Quantity']
        response = {'result': results}
        father = actor(state, record['fatherId'])
        record.update(children=plans, designFinalized=True,
                      inheritedSkills=parent_shields(self.defs, mother, father),
                      charmChoice={'sku': item['id'], 'gemsSpent': cost, 'response': copy.deepcopy(response)})
        touch(state, at)
        return response

