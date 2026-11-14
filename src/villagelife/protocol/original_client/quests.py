"""Validated quest creation and completion using authored original tables."""
from __future__ import annotations
import copy
import uuid
from decimal import Decimal
from .catalog import OriginalDefinitions
from .inventory import OriginalInventoryRules


class OriginalQuestRules:
    ALLOWED_TARGETS={'material_type','building_task','story','progression_object',
                     'fire_type','decor_item','quest_item','interactive_activity'}

    def __init__(self, definitions: OriginalDefinitions,
                 inventory: OriginalInventoryRules | None = None):
        self.defs=definitions
        self.inventory=inventory or OriginalInventoryRules(definitions)

    TRAVEL_OBJECTIVES = {'24': 2, '77': 3}
    ONE_TIME_TRAVEL_STORIES = TRAVEL_OBJECTIVES.keys() | {'25', '74', '75', '78'}

    @staticmethod
    def completed_travel_stories(state: dict) -> dict:
        return {str(record['quest']['objectId']): record
                for record in state.get('completedQuests', {}).values()
                if record.get('quest', {}).get('questTypeId') == 12
                and str(record['quest'].get('objectId')) in OriginalQuestRules.ONE_TIME_TRAVEL_STORIES}

    def travel_objective_reached(self, state: dict, story: str) -> bool:
        return story in self.TRAVEL_OBJECTIVES and int(state.get('user', {}).get('maxAreaId', 1)) >= self.TRAVEL_OBJECTIVES[story]

    def reconcile_travel(self, state: dict, at: int) -> None:
        completed = self.completed_travel_stories(state)
        for quest in state.get('quests', [])[:]:
            if quest.get('questTypeId') != 12:
                continue
            story = str(quest['objectId'])
            prior = completed.get(story)
            if prior is not None:
                state['completedQuests'].setdefault(quest['id'], {**prior, 'quest': copy.deepcopy(quest)})
                state['quests'].remove(quest)
            elif self.travel_objective_reached(state, story):
                self.complete(state, {'userQuestId': quest['id']}, at)
                completed[story] = state['completedQuests'][quest['id']]

    def add(self, state: dict, data: dict, at: int) -> dict:
        quest_type=data.get('questTypeId')
        obj=str(data.get('objectId',''))
        amount=data.get('amount',1)
        if (isinstance(quest_type,bool) or not isinstance(quest_type,int) or
                isinstance(amount,bool) or not isinstance(amount,(int,float)) or amount<=0):
            raise ValueError('Invalid quest request')
        definition=self.defs.item('quest_type',quest_type)
        target=definition['targetObjectType']
        if target not in self.ALLOWED_TARGETS:
            raise NotImplementedError('Quest objective rules not recovered: '+target)
        self.defs.item(target,obj)
        if target == 'story' and obj in self.ONE_TIME_TRAVEL_STORIES:
            self.reconcile_travel(state, at)
            completed = self.completed_travel_stories(state).get(obj)
            if completed is not None:
                return {'userQuest': copy.deepcopy(completed['quest'])}
        for current in state.setdefault('quests',[]):
            if current.get('questTypeId')==quest_type and current.get('objectId')==obj:
                return {'userQuest':copy.deepcopy(current)}
        quest={'id':'local-quest-'+uuid.uuid4().hex,'questTypeId':quest_type,
               'objectId':obj,'amount':amount,'createdAt':at,
               'villagerId':str(data.get('villagerId',''))}
        state['quests'].append(quest)
        if target == 'story' and self.travel_objective_reached(state, obj):
            self.complete(state, {'userQuestId': quest['id']}, at)
        state['revision']=int(state.get('revision',0))+1
        return {'userQuest':copy.deepcopy(quest)}

    def complete(self, state: dict, data: dict, at: int) -> dict:
        ident=data.get('userQuestId')
        if not isinstance(ident,str):raise ValueError('Quest identifier required')
        completed=state.setdefault('completedQuests',{})
        if ident in completed:return copy.deepcopy(completed[ident]['response'])
        quest=next((row for row in state.setdefault('quests',[]) if row.get('id')==ident),None)
        if quest is None:raise ValueError('Unknown local quest')
        definition=self.defs.item('quest_type',quest['questTypeId'])
        target=definition['targetObjectType'];obj=quest['objectId']
        amount=quest['amount'];reward_set='0'
        story_id = obj if target == 'story' else ''
        traveled = self.travel_objective_reached(state, story_id)
        if target=='story':
            story=self.defs.item('story',obj)
            target=self.defs.item('quest_type',story['questType'])['targetObjectType']
            obj=story['questObjectId'];amount=float(story['questAmount']);reward_set=story['rewardSet']
        if target=='material_type':
            if not traveled and state.get('inventory',{}).get(str(obj),0)<amount:
                raise ValueError('Quest objective has not been reached')
        elif target=='interactive_activity':
            matches=[row for row in state.get('interactiveReceipts',{}).values()
                     if row.get('participants',[None,None,None])[2]==str(obj)
                     and row.get('completionTime',at+1)<=at
                     and row.get('startedAt',0)>=quest.get('createdAt',0)
                     and (not quest.get('villagerId') or quest['villagerId'] in row.get('participants',[])[:2])]
            if len(matches)<amount:raise ValueError('Interactive quest objective has not completed')
        else:
            raise NotImplementedError('Quest completion condition not recovered: '+target)
        rewards=[row for row in self.defs.rows('reward_set_item')
                 if reward_set!='0' and row['setId']==reward_set]
        if any(Decimal(row['chance'])!=1 for row in rewards):
            raise NotImplementedError('Quest reward probability rule not recovered')
        for row in rewards:
            key=str(row['materialType'])
            current = Decimal(str(state['inventory'].get(key, 0)))
            quantity = Decimal(row['quantity'])
            state['inventory'][key] = float(max(current, quantity) if story_id in self.TRAVEL_OBJECTIVES
                                            else current + quantity)
        response={'inventory':self.inventory.list_items(state)}
        state['quests']=[row for row in state['quests'] if row.get('id')!=ident]
        completed[ident]={'quest':copy.deepcopy(quest),'completedAt':at,
                          'response':copy.deepcopy(response)}
        state['revision']=int(state.get('revision',0))+1
        return response
