"""Original coming-of-age inbox and its one-time skill choice."""
from __future__ import annotations

import math
from collections import Counter

from .birth_skills import skill_type
from .native_ids import mappings
from .relationships import actor, actors, touch

CHOOSE_SKILL = 'ClientVillagerService/SetVillagerSkill'
ACK_MESSAGE = 'ClientUserService/HandleUserMessages'
ACK_NOTICE = 'ClientUserService/HandleUserNotification'


class OriginalLifeStages:
    def __init__(self, world):
        self.world = world

    def birthday(self, person):
        age = int(self.world.global_values.get('coming_of_age', 13))
        hours = self.world.global_values.get('hours_per_year')
        if hours is None or not {'startAge', 'bornAt'} <= person.keys():
            return None
        start_age = float(person['startAge'])
        if start_age >= age:
            return None
        return int(person['bornAt']) + math.ceil((age - start_age) * float(hours) * 3600)

    def ready(self, person, at):
        birthday = self.birthday(person)
        if birthday is None or at < birthday:
            return None
        try:
            kind = self.world.current_villager_type(person, at)
        except KeyError:
            return None
        if kind.get('name') == 'Dog Villager' or int(self.world.current_age(person, at)) > 75:
            return None
        return birthday

    @staticmethod
    def identifiers(state, owner):
        outward, _ = mappings(state, owner)
        return {ident: (str(1_000_000_000 + int(native.rsplit('_', 1)[1])),
                        str(2_000_000_000 + int(native.rsplit('_', 1)[1])))
                for ident, native in outward.items()}

    def notices(self, state, owner, at):
        result = []
        ids = None
        for person in actors(state):
            ident = person['id']
            if self.world._area(person) != state.get('areaId', 1) or 'comingOfAgeSkill' in person:
                continue
            birthday = self.ready(person, at)
            if birthday is None:
                continue
            if ids is None:
                ids = self.identifiers(state, owner)
            notice, message = ids[ident]
            body = {'id': notice, 'notificationTypeId': 0, 'createdAt': birthday,
                    'requestStatusTypeId': 1, 'isIncoming': 'false',
                    'data': {'recipient': {'villager': {
                        'id': ident, 'name': person['name'], 'equipment': person.get('equipment', ''),
                        'villagerTypeId': int(self.world.current_villager_type(person, at)['id']),
                        'createdAt': person['bornAt'], 'startingAge': person['startAge'],
                    }}}}
            result.append((person, message, body))
        return result

    def notifications(self, state, owner, at):
        return [body for _, _, body in self.notices(state, owner, at)]

    def messages(self, state, owner, at):
        return [{'id': message, 'messageTypeId': 7, 'data': body}
                for person, message, body in self.notices(state, owner, at)
                if not person.get('comingOfAgeMessageSeen')]

    def available_skills(self, state):
        maximum = int(state['user'].get('maxAreaId', state['areaId']))
        return {int(row['id']) for row in self.world.defs.rows('villager_skill')
                if int(row['id']) > 0 and 1 <= int(row.get('area', 0)) <= maximum}

    def blocked_birthdays(self, state, at):
        for person in actors(state):
            if 'comingOfAgeSkill' in person or not person.get('skills'):
                continue
            birthday = self.ready(person, at)
            if birthday is None:
                continue
            counts = Counter(map(skill_type, person['skills']))
            available = self.available_skills(state)
            if available and min(counts[skill] for skill in available) >= int(self.world.global_value('skill_slots_max')):
                yield person, birthday

    @staticmethod
    def complete(state, person, skill, at):
        person['comingOfAgeSkill'] = skill
        person['comingOfAgeCompletedAt'] = at
        touch(state, at)

    def choose_skill(self, state, data, at):
        person = actor(state, data.get('villagerId'))
        skill = data.get('skillTypeId')
        if type(skill) is not int or skill < 0:
            raise ValueError('A coming-of-age skill identifier is required')
        if 'comingOfAgeSkill' in person:
            if person['comingOfAgeSkill'] != skill:
                raise ValueError('This villager already chose a coming-of-age skill')
            return {}
        if self.ready(person, at) is None:
            raise ValueError('The villager has not reached their coming-of-age birthday')
        if skill:
            definition = self.world.defs.item('villager_skill', skill)
            maximum = int(state['user'].get('maxAreaId', state['areaId']))
            if not 1 <= int(definition['area']) <= maximum:
                raise ValueError('This skill is unavailable in the village')
            ranks = person.get('skills', [])
            counts = Counter(map(skill_type, ranks))
            limit = int(self.world.global_value('skill_slots_max'))
            if counts[skill] >= limit:
                if any(counts[choice] < limit for choice in self.available_skills(state)):
                    raise ValueError('This villager already mastered the chosen skill')
                # Let the client finish the birthday when every available
                # choice is full, retaining the existing ranks.
            else:
                person['skills'] = [*ranks, {'skilltypeId': skill, 'skillOriginType': 0}]
        self.complete(state, person, skill, at)
        return {}

    def acknowledge(self, state, service, data, owner, at):
        """Consume birthday message IDs, returning any IDs for other handlers."""
        ids = self.identifiers(state, owner)
        people = [p for p in actors(state) if self.ready(p, at) is not None]
        if service == ACK_NOTICE:
            requested = str(data.get('userNotificationId'))
            if any(ids[p['id']][0] == requested for p in people):
                # The client also acknowledges when the actor is temporarily
                # absent from its scene. Keep the event available until claimed.
                return None
            return data
        value = data.get('userMessageIds')
        if not isinstance(value, str) or not value or len(value) > 2000:
            return data
        by_message = {ids[p['id']][1]: p for p in people}
        remaining = []
        changed = False
        for ident in map(str.strip, value.split(',')):
            person = by_message.get(ident)
            if person is None:
                remaining.append(ident)
            elif not person.get('comingOfAgeMessageSeen'):
                person['comingOfAgeMessageSeen'] = True
                changed = True
        if changed:
            touch(state, at)
        return {**data, 'userMessageIds': ','.join(remaining)} if remaining else None

