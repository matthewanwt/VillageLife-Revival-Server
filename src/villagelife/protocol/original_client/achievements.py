"""Reconstructed original-client achievements from persistent village state.

The 2.11 server rules are not present in this repository or its history.  This
module therefore reconstructs only progress that can be read with confidence
from the save: marriages, births, population, skill mastery, village age,
retirement, travel, decor, concurrent work, level and the dating milestones.
Achievements whose original counters depend on event history that this server
does not yet retain stay at zero instead of being guessed.
"""
from __future__ import annotations

from collections import Counter
from functools import cached_property

from villagelife.persistence.history import active_work

from .birth_skills import skill_type
from .catalog import OriginalDefinitions
from .world import OriginalWorldRules

SERVICES = {
    'ClientAchievement/GetUserAchievements',
    'ClientAchievement/GetUnReceievedUserGameAchievements',
    'ClientAchievement/MarkAchievementAsViewed',
    'ClientAchievement/CollectUserGameAchievementReward',
}

GEM_MATERIAL = '323'

# Only achievements whose progress is directly readable from the durable save.
# The remaining live achievements keep their recorded progress (initially zero)
# until their original event history is available.
SKILL_ACHIEVEMENTS = {5: 2, 6: 3, 7: 6, 8: 7, 9: 8, 10: 9}
WORK_ACHIEVEMENTS = {26: '4', 27: '8', 28: '9', 31: '1'}


