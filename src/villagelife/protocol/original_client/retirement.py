"""Local completion of an authored, scheduled Farewell quest."""
from __future__ import annotations

import copy
import uuid

from .habitats import OriginalHabitatRules
from .native_ids import reserve_ids

RETIRE = 'ClientVillager/RetireVillager'
QUEST_TYPE = 23


def active_retirements(state, definitions, at):
    for actor in state['world']['entities']:
        if (actor.get('templateType') != 'villager_type'
                or actor['position']['areaId'] != state['areaId']
                or int(actor.get('retireAt', 0)) <= at):
            continue
        event_id = int(actor.get('retireEventID', 0))
        if event_id <= 0:
            continue
        try:
            event = definitions.item('TimedEvent', event_id)
        except KeyError:
            continue
        if int(event['area']) == state['areaId']:
            yield actor, event


class OriginalRetirementRules:
    def __init__(self, definitions):
        self.defs = definitions

    def begin(self, state, data, at):
        if type(data.get('amount')) is not int or data['amount'] != 0:
            raise ValueError('Farewell requires a zero-amount timed quest')
        event_id = str(data.get('objectId', ''))
        villager_id = data.get('villagerId', '')
        matches = [(person, event) for person, event in active_retirements(state, self.defs, at)
                   if event['id'] == event_id and villager_id in ('', person['id'])]
        if len(matches) != 1:
            raise ValueError('No unique scheduled Farewell matches this quest')
        actor, event = matches[0]
        quests = state.setdefault('quests', [])
        for quest in quests:
            if (quest['questTypeId'] == QUEST_TYPE and quest['objectId'] == event_id
                    and quest['villagerId'] == actor['id']):
                return {'userQuest': copy.deepcopy(quest)}
        quest = {'id': 'local-quest-' + uuid.uuid4().hex, 'questTypeId': QUEST_TYPE,
                 'objectId': event_id, 'amount': 0, 'villagerId': actor['id'],
                 'createdAt': at, 'expiresAt': actor['retireAt']}
        quests.append(quest)
        state['revision'] = int(state.get('revision', 0)) + 1
        return {'userQuest': copy.deepcopy(quest)}

    def finish(self, state, data, at, owner):
        if data:
            raise ValueError('Farewell takes an empty request')
        result = {'RetireVillagerIDs': [], 'EmptiedShelterIDs': [], 'RemovedMaterialIDs': [],
                  'RemovedUserQuestIDs': [], 'RemovedUserTaskIDs': []}
        scheduled = list(active_retirements(state, self.defs, at))
        if not scheduled:
            if state.get('retiredVillagers'):
                return {'result': result}
            raise ValueError('No scheduled Farewell in this village')
        if len(scheduled) != 1:
            raise ValueError('Farewell needs one scheduled villager in this area')
        actor, event = scheduled[0]
        ident = actor['id']
        material = event['questObjectId']
        task_id = int(event['taskId'])
        started = int(actor['retireAt']) - int(event['Duration'])
        jobs = state.get('workAreas', {})
        preparations = [job for job in jobs.values()
                        if job.get('taskTypeId') == task_id
                        and job.get('position', {}).get('areaId') == state['areaId']
                        and int(job.get('createdAt', 0)) >= started]
        if (state['inventory'].get(material, 0) < 1
                or not any(job.get('status') == 'harvested' for job in preparations)):
            raise ValueError('Craft and collect the Farewell gift first')
        if any(job.get('villagerId') == ident and job.get('status') == 'working'
               and job['completionTime'] > at for job in jobs.values()):
            raise ValueError('This villager is still busy. Finish their work before Farewell')

        reserve_ids(state, owner, [ident])
        for shelter in state['world']['entities']:
            for bed in shelter.get('beds', []):
                if bed.get('villagerId') == ident:
                    OriginalHabitatRules.release_bed(actor, shelter, bed)
                    if shelter['id'] not in result['EmptiedShelterIDs']:
                        result['EmptiedShelterIDs'].append(shelter['id'])
        state['inventory'][material] -= 1
        if state['inventory'][material] == 0:
            result['RemovedMaterialIDs'].append(int(material))
        quests = state.get('quests', [])
        for quest in quests[:]:
            if (quest['questTypeId'] == QUEST_TYPE and quest['objectId'] == event['id']
                    and quest['villagerId'] == ident):
                result['RemovedUserQuestIDs'].append(quest['id'])
                quests.remove(quest)
        state['wants'] = [want for want in state.get('wants', []) if want['VillagerStringID'] != ident]
        state['world']['entities'].remove(actor)
        actor.update(retireAt=0, retireEventID=0, retiredAt=at)
        state.setdefault('retiredVillagers', {})[ident] = actor
        result['RetireVillagerIDs'].append(ident)
        state['revision'] = int(state.get('revision', 0)) + 1
        return {'result': result}
