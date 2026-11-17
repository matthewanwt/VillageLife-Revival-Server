"""Original conception, birth and pregnancy timer requests."""
from __future__ import annotations
from .collection_projection import ordinary_seed

import copy
import uuid

from .birth_skills import newborn_shields, parent_shields
from .daily import satisfy_wants
from .inventory import spend_gems
from .native_ids import reserve_ids
from .randomness import randbelow
from .relationships import actor, actors, add_relation, free_places, partner, touch
from .timers import f32, gem_price

WISHES = {'ClientWant/GenerateBirthWants', 'ClientWant/GenerateChildWants'}
CONCEIVE = 'ClientVillager/CanConcievePregnancy'
RETRY = 'ClientVillager/SkipRetryConcievePregnancy'
DESIGN = 'ClientVillager/DesignPregnancy'
BIRTH = 'ClientVillager/Birth'
SKIP = 'ClientVillagerService/SkipPregnancy'
SERVICES = WISHES | {CONCEIVE, RETRY, DESIGN, BIRTH, SKIP}


def pregnant(person):
    return str(person.get('pregnant', 'false')).lower() in {'true', '1'}


class OriginalFamilyRules:
    def __init__(self, world, inventory, wants):
        self.world = world
        self.defs = world.defs
        self.inventory = inventory
        self.wants = wants

    def setting(self, name):
        return int(self.world.global_value(name))

    def places(self, state, excluding=None):
        return free_places(state, self.world, excluding)

    def couple(self, state, ident, at):
        mother = actor(state, ident)
        if int(mother.get('gender', 0)) != 1:
            raise ValueError('A mother is required')
        father = actor(state, partner(mother, 2))
        if int(father.get('gender', 0)) != 0 or partner(father, 2) != mother['id']:
            raise ValueError('A reciprocal marriage is required')
        minimum = self.setting('minAgeForDating')
        if (not minimum <= int(self.world.current_age(mother, at)) <= self.setting('childWantFemaleMaxAge')
                or self.world.current_age(father, at) < minimum):
            raise ValueError('Parents must meet the original age limits')
        bed_ids = {mother['id']: mother.get('shelterBedId'), father['id']: father.get('shelterBedId')}
        for shelter in state['world']['entities']:
            if shelter.get('templateType') != 'shelter':
                continue
            occupants = {b.get('villagerId') for b in shelter.get('beds', [])
                         if b.get('villagerId') in bed_ids and b.get('id') == bed_ids[b['villagerId']]}
            if occupants == set(bed_ids):
                return mother, father
        raise ValueError('Both married parents must occupy the same shelter')

    def eligible(self, state, mother, at):
        try:
            mother, father = self.couple(state, mother['id'], at)
        except ValueError:
            return False
        if pregnant(mother) or self.places(state) < 1 or self.world._area(mother) != state['areaId']:
            return False
        married = max(int(mother.get('marriedAt', 0)), int(father.get('marriedAt', 0)),
                      int(state.get('createdAt', 0)))
        if at - married < self.setting('childWantDelayAfterMarriage'):
            return False
        previous = max(int(mother.get('lastChildBornAt', 0)), int(father.get('lastChildBornAt', 0)))
        if previous and at - previous < self.setting('childWantDelayAfterLastChild'):
            return False
        if state['areaId'] == 2:
            count = int(state['user']['populationCap']) - self.places(state)
            limit = self.setting('ageOfMaxChildrenForChildWantArea2')
            children = [p for p in actors(state) if any(r['villagerId'] == mother['id'] and int(r['type']) == 0
                                                        for r in p.get('relations', []))]
            if (count >= self.setting('maxVillagersForChildWantArea2')
                    or any(self.world.current_age(p, at) < limit for p in children)):
                return False
        return True

    def generate(self, state, at):
        before = state.get('wants', [])
        eligible = [p for p in actors(state) if int(p.get('gender', 0)) == 1 and self.eligible(state, p, at)]
        allowed = {p['id'] for p in eligible}
        kept = [w for w in before if w.get('MaterialID') != 343 or w['VillagerStringID'] in allowed]
        changed = kept != before
        state['wants'] = kept
        existing = {w['VillagerStringID'] for w in kept if w.get('wantableCategoryType') == 5}
        for mother in eligible:
            ident = mother['id']
            record = state.get('pregnancies', {}).get(ident, {})
            if ident in existing or self.retry_remaining(record, at):
                continue
            last = state.get('childWantGeneratedAt', {}).get(ident)
            if last is not None and at - last < self.setting('waitDurationAfterLastChildWantGen'):
                continue
            self.wants._append(state, mother, 5, 343, at)
            state.setdefault('childWantGeneratedAt', {})[ident] = at
            changed = True
        if changed:
            touch(state, at)
        return {'result': copy.deepcopy(state['wants'])}

    @staticmethod
    def reply(mother, satisfied=()):
        return {'result': {'ErrorCode': 0,
                           'PregnancyInfo': {'pregnant': int(pregnant(mother)),
                                             'pregnancyStartTime': mother.get('pregnancyStartTime', 0),
                                             'pregnancyTryCount': mother.get('pregnancyTryCount', 0)},
                           'SatisfiedWantModels': list(satisfied)}}

    def inventory_reply(self, state):
        inventory = self.inventory.list_items(state)
        return {'result': {'Inventory': inventory, 'inventory': inventory, 'SatisfiedWantModels': []},
                'inventory': inventory}

    def plan(self, gender, rng, gacha=None):
        ref = 'baby female' if gender else 'baby male'
        seeds = [r for r in self.defs.rows('villager_starting_variation')
                 if r.get('refId') == ref and r.get('SpecialType', '0') == '0']
        if not seeds:
            raise ValueError('Missing original newborn appearance')
        seed = seeds[randbelow(rng, len(seeds))]
        return {'id': 'family-child-' + uuid.uuid4().hex, 'gender': gender, 'seedId': seed['id'],
                **({'gachaBaseId': gacha['id']} if gacha else {})}

    def children(self, kind, places, rng):
        count = {2: 2, 9: 3}.get(kind, 1)
        if kind == 1 and places >= 2 and randbelow(rng, 100) < self.setting('twinsChance'):
            count = 2
        if places < count:
            raise ValueError('Not enough population capacity for these babies')
        return [self.plan(0 if kind == 7 else 1 if kind == 8 else randbelow(rng, 2), rng)
                for _ in range(count)]

    def retry_remaining(self, record, at):
        if record.get('status') != 'failed' or record.get('retryUnlockedAt'):
            return 0
        return max(0, record['attemptedAt'] + self.setting('pregnancySkipRetryDuration') - at)

    def conceive(self, state, data, at, rng):
        mother = actor(state, data.get('villagerId'))
        ident = mother['id']
        records = state.setdefault('pregnancies', {})
        last = records.get(ident, {})
        if pregnant(mother):
            return self.reply(mother, last.get('satisfiedWants', []))
        mother, father = self.couple(state, ident, at)
        if self.retry_remaining(last, at):
            return self.reply(mother)
        if not self.eligible(state, mother, at):
            raise ValueError('This couple is not ready for a baby')
        tries = int(mother.get('pregnancyTryCount', 0)) + 1
        success = (tries >= self.setting('retriesBeforePregnancySuccess')
                   or randbelow(rng, 100) < self.setting('pregnancyChancePercentage'))
        record = {'id': uuid.uuid4().hex, 'motherId': ident, 'fatherId': father['id'],
                  'attemptedAt': at, 'status': 'pregnant' if success else 'failed',
                  'kind': 1, 'designFinalized': False, 'children': []}
        if success:
            record['inheritedSkills'] = parent_shields(self.defs, mother, father)
            record['children'] = self.children(1, self.places(state), rng)
            record['readyAt'] = int(f32(at)) + self.setting('pregnancySkipDuration')
        # Clear the baby wish after either result. The failed attempt is saved
        # with its retry timer and cannot be rerolled by reopening the UI.
        record['satisfiedWants'] = satisfy_wants(state, {ident, father['id']}, 5, at, 343)
        mother.update(pregnant='true' if success else 'false', pregnancyStartTime=at,
                      pregnancyTryCount=tries, updatedAt=at)
        records[ident] = record
        touch(state, at)
        return self.reply(mother, record['satisfiedWants'])

    def retry(self, state, data, at):
        mother, _ = self.couple(state, data.get('villagerId'), at)
        record = state.get('pregnancies', {}).get(mother['id'], {})
        if record.get('status') != 'failed' or pregnant(mother):
            raise ValueError('A failed conception attempt is required')
        remaining = self.retry_remaining(record, at)
        if remaining:
            spend_gems(state, gem_price(self.world, remaining, 'PregnancySkipRetry'))
            record['retryUnlockedAt'] = at
            touch(state, at)
        return self.inventory_reply(state)

    def design(self, state, data, at, rng):
        mother = actor(state, data.get('villagerId'))
        record = state.get('pregnancies', {}).get(mother['id'], {})
        if record.get('status') != 'pregnant' or not pregnant(mother):
            raise ValueError('Active pregnancy required')
        raw = str(data.get('pregnancyType'))
        prices = {'2': 'gemsForTwins', '7': 'gemsForBoy', '8': 'gemsForGirl', '9': 'gemsForTriplet'}
        if raw != '1' and raw not in prices:
            raise ValueError('Unsupported pregnancy choice')
        if record['designFinalized']:
            if record['kind'] != int(raw):
                raise ValueError('Pregnancy choice already finalized')
            return self.inventory_reply(state)
        if raw != '1':
            spend_gems(state, self.setting(prices[raw]))
            record['children'] = self.children(int(raw), self.places(state, mother['id']), rng)
        record.update(kind=int(raw), designFinalized=True)
        touch(state, at)
        return self.inventory_reply(state)

    def birth_reply(self, state, record, owner):
        native = reserve_ids(state, owner, ())
        villagers = []
        for ident in record['bornChildren']:
            child = actor(state, ident)
            villagers.append({'ID': native[ident], 'Name': child['name'], 'Equipment': child['equipment'],
                              'villagerBaseId': 0 if ordinary_seed(child, self.defs) else child['villagerBaseId'], 'StartAge': 0,
                              'BornAt': child['bornAt'], 'createdAt': child['bornAt'],
                              'Gender': child['gender'], 'Rarity': child['rarity'],
                              'Skills': [{'SkillTypeID': s['skilltypeId'], 'SkillSourceType': s['skillOriginType']}
                                         for s in child['skills']]})
        return {'result': {'villagers': villagers, 'inventory': self.inventory.list_items(state)}}

    def child(self, state, plan, mother, at, index, inherited):
        seed = self.defs.item('villager_starting_variation', plan['seedId'])
        gender = plan['gender']
        area = self.world._area(mother)
        position = {**mother['position'], 'x': float(mother['position']['x']) + 40 * (index + 1),
                    'y': float(mother['position']['y']) + 40}
        child = {'id': plan['id'], 'refId': '', 'name': seed['name'], 'templateType': 'villager_type',
                 'templateId': 4 if gender else 3, 'serverPersisted': True, 'startingArea': area,
                 'villagerBaseId': int(seed['id']), 'birthType': 0, 'specialType': 0, 'energyLevel': 0,
                 'energyTimeStamp': at, 'startAge': 0, 'bornAt': at, 'updatedAt': at,
                 'pregnant': 'false', 'pregnancyTryCount': 0, 'pregnancyStartTime': 0,
                 'gender': gender, 'xp': 0, 'rarity': 0, 'shelterBedId': '', 'position': position,
                 'equipment': seed['equipment'], 'genetics': seed['genetics'], 'relations': [],
                 'skills': [dict(row) for row in inherited], 'wants': [], 'clothing': [],
                 'isCommunityVillager': 'false',
                 'retireAt': 0, 'retireEventID': 0}
        if 'gachaBaseId' in plan:
            chosen = self.defs.item('gachaVillager', plan['gachaBaseId'])
            child.update(name=chosen['name'], villagerBaseId=int(chosen['id']),
                         collectionBaseId=int(chosen['id']), equipment=chosen['equipment'],
                         rarity=max(0, int(chosen['star']) - 1), genetics='',
                         skills=newborn_shields(self.defs, inherited, chosen,
                                               int(self.world.global_values.get('skill_slots_max', 3))))
            collection = state.setdefault('villagerCollection', {})
            collection[chosen['id']] = max(2, int(collection.get(chosen['id'], 0)))
        return child

    def birth(self, state, data, at, owner, *, skip):
        mother = actor(state, data.get('motherVillagerId' if skip else 'VillagerStringID'))
        record = state.get('pregnancies', {}).get(mother['id'], {})
        if not record:
            raise ValueError('No saved pregnancy for this mother')
        if skip and (data.get('fatherVillagerId') != record['fatherId']
                     or data.get('areaId') != self.world._area(mother)):
            raise ValueError('Pregnancy parents and area must match the save')
        if record['status'] == 'born':
            return self.birth_reply(state, record, owner)
        if record['status'] != 'pregnant' or not pregnant(mother):
            raise ValueError('Active pregnancy required')
        remaining = max(0, record['readyAt'] - at)
        if not skip and remaining:
            raise ValueError('Pregnancy is not ready')
        if self.places(state, mother['id']) < len(record['children']):
            raise ValueError('Village population capacity reached')
        father = actor(state, record['fatherId'])
        if 'inheritedSkills' not in record:
            record['inheritedSkills'] = parent_shields(self.defs, mother, father)
        if skip and not record.get('skipReceipt'):
            cost = gem_price(self.world, remaining, 'PregnancySkip')
            spend_gems(state, cost)
            record['skipReceipt'] = {'at': at, 'gemsSpent': cost}
        # Imported saves planned newborns as a raw suffix. Keep their original
        # canonical identity and any native ID already shown in a charm reveal.
        for plan in record['children']:
            if 'id' not in plan:
                plan['id'] = f"Villager_{owner}_{plan['rawId']}"
        reserve_ids(state, owner, [plan['id'] for plan in record['children']])
        parent_ids = {mother['id'], father['id']}
        siblings = [p for p in actors(state) if any(r['villagerId'] in parent_ids and int(r['type']) == 0
                                                   for r in p.get('relations', []))]
        born = []
        for index, plan in enumerate(record['children']):
            child = self.child(state, plan, mother, at, index, record['inheritedSkills'])
            for parent in (mother, father):
                add_relation(child, parent, 0)
                add_relation(parent, child, 1)
            for sibling in siblings + born:
                add_relation(child, sibling, 3)
                add_relation(sibling, child, 3)
            born.append(child)
        state['world']['entities'].extend(born)
        mother.update(pregnant='false', pregnancyStartTime=0, pregnancyTryCount=0, updatedAt=at)
        for parent in (mother, father):
            parent['lastChildBornAt'] = at
        record.update(status='born', bornAt=at, bornChildren=[p['id'] for p in born])
        touch(state, at)
        # Both native actions call BirthModelListener, which needs the newborns
        # and refreshed inventory in one response.
        return self.birth_reply(state, record, owner)

    def operate(self, state, service, data, at, owner, rng):
        if service in WISHES:
            return self.generate(state, at)
        if service == CONCEIVE:
            return self.conceive(state, data, at, rng)
        if service == RETRY:
            return self.retry(state, data, at)
        if service == DESIGN:
            return self.design(state, data, at, rng)
        return self.birth(state, data, at, owner, skip=service == SKIP)

