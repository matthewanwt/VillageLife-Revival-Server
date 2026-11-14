"""Local NPC dating using the original catalogue and community inbox."""
from __future__ import annotations

import copy
import hashlib
import json

from .daily import satisfy_wants
from .native_ids import mappings
from .randomness import randbelow
from .world import OriginalWorldRules

SERVICES = {
    'ClientVillager/GetCommunityVillagers', 'ClientVillagerService/OptIntoCommunity',
    'ClientRequest/AcceptDatingRequest', 'ClientVillagerService/GetPartnerVillager',
    'ClientVillagerService/Breakup', 'ClientWant/GenerateRelationshipWants',
    'ClientWant/SatisfyRelationshipWant', 'ClientDeviceService/Push',
    'ClientVillager/CommunityDateReceived',
}
COMMUNITY_SERVICES = {'CharacterRequest/Create', 'CharacterRequest/GetReceived',
                      'CharacterRequest/Delete'}


def actors(state):
    return [p for p in state['world']['entities'] if p.get('templateType') == 'villager_type']


def actor(state, ident):
    for person in actors(state):
        if person['id'] == ident:
            return person
    raise ValueError('Unknown villager in this village')


def partner(person, group):
    return next((r['villagerId'] for r in person.get('relations', []) if int(r['type']) == group), None)


def add_relation(person, other, group):
    link = {'villagerId': other['id'], 'type': group}
    relations = person.setdefault('relations', [])
    if link not in relations:
        relations.append(link)


def free_places(state, world, excluding=None):
    population = sum(world.defs.item('villager_type', p['templateId']).get('name') != 'Dog Villager'
                     for p in actors(state))
    reserved = sum(len(p.get('children', [])) or 1 for ident, p in state.get('pregnancies', {}).items()
                   if ident != excluding and p.get('status') == 'pregnant')
    return int(state['user']['populationCap']) - population - reserved


def touch(state, at):
    state['revision'] = int(state.get('revision', 0)) + 1
    state['updatedAt'] = at


def chance(local, target):
    difference = int(target.get('rarity', 0)) - int(local.get('rarity', 0))
    return 100 if difference < 0 else {0: 50, 1: 25}.get(difference, 0)


def candidate(person):
    owner = person['ownerUserId']
    user = {'id': owner, 'name': 'Local NPC Village', 'firstname': 'Local NPC',
            'identifier': {'pId': owner, 'fbId': '0'}, 'IsTablet': 'true', 'Locale': 'en'}
    villager = {k: copy.deepcopy(person[k]) for k in
                ('id', 'name', 'equipment', 'startAge', 'bornAt', 'gender', 'skills')}
    villager.update(villagerTypeId=person['templateId'], Rarity=person['rarity'],
                    rarity=person['rarity'], pregnant=0)
    return {'user': user, 'villager': villager, 'skills': copy.deepcopy(person['skills'])}