class OriginalAchievementRules:
    def __init__(self, definitions: OriginalDefinitions):
        self.defs = definitions
        self.world = OriginalWorldRules(definitions)

    @cached_property
    def definitions(self) -> list[dict]:
        return [row for row in self.defs.rows('gameAchievements')
                if str(row.get('live', '0')) == '1']

    @staticmethod
    def _thresholds(row: dict) -> tuple[int, int, int]:
        result = []
        for index in (1, 2, 3):
            try:
                result.append(int(row.get(f'itemQuantity{index}', 0) or 0))
            except (TypeError, ValueError):
                result.append(0)
        return tuple(result)

    @staticmethod
    def _rewards(row: dict) -> tuple[int, int, int]:
        result = []
        for index in (1, 2, 3):
            try:
                result.append(max(0, int(row.get(f'gemReward{index}', 0) or 0)))
            except (TypeError, ValueError):
                result.append(0)
        return tuple(result)

    def definition(self, ident: int) -> dict:
        row = next((value for value in self.definitions
                    if str(value.get('id')) == str(ident)), None)
        if row is None:
            raise ValueError('Unknown achievement in this village')
        return row

    @staticmethod
    def _people(state: dict) -> list[dict]:
        return [entity for entity in state.get('world', {}).get('entities', [])
                if entity.get('templateType') == 'villager_type']

    @classmethod
    def _all_people(cls, state: dict) -> list[dict]:
        people = {person.get('id'): person for person in cls._people(state)}
        for person in state.get('retiredVillagers', {}).values():
            if isinstance(person, dict):
                people.setdefault(person.get('id'), person)
        return list(people.values())

    @staticmethod
    def _area(entity: dict) -> int:
        try:
            return int(entity.get('position', {}).get('areaId', 1) or 1)
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _integer(value, default: int = 0) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default

    def _marriages(self, state: dict) -> int:
        completed = sum(1 for record in state.get('npcMarriageRequests', [])
                        if isinstance(record, dict)
                        and record.get('status') == 'completed')
        stamps = {self._integer(person.get('marriedAt'))
                  for person in self._all_people(state)
                  if self._integer(person.get('marriedAt')) > 0}
        return max(completed, len(stamps))

    def _births(self, state: dict) -> int:
        created = self._integer(state.get('createdAt'))
        born = set()
        for person in self._all_people(state):
            born_at = self._integer(person.get('bornAt'))
            if (born_at > created and self._integer(person.get('startAge')) == 0
                    and person.get('id')):
                born.add(person['id'])
        return len(born)

    def _masters(self, people: list[dict], limit: int) -> dict[int, int]:
        counts = Counter()
        for person in people:
            ranks = Counter(skill_type(skill) for skill in person.get('skills', []))
            for ident, skill in SKILL_ACHIEVEMENTS.items():
                if ranks[skill] >= limit:
                    counts[ident] += 1
        return counts

    def _years(self, state: dict, now: int) -> int:
        created = self._integer(state.get('createdAt'))
        if created <= 0:
            return 0
        hours = self.world.global_values.get('hours_per_year')
        try:
            seconds = int(float(hours) * 3600)
        except (TypeError, ValueError):
            return 0
        if seconds <= 0:
            return 0
        return max(0, (now - created) // seconds)

    def _outfits(self, people: list[dict]) -> int:
        outfits = set()
        for person in people:
            for item in person.get('clothing', []):
                if isinstance(item, dict):
                    ident = item.get('clothingSetId', item.get('clothingSetID',
                                   item.get('id', item.get('clothingItemId'))))
                else:
                    ident = item
                if ident not in (None, '', 0, '0'):
                    outfits.add(str(ident))
        return len(outfits)

    def _wayfarers(self, people: list[dict]) -> int:
        moved = 0
        for person in people:
            area = self._area(person)
            start = self._integer(person.get('startingArea'), area)
            if area > start:
                moved += 1
        return moved

    @staticmethod
    def _decor(state: dict) -> int:
        return sum(1 for entity in state.get('world', {}).get('entities', [])
                   if entity.get('templateType') == 'decor_item'
                   and entity.get('localCreated'))

    @staticmethod
    def _completed(state: dict, key: str) -> int:
        value = state.get(key)
        return len(value) if isinstance(value, (dict, list)) else 0

    @staticmethod
    def _concurrent(state: dict, family: str) -> int:
        return sum(1 for job in active_work(state)
                   if isinstance(job, dict) and job.get('status') == 'working'
                   and str(job.get('family')) == family)

    @staticmethod
    def _level(state: dict) -> int:
        user = state.get('user') or {}
        return max(0, OriginalAchievementRules._integer(
            user.get('userLevelID', user.get('userLevel', 0))))

    @staticmethod
    def _love(state: dict) -> int:
        progress = 0
        if state.get('npcDateRequests'):
            progress = 1
        if state.get('npcMarriageRequests'):
            progress = 2
        if any(isinstance(record, dict) and record.get('status') == 'completed'
               for record in state.get('npcMarriageRequests', [])):
            progress = 3
        return progress

    def _derived(self, state: dict, now: int) -> dict[int, int]:
        people = self._all_people(state)
        try:
            limit = int(self.world.global_values.get('skill_slots_max', 3))
        except (TypeError, ValueError):
            limit = 3
        derived = {
            1: self._marriages(state),
            2: self._births(state),
            3: len(self._people(state)),
            4: self._completed(state, 'completedQuests'),
            13: self._years(state, now),
            14: self._outfits(people),
            15: len(state.get('retiredVillagers', {})),
            16: self._wayfarers(people),
            23: self._completed(state, 'funReceipts'),
            24: self._decor(state),
            33: self._level(state),
            35: self._love(state),
        }
        derived.update(self._masters(people, max(1, limit)))
        for ident, family in WORK_ACHIEVEMENTS.items():
            derived[ident] = self._concurrent(state, family)
        return derived

    @staticmethod
    def _record(state: dict, ident: str) -> dict:
        records = state.setdefault('achievements', {})
        return records.setdefault(ident, {})

    @staticmethod
    def _level_for(progress: int, thresholds: tuple[int, int, int]) -> int:
        return sum(1 for threshold in thresholds if threshold > 0 and progress >= threshold)

    def sync(self, state: dict, now: int, *, persist: bool = True,
             served: bool = False) -> list[dict]:
        """Return wire records and, when requested, persist monotonic progress.

        ``served`` marks a response to the achievement list. The original client
        acknowledges new tiers with a separate call; if that acknowledgement is
        lost, a tier that has already been listed once is treated as seen so the
        same toast cannot pop on every menu open or area change.
        """
        derived = self._derived(state, now)
        stored_records = state.get('achievements') or {}
        updates = {}
        records = []
        for row in self.definitions:
            ident = str(row.get('id'))
            if not ident:
                continue
            number = int(ident)
            thresholds = self._thresholds(row)
            stored = stored_records.get(ident) or {}
            old_progress = self._integer(stored.get('progress'))
            old_level = self._integer(stored.get('levelAchieved'))
            old_collected = self._integer(stored.get('levelRewardCollected'))
            old_viewed = self._integer(stored.get('viewed'))
            old_served = self._integer(stored.get('servedLevel'))
            progress = max(old_progress, derived.get(number, 0))
            level = max(old_level, self._level_for(progress, thresholds))
            viewed = old_viewed
            if level > old_level:
                # A newly reached level has not been shown yet.
                viewed = min(old_viewed, old_level)
            if served and level <= old_served and level > viewed:
                # This tier was already listed once; do not repeat the toast.
                viewed = level
            served_level = max(old_served, level) if served else old_served
            record = {
                'GameAchievementId': number,
                'UserGameAchievementId': ident,
                # The original per-user record id is not documented; the client
                # reads one of these aliases when it posts a view/claim request.
                'Id': ident,
                'UserGameAchievementID': ident,
                'UserAchievementId': ident,
                'GameAchievementUserId': ident,
                'UserGameAchievementsId': ident,
                'ItemQuantity': progress,
                'LevelAchieved': level,
                'LevelRewardCollected': old_collected,
                'IsViewed': 1 if level == 0 or viewed >= level else 0,
            }
            records.append(record)
            if progress or level or old_collected or viewed or served_level:
                updates[ident] = {'progress': progress, 'levelAchieved': level,
                                  'levelRewardCollected': old_collected,
                                  'viewed': viewed, 'servedLevel': served_level}
        if persist:
            merged = dict(stored_records)
            merged.update(updates)
            if merged != stored_records:
                state['achievements'] = merged
                state['revision'] = int(state.get('revision', 0)) + 1
                state.setdefault('rules', {})['achievements'] = {
                    'evidence': 'authored gameAchievements thresholds and rewards; '
                                'progress derived from durable village state',
                    'status': 'reconstruction; event-history-only achievements remain '
                              'at zero until their events are recorded',
                }
        return records

    def observe(self, state: dict, now: int) -> None:
        """Persist newly reached levels during unrelated gameplay mutations."""
        try:
            self.sync(state, now)
        except (KeyError, ValueError, TypeError, AttributeError):
            # Achievement reconstruction must never break a gameplay action.
            return

    @staticmethod
    def _candidate(data: dict) -> str | None:
        for key in ('userGameAchievementId', 'UserGameAchievementId',
                    'UserGameAchievementID', 'UserAchievementId',
                    'GameAchievementUserId', 'UserGameAchievementsId',
                    'gameAchievementId', 'GameAchievementId', 'Id', 'id'):
            value = data.get(key)
            if value is None or value == '':
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    def _ident(self, data: dict) -> int:
        """Resolve the achievement from the id the client echoes back.

        The client posts ``userGameAchievementId`` as a string copy of the
        record it was given, so that value is our own decimal achievement id.
        """
        text = self._candidate(data)
        if text is None:
            raise ValueError('Achievement identifier required')
        if not text.isdigit():
            raise ValueError('Achievement identifier is not numeric')
        ident = int(text)
        self.definition(ident)
        return ident

    def _gems(self, state: dict) -> int:
        try:
            return int(state.get('inventory', {}).get(GEM_MATERIAL, 0))
        except (TypeError, ValueError):
            return 0

    def _collect(self, state: dict, ident: int, now: int,
                 inventory: object) -> dict:
        row = self.definition(ident)
        rewards = self._rewards(row)
        self.sync(state, now)
        record = self._record(state, str(ident))
        level = self._integer(record.get('levelAchieved'))
        collected = self._integer(record.get('levelRewardCollected'))
        gems = 0
        if level > collected:
            gems = sum(rewards[collected:level])
            state.setdefault('inventory', {})[GEM_MATERIAL] = self._gems(state) + gems
            record['levelRewardCollected'] = level
            record['viewed'] = max(self._integer(record.get('viewed')), level)
            record['servedLevel'] = max(self._integer(record.get('servedLevel')), level)
            state['revision'] = int(state.get('revision', 0)) + 1
        items = inventory.list_items(state)
        text = str(ident)
        # The client's collect listener reads the updated record from
        # ``result.UserGameAchievement`` and refreshes the HUD, including the
        # gem total, from ``result.Inventory``. Without that envelope the claim
        # is accepted but the counter never moves.
        updated = {
            'GameAchievementId': ident,
            'UserGameAchievementId': text,
            'Id': text,
            'UserGameAchievementID': text,
            'UserAchievementId': text,
            'GameAchievementUserId': text,
            'UserGameAchievementsId': text,
            'ItemQuantity': self._integer(record.get('progress')),
            'LevelAchieved': level,
            'LevelRewardCollected': level,
            'IsViewed': 1,
        }
        return {'inventory': items,
                'userMaterialTypes': items,
                'user': dict(state.get('user') or {}),
                'result': {'UserGameAchievement': updated,
                           'Inventory': items,
                           'inventory': items,
                           'userMaterialTypes': items,
                           'Gems': gems,
                           'GemsCollected': gems,
                           'GameAchievementId': ident,
                           'LevelRewardCollected': level}}

    @staticmethod
    def _envelope(records: list[dict]) -> dict:
        """The original list key is undocumented; the client ignores unknown
        keys, so the records are published under the plausible spellings."""
        return {'result': records, 'userGameAchievements': records,
                'UserGameAchievements': records}

    def operate(self, state: dict, service: str, data: dict, now: int,
                inventory: object) -> dict:
        if service == 'ClientAchievement/GetUserAchievements':
            return self._envelope(self.sync(state, now, served=True))
        if service == 'ClientAchievement/GetUnReceievedUserGameAchievements':
            records = self.sync(state, now, persist=False)
            return self._envelope([record for record in records
                                   if record['LevelRewardCollected'] < record['LevelAchieved']])
        ident = self._ident(data)
        if service == 'ClientAchievement/MarkAchievementAsViewed':
            self.sync(state, now)
            record = self._record(state, str(ident))
            level = self._integer(record.get('levelAchieved'))
            viewed = self._integer(record.get('viewed'))
            served = self._integer(record.get('servedLevel'))
            if level > viewed or level > served:
                record['viewed'] = max(viewed, level)
                record['servedLevel'] = max(served, level)
                state['revision'] = int(state.get('revision', 0)) + 1
            return {}
        if service == 'ClientAchievement/CollectUserGameAchievementReward':
            return self._collect(state, ident, now, inventory)
        raise NotImplementedError(service)
