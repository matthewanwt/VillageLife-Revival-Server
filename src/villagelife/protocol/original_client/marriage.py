"""Original proposal, wedding and local NPC move-in contracts."""
from __future__ import annotations

import copy

from .daily import satisfy_wants
from .relationships import actor, actors, add_relation, candidate, free_places, partner, touch

READS = {'ClientUserService/GetUserNotifications',
         'ClientRequestService/GetPaginatedSentRequests',
         'ClientRequestService/GetPaginatedReceivedRequests',
         'ClientVillagerService/GetNeighborVillagers'}
SERVICES = {'ClientRequestService/SendMarriageRequest', 'ClientRelationship/PrepareWedding',
            'ClientNotification/ProcessAcceptedProposal', 'ClientRequestService/DeleteUserRequests',
            'ClientUserService/HandleUserMessages', 'ClientUserService/HandleUserNotification',
            'ClientUser/TrackMarriageAchievement'}
ACTIVE = {'accepted', 'prepared'}


class OriginalMarriageRules:
    def __init__(self, dating):
        self.dating = dating
        self.world = dating.world

    def records(self, state):
        return state.get('npcMarriageRequests', [])

    def pair(self, state, person, target_id, at):
        target = self.dating.npc(state, target_id)
        minimum = self.dating.setting('minAgeForDating')
        maximum = self.dating.setting('maxAgeForMarriage')
        if (person['gender'] == target['gender'] or partner(person, 4) != target['id']
                or partner(target, 4) != person['id'] or partner(person, 2) or partner(target, 2)
                or any(not minimum <= int(self.world.current_age(p, at)) <= maximum
                       for p in (person, target))):
            raise ValueError('An eligible reciprocal dating pair is required')
        return target

    def free_places(self, state):
        return free_places(state, self.world)

    def wish_available(self, state, person, at):
        ident = person['id']
        target = partner(person, 4)
        if target is None or self.free_places(state) < 1:
            return False
        if any(r['localVillagerId'] == ident and r['status'] in ACTIVE for r in self.records(state)):
            return False
        delay = self.dating.setting('marriage_want_delay')
        if not any(r['status'] == 'accepted' and r['localVillagerId'] == ident
                   and r['candidateId'] == target and at - r['acceptedAt'] >= delay
                   for r in state.get('npcDateRequests', [])):
            return False
        try:
            return self.pair(state, person, target, at)['rarity'] <= int(person.get('rarity', 0))
        except (PermissionError, ValueError):
            return False

    def record(self, state, data):
        ids = {str(data[k]) for k in ('RequestID', 'RequestStringID', 'userRequestId')
               if k in data and str(data[k]) not in {'', '0', '-1'}}
        if len(ids) != 1:
            raise ValueError('One matching marriage request identifier required')
        for record in self.records(state):
            if record['id'] in ids:
                return record
        raise PermissionError('Unknown marriage request in this village')

    def villager(self, person, at):
        return {'id': person['id'], 'name': person['name'], 'equipment': person['equipment'],
                'villagerTypeId': int(self.world.current_villager_type(person, at)['id']),
                'pregnant': int(str(person.get('pregnant', 'false')).lower() in {'true', '1'}),
                'xp': int(person.get('xp', 0))}

    def wire(self, state, record, at, owner):
        person = actor(state, record['localVillagerId'])
        sender = {'user': {'id': owner, 'name': state['user'].get('name', 'Your village'),
                           'firstname': '', 'IsTablet': 'true', 'Locale': 'en'},
                  'villager': {**self.villager(person, at), 'rarity': person.get('rarity', 0)}}
        return {'id': int(record['id']), 'userRequestId': record['id'], 'requestTypeId': 1,
                'requestStatusTypeId': int(at >= record['readyAt']), 'createdAt': record['createdAt'],
                'isIncoming': 'false', 'isCommunityVillager': 1, 'sender': sender,
                'recipient': candidate(record['npcSnapshot'])}

    @staticmethod
    def notification_id(record):
        return str(4000000 + int(record['id']))

    @staticmethod
    def message_id(record):
        return str(8000000 + int(record['id']))

    def notice(self, state, record, at, owner):
        return {'id': self.notification_id(record), 'notificationTypeId': 12,
                'createdAt': record['readyAt'], 'data': self.wire(state, record, at, owner)}

    def ready(self, state, at):
        return [r for r in self.records(state) if r['status'] in ACTIVE and at >= r['readyAt']
                and not r.get('notificationHandled')]

    def messages(self, state, at, owner):
        return [{'id': self.message_id(r), 'messageTypeId': 7, 'data': self.notice(state, r, at, owner)}
                for r in self.ready(state, at) if not r.get('messageHandled')]

    def propose(self, state, data, at, owner):
        person = actor(state, data.get('senderVillagerId'))
        target_id = data.get('recipientVillagerId')
        for record in self.records(state):
            if (record['localVillagerId'] == person['id'] and record['candidateId'] == target_id
                    and record['status'] in ACTIVE | {'completed'}):
                if str(data.get('recipientUserId')) != record['guestUserId']:
                    raise PermissionError('Wrong NPC village owner')
                return {'userRequest': self.wire(state, record, at, owner)}
        target = self.pair(state, person, target_id, at)
        if str(data.get('recipientUserId')) != target['ownerUserId']:
            raise PermissionError('Wrong NPC village owner')
        local_rarity, npc_rarity = int(person.get('rarity', 0)), int(target['rarity'])
        if str(data.get('stars')) not in {str(local_rarity), str(npc_rarity)}:
            raise ValueError('Wedding stars must match a saved partner')
        if npc_rarity > local_rarity:
            raise ValueError('Weddings hosted by a higher-star NPC village are unavailable')
        if self.free_places(state) < 1:
            raise ValueError('Village population capacity reached')
        ident = int(state.get('nextNpcMarriageRequestId', 2000000))
        state['nextNpcMarriageRequestId'] = ident + 1
        record = {'id': str(ident), 'localVillagerId': person['id'], 'candidateId': target_id,
                  'npcSnapshot': copy.deepcopy(target), 'status': 'accepted', 'createdAt': at,
                  'readyAt': at + self.dating.setting('date_return_time_seconds'),
                  'guestUserId': target['ownerUserId'], 'hidden': False}
        state.setdefault('npcMarriageRequests', []).append(record)
        satisfy_wants(state, {person['id']}, 5, at)
        touch(state, at)
        return {'userRequest': self.wire(state, record, at, owner)}

    def prepare(self, state, data, at, owner):
        record = self.record(state, data)
        if record['status'] not in ACTIVE | {'completed'} or at < record['readyAt']:
            raise ValueError('Marriage request is not ready')
        person = actor(state, record['localVillagerId'])
        target = record['npcSnapshot']
        if record['status'] != 'completed':
            target = self.pair(state, person, record['candidateId'], at)
            if self.free_places(state) < 1:
                raise ValueError('Village population capacity reached')
        if record['status'] == 'accepted':
            record.update(status='prepared', preparedAt=at)
            touch(state, at)
        bride, groom = (person, target) if int(person['gender']) else (target, person)
        def wedding_actor(p):
            villager = self.villager(p, at)
            return {'Name': villager['name'], 'VillagerType': villager['villagerTypeId'],
                    'IsPregnant': 'true' if villager['pregnant'] else 'false',
                    'Xp': villager['xp'], 'Equipment': villager['equipment']}
        area = self.world._area(person)
        relatives = {r['villagerId'] for r in person.get('relations', [])}
        guests = [guest for guest in actors(state) if guest['id'] not in {person['id'], target['id']}
                  and self.world._area(guest) == area
                  and self.world.current_age(guest, at) >= 4
                  and self.world.current_villager_type(guest, at).get('name') != 'Dog Villager']
        guests.sort(key=lambda guest: guest['id'] not in relatives)
        cap = int(self.world.global_values.get('MarriageCongregationCap', 10))
        return {'result': {'Bride': wedding_actor(bride), 'Groom': wedding_actor(groom),
                           'Congregation': [wedding_actor(g) for g in guests[:cap]], 'NeighbourCongregation': [],
                           'IsUserBride': 'true' if int(person['gender']) else 'false', 'IsUserHost': 'true'},
                'data': {'users': {'host': {'id': owner, 'name': 'Your village'},
                                   'guest': {'id': record['guestUserId'], 'name': 'Local NPC Village'}},
                         'villagers': {'host': {'id': person['id'], 'name': person['name']},
                                       'guest': {'id': record['candidateId'], 'name': target['name']}}}}

    def complete(self, state, data, at, owner):
        record = self.record(state, data)
        if record['status'] == 'completed':
            return {}
        if record['status'] != 'prepared':
            raise ValueError('Wedding must be prepared before completion')
        person = actor(state, record['localVillagerId'])
        target = self.pair(state, person, record['candidateId'], at)
        if self.free_places(state) < 1:
            raise ValueError('Village population capacity reached')
        moved = {key: copy.deepcopy(target[key]) for key in
                 ('id', 'name', 'equipment', 'genetics', 'startAge', 'bornAt', 'gender', 'rarity', 'skills')}
        kind = self.world.current_villager_type(target, at)
        moved.update(refId='', templateType='villager_type', templateId=int(kind['id']),
                     villagerBaseId=int(target['seedId']), startingArea=self.world._area(person),
                     serverPersisted=True, ownerUserId=owner, originNpcUserId=target['ownerUserId'],
                     birthType=0, specialType=0, energyLevel=int(kind['maxEnergy']), energyTimeStamp=at,
                     updatedAt=at, pregnant='false', pregnancyTryCount=0, pregnancyStartTime=0,
                     xp=0, shelterBedId='', relations=[], wants=[], clothing=[],
                     isCommunityVillager='false', retireAt=0, retireEventID=0, marriedAt=at,
                     position={**person['position'], 'x': float(person['position']['x']) + 40})
        person['relations'] = [r for r in person['relations'] if int(r['type']) != 4]
        person['marriedAt'] = at
        add_relation(person, moved, 2)
        add_relation(moved, person, 2)
        state['world']['entities'].append(moved)
        state['externalVillagers'].pop(target['id'], None)
        state['npcDatingPool'] = [p for p in state['npcDatingPool'] if p['id'] != target['id']]
        for date in state.get('npcDateRequests', []):
            if date['candidateId'] == target['id'] and date['status'] == 'accepted':
                date['status'] = 'married'
        record.update(status='completed', completedAt=at, hidden=True, movedVillagerId=moved['id'])
        satisfy_wants(state, {person['id']}, 5, at)
        touch(state, at)
        return {}

    def read(self, state, service, data, at, owner):
        method = service.rsplit('/', 1)[1]
        if method == 'GetUserNotifications':
            return {'userNotifications': [*copy.deepcopy(state.get('notifications', [])),
                                           *(self.notice(state, r, at, owner) for r in self.ready(state, at))]}
        if method == 'GetNeighborVillagers':
            ident = str(data.get('neighborUserId'))
            people = actors(state) if ident == owner else [
                r['npcSnapshot'] for r in self.records(state) if r['guestUserId'] == ident
                and r['status'] in {'prepared', 'completed'}]
            if not people and ident != owner:
                raise PermissionError('Only the prepared private NPC wedding village is available')
            return {'villagers': [self.villager(p, at) for p in people]}
        key = 'sentRequests' if method == 'GetPaginatedSentRequests' else 'receivedRequests'
        if state.get(key):
            raise NotImplementedError('Imported social request pagination requires verification')
        count = data.get('count', 500)
        if type(count) is not int or not 1 <= count <= 500:
            raise ValueError('Invalid request page size')
        records = [r for r in self.records(state) if not r['hidden'] and r['status'] in ACTIVE] if key == 'sentRequests' else []
        return {'userRequests': [self.wire(state, r, at, owner) for r in records[:count]]}

    def operate(self, state, service, data, at, owner):
        method = service.rsplit('/', 1)[1]
        handlers = {'SendMarriageRequest': self.propose, 'PrepareWedding': self.prepare,
                    'ProcessAcceptedProposal': self.complete}
        if method in handlers:
            return handlers[method](state, data, at, owner)
        if method == 'TrackMarriageAchievement':
            return {}
        if method == 'HandleUserNotification':
            value = str(data.get('userNotificationId'))
            if value == '0':
                return {}
            ids, id_for, flag = [value], self.notification_id, 'notificationHandled'
        else:
            key = 'userMessageIds' if method == 'HandleUserMessages' else 'userRequestIds'
            value = data.get(key)
            if not isinstance(value, str) or not value or len(value) > 2000:
                raise ValueError('Original comma-separated IDs required')
            ids = [ident.strip() for ident in value.split(',')]
            id_for = self.message_id if method == 'HandleUserMessages' else lambda r: r['id']
            flag = 'messageHandled' if method == 'HandleUserMessages' else 'hidden'
        available = {id_for(r): r for r in self.records(state)}
        if any(ident not in available for ident in ids):
            raise PermissionError('Unknown private wedding record')
        for ident in set(ids):
            if not available[ident].get(flag):
                available[ident][flag] = True
                touch(state, at)
        return {}