class OriginalDatingRules:
    def __init__(self, world: OriginalWorldRules, wants):
        self.world = world
        self.wants = wants

    def setting(self, key):
        return int(self.world.global_value(key))

    def dateable(self, person, at):
        kind = self.world.current_villager_type(person, at)
        return (kind.get('isDateable') == '1' and partner(person, 2) is None
                and partner(person, 4) is None)

    @staticmethod
    def npc(state, ident):
        for person in state.get('npcDatingPool', []):
            if person['id'] == ident and person.get('ownerKind') == 'npc':
                return person
        raise PermissionError('Unknown private NPC candidate')

    def active(self, request, at):
        return request['status'] == 'pending' and at - request['createdAt'] < self.setting('communityDatesExpiry')

    def available(self, person, at):
        return self.dateable(person, at) and at - person['createdAt'] < self.setting('communityDatesExpiry')

    def npc_skills(self, state, rng):
        draw = randbelow(rng, 100)
        rarity = 2 if draw < 2 else 1 if draw < 14 else 0
        available = [int(r['id']) for r in self.world.defs.rows('villager_skill')
                     if r['id'] != '0' and int(r.get('area', 0)) <= int(state.get('areaId', 1))]
        if not available or (rarity == 0 and randbelow(rng, 100) >= 15):
            return rarity, []
        result = []
        for _ in range(min(len(available), rarity + 1)):
            skill = available.pop(randbelow(rng, len(available)))
            result.extend({'skilltypeId': skill, 'skillOriginType': 0} for _ in range(rarity + 1))
        return rarity, result

    def catalogue(self, state, data, at, owner, rng):
        gender = str(data.get('Gender'))
        if gender not in {'0', '1'}:
            raise ValueError('Original Gender 0 or 1 required')
        gender = int(gender)
        old_pool = state.get('npcDatingPool', [])
        pending = {r['candidateId'] for r in state.get('npcDateRequests', []) if self.active(r, at)}
        pool = [p for p in old_pool if p['relations'] or p['id'] in pending or self.available(p, at)]
        count = self.setting('communityDatesAvailable')
        slots = count - sum(p['gender'] == gender and self.available(p, at) for p in pool)
        seeds = [r for r in self.world.defs.rows('villager_starting_variation')
                 if r.get('SpecialType', '0') == '0' and int(r['Gender']) == gender
                 and 18 <= int(r['startAge']) <= 39 and r.get('isPregnant', '0') == '0']
        serial = int(state.get('nextNpcSerial', 1))
        for _ in range(max(0, slots)):
            if not seeds:
                raise ValueError('Missing original adult NPC appearances')
            seed = seeds[randbelow(rng, len(seeds))]
            digest = hashlib.sha256(f'{owner}:npc:{serial}'.encode()).hexdigest()
            npc_owner = str(800000000000000 + int(digest[:12], 16))
            rarity, skills = self.npc_skills(state, rng)
            pool.append({'id': f'Villager_{npc_owner}_{serial}', 'ownerUserId': npc_owner,
                         'ownerKind': 'npc', 'seedId': seed['id'], 'name': seed['name'],
                         'equipment': seed['equipment'], 'genetics': seed['genetics'],
                         'templateId': int(seed['villagerType']), 'startAge': int(seed['startAge']),
                         'bornAt': at, 'gender': gender, 'rarity': rarity, 'skills': skills,
                         'relations': [], 'pregnant': 'false', 'createdAt': at})
            serial += 1
        if pool != old_pool:
            state['npcDatingPool'] = pool
            state['nextNpcSerial'] = serial
            touch(state, at)
        return {'result': [{'IsTablet': 'true', 'Locale': 'en',
                            'data': json.dumps(candidate(p), separators=(',', ':'))}
                           for p in pool if p['gender'] == gender and self.available(p, at)][:count]}

    def create(self, state, data, at, owner, rng):
        owners, ids = data.get('ForUserIds'), data.get('CharacterIds')
        if (not isinstance(owners, list) or not isinstance(ids, list)
                or len(owners) != len(ids) or not 1 <= len(ids) <= 25):
            raise ValueError('Matching original recipient lists required')
        _, inward = mappings(state, owner)
        local = actor(state, inward.get(str(data.get('FriendCharacterId'))))
        if not local.get('communityOptIn') or not self.dateable(local, at):
            raise ValueError('An opted-in single adult is required')
        targets = [self.npc(state, f'Villager_{user_id}_{suffix}') for user_id, suffix in zip(owners, ids)]
        if any(not self.available(p, at) or p['gender'] == local['gender'] for p in targets):
            raise ValueError('Candidate is not eligible for this date')
        records = state.setdefault('npcDateRequests', [])
        recent = {r['candidateId'] for r in records if r['localVillagerId'] == local['id']
                  and (self.active(r, at) or at < r['readyAt'])}
        for target in targets:
            if target['id'] in recent:
                continue
            recent.add(target['id'])
            ident = int(state.get('nextNpcDateRequestId', 1000000))
            state['nextNpcDateRequestId'] = ident + 1
            replied = randbelow(rng, 100) < chance(local, target)
            records.append({'id': str(ident), 'localVillagerId': local['id'],
                            'candidateId': target['id'], 'status': 'pending' if replied else 'declined',
                            'createdAt': at, 'readyAt': at + self.setting('date_return_time_seconds')})
            touch(state, at)
        return {}

    def inbox(self, state, at, owner):
        outward, _ = mappings(state, owner)
        results = []
        for record in state.get('npcDateRequests', []):
            if not self.active(record, at) or at < record['readyAt']:
                continue
            local = actor(state, record['localVillagerId'])
            target = self.npc(state, record['candidateId'])
            if not self.dateable(local, at) or not self.dateable(target, at):
                continue
            appearance = {**candidate(target)['villager'], 'stars': target['rarity'] + 1,
                          'SenderUserName': 'Local NPC Village'}
            results.append({'ID': record['id'], 'ByUserID': target['ownerUserId'],
                            'ForUserID': str(owner), 'CharacterID': outward[local['id']].rsplit('_', 1)[1],
                            'FriendCharacterID': target['id'].rsplit('_', 1)[1],
                            'FriendCharacterAppearance': json.dumps(appearance, separators=(',', ':')),
                            'createdAt': record['readyAt']})
        return {'CharacterRequests': results}

    @staticmethod
    def request(state, ident):
        for record in state.get('npcDateRequests', []):
            if record['id'] == str(ident):
                return record
        raise PermissionError('Unknown date request in this village')

    def accept(self, state, data, at):
        record = self.request(state, data.get('RequestID'))
        if record['status'] in {'accepted', 'married'}:
            return {}
        if not self.active(record, at) or at < record['readyAt']:
            raise ValueError('Date request is not available')
        local = actor(state, record['localVillagerId'])
        target = self.npc(state, record['candidateId'])
        if not self.dateable(local, at) or not self.dateable(target, at):
            raise ValueError('Both villagers must still be eligible')
        add_relation(local, target, 4)
        add_relation(target, local, 4)
        state.setdefault('externalVillagers', {})[target['id']] = copy.deepcopy(target)
        record.update(status='accepted', acceptedAt=at)
        for other in state['npcDateRequests']:
            if other['status'] == 'pending' and (other['localVillagerId'] == local['id']
                                                 or other['candidateId'] == target['id']):
                other['status'] = 'superseded'
        satisfy_wants(state, {local['id']}, 5, at)
        touch(state, at)
        return {}

    def remove(self, state, data, at):
        ids = data.get('CharacterRequestIds')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 100:
            raise ValueError('CharacterRequestIds list required')
        for record in [self.request(state, ident) for ident in ids]:
            if record['status'] == 'pending':
                record['status'] = 'rejected'
                touch(state, at)
        return {}

    def breakup(self, state, data, at):
        local = actor(state, data.get('villagerId'))
        target = self.npc(state, data.get('partnerVillagerId'))
        if partner(local, 4) != target['id'] or partner(target, 4) != local['id']:
            raise ValueError('A reciprocal date is required')
        for person in (local, target):
            person['relations'] = [r for r in person['relations'] if int(r['type']) != 4]
        state['externalVillagers'].pop(target['id'], None)
        for record in state.get('npcDateRequests', []):
            if record['candidateId'] == target['id'] and record['status'] == 'accepted':
                record.update(status='broken_up', brokenUpAt=at)
        for record in state.get('npcMarriageRequests', []):
            if record['candidateId'] == target['id'] and record['status'] in {'accepted', 'prepared'}:
                record.update(status='cancelled', hidden=True)
        satisfy_wants(state, {local['id']}, 5, at)
        touch(state, at)
        return {}

    def generate(self, state, at, marriage):
        wishes = state.setdefault('wants', [])
        active = {w['VillagerStringID'] for w in wishes if w.get('wantableCategoryType') == 5}
        interval = int(self.world.global_values.get('WantIntervalRelationship', 28800))
        changed = False
        for person in actors(state):
            ident = person['id']
            if ident in active or self.world._area(person) != state['areaId']:
                continue
            if at - state.get('needSatisfiedAt', {}).get(f'{ident}:5', -interval) < interval:
                continue
            material = 340
            if not self.dateable(person, at):
                if not marriage.wish_available(state, person, at):
                    continue
                material = 342
            self.wants._append(state, person, 5, material, at)
            changed = True
        if changed:
            touch(state, at)
        return {'result': copy.deepcopy(wishes)}

    def operate(self, state, service, data, at, owner, rng, marriage):
        method = service.rsplit('/', 1)[1]
        if method == 'GetCommunityVillagers':
            return self.catalogue(state, data, at, owner, rng)
        if method == 'AcceptDatingRequest':
            return self.accept(state, data, at)
        if method == 'Breakup':
            return self.breakup(state, data, at)
        if method == 'GenerateRelationshipWants':
            return self.generate(state, at, marriage)
        if method == 'SatisfyRelationshipWant':
            person = actor(state, data.get('VillagerStringID'))
            removed = satisfy_wants(state, {person['id']}, 5, at)
            if removed:
                touch(state, at)
            return {'result': {'SatisfiedWantModels': removed}}
        if method in {'Push', 'CommunityDateReceived'}:
            field = 'UserIDs' if method == 'Push' else 'VillagerIDs'
            ids = data.get(field)
            allowed = {p['ownerUserId'] if method == 'Push' else p['id'].rsplit('_', 1)[1]
                       for p in state.get('npcDatingPool', [])}
            if not isinstance(ids, list) or not ids or any(str(i) not in allowed for i in ids):
                raise NotImplementedError('External player notifications are unavailable')
            return {}
        person = actor(state, data.get('villagerId'))
        if method == 'GetPartnerVillager':
            return candidate(self.npc(state, partner(person, 4)))
        if not self.dateable(person, at):
            raise ValueError('Villager is not eligible to date')
        if not person.get('communityOptIn'):
            person['communityOptIn'] = True
            touch(state, at)
        return {}


