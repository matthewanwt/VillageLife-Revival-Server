"""Transactional original-client work, construction and harvesting."""
from __future__ import annotations
from villagelife.persistence.history import active_work
from .indexes import entities_for_id
import copy
from decimal import Decimal
import math
import time
import uuid
from .catalog import OriginalDefinitions, matching
from .daily import satisfy_wants
from .world import OriginalWorldRules
from .inventory import OriginalInventoryRules, spend_gems
from .buildings import OriginalBuildingRules
from .birth_skills import skill_type
import struct

class OriginalWorkRules:
    TYPES={'ClientTaskService/StartGatheringTask':'3',
           'ClientTaskService/StartCraftingTask':'1',
           'ClientTaskService/StartFarmingTask':'4',
           'ClientTaskService/StartFishingTask':'8',
           'ClientTaskService/StartHuntingTask':'9',
           'ClientTaskService/StartBuildingTask':'2'}
    EQUIPMENT_TASKS = {
        '8': ('userFishingBoatId', 'fishing_boat', 2, 'fishing_task', 'fishingLocationPosition'),
        '9': ('userHuntingSledId', 'HuntingSledType', 3, 'HuntingTask', 'huntingLocationPosition'),
    }

    def __init__(self,defs:OriginalDefinitions,inventory:OriginalInventoryRules|None=None):
        self.defs=defs
        self.world=OriginalWorldRules(defs)
        self.inventory=inventory or OriginalInventoryRules(defs)
        self.buildings=OriginalBuildingRules(defs,self.inventory)

    @staticmethod
    def _n(value):
        number=Decimal(str(value))
        if not number.is_finite() or number<0:raise ValueError('Invalid material amount')
        return number

    def _duration(self, task: dict, actor: dict) -> int:
        duration = self._n(task['duration'])
        if duration != int(duration):
            raise NotImplementedError('Nonintegral duration rule not recovered')
        skill = int(task.get('skillId', 0))
        if not skill:
            return int(duration)
        skills = actor.get('skills', [])
        gathering = str(task.get('taskType')) == '3'
        # Script_3253_GetVillagerTaskDuration reads the first 18 native slots.
        # Keep other task families on their existing arithmetic and slot rules.
        if gathering:
            skills = skills[:18]
        ranks = sum(skill_type(row) == skill for row in skills)
        if not ranks:
            return int(duration)
        # Original Script 3253 subtracts the authored multiplier per matching
        # rank, caps the reduction at 75%, then truncates the adjusted seconds.
        reduction = self._n(self.defs.item('villager_skill', skill)['professionMultiplier'])
        if gathering:
            if duration >= 2**31 or reduction > 1:
                raise ValueError('Gathering duration or multiplier outside native range')
            def f32(value):
                return struct.unpack('<f', struct.pack('<f', float(value)))[0]
            factor = f32(1)
            for _ in range(ranks):
                factor = f32(factor - f32(reduction))
            adjusted = f32(f32(duration) * max(f32(0.25), factor))
            if adjusted >= 2**31:
                raise ValueError('Gathering duration outside native integer range')
            return int(adjusted)
        return int(duration * max(Decimal('0.25'), 1 - ranks * reduction))

    def start(self,state:dict,service:str,data:dict,at:int)->dict:
        expected=self.TYPES.get(service)
        if not expected:raise NotImplementedError('Original building task rules are not yet complete')
        task_id=data.get('taskTypeId')
        if type(task_id) is not int:raise ValueError('Task type ID must be integer')
        task=self.defs.item('task',task_id)
        if task.get('taskType')!=expected and not (expected=='2' and task.get('taskType')=='6'):
            raise ValueError('Task family mismatch')
        villager=data.get('villagerId')
        if not isinstance(villager,str):raise ValueError('Villager identifier required')
        equipment = self.EQUIPMENT_TASKS.get(expected)
        source_field = equipment[0] if equipment else ('userFarmPlotId' if expected == '4' else 'userMaterialSourceId')
        source_id = data.get(source_field)
        if (equipment or expected in {'3', '4'}) and not isinstance(source_id, str):
            raise ValueError('Source identifier required')
        if expected=='1' and source_id is not None and not isinstance(source_id,str):
            raise ValueError('Source identifier must be a string')
        actors=entities_for_id(state, villager, 'villager_type')
        if len(actors)!=1:raise ValueError('Villager not found in this world')
        actor=actors[0]
        if self.world._area(actor)!=state['areaId']:raise ValueError('Villager in another village')
        actor_type=self.world.current_villager_type(actor,at)
        if actor_type.get('canWork')!='1':raise ValueError('Villager cannot work at this life stage')
        excluded=task.get('excludeVillagerSet','0')
        if excluded!='0' and any(row.get('villagerSet')==excluded and
                                  row.get('villagerType')==str(actor_type.get('id', actor['templateId']))
                                  for row in self.defs.rows('villager_set_item')):
            raise ValueError('Villager is excluded from this task')
        family='6' if expected=='2' and task.get('taskType')=='6' else expected
        upgrade_definition=None
        if family=='2':
            candidates=[v for v in state['world']['entities'] if v.get('templateType')=='building_task'
                        and self.world._area(v)==state['areaId']
                        and str(self.defs.item('building_task',v['templateId']).get('taskId'))==str(task_id)]
            candidates.sort(key=lambda item:math.hypot(float(item['position']['x'])-float(data.get('x',0)),
                                                        float(item['position']['y'])-float(data.get('y',0))))
            if not candidates:raise ValueError('No matching construction foundation')
            source=candidates[0];source_id=source['id']
            self.buildings.completion_definition(source)
        elif family=='6':
            candidates=[]
            for upgrade in self.defs.rows('building_task'):
                if str(upgrade.get('taskId'))!=str(task_id) or str(upgrade.get('parentId'))=='-1':continue
                parent=self.defs.item('building_task',upgrade['parentId'])
                previous=self.defs.item('building_type',parent['buildingType'])
                self.buildings.completion_definition({'templateId':int(upgrade['id'])})
                for item in state['world']['entities']:
                    if (item.get('templateType')==previous['entityRef'] and
                        int(item.get('templateId',-1))==int(previous['entityID']) and
                        self.world._area(item)==state['areaId']):candidates.append((item,upgrade))
            candidates.sort(key=lambda pair:math.hypot(float(pair[0]['position']['x'])-float(data.get('x',0)),
                                                        float(pair[0]['position']['y'])-float(data.get('y',0))))
            if not candidates:raise ValueError('No matching building available to upgrade')
            source,upgrade_definition=candidates[0];source_id=source['id']
        else:
            source_type = equipment[1] if equipment else {'3': 'material_source', '4': 'farming_plot', '1': 'workshop'}[expected]
            sources=[v for v in state['world']['entities'] if v.get('id')==source_id and v.get('templateType')==source_type]
            if expected=='1' and source_id is None:
                sources = [
                    entity for entity in state['world']['entities']
                    if entity.get('templateType') == source_type
                    and self.world._area(entity) == state['areaId']
                    and str(task['workAreaType']) in self.defs.item(
                        'workshop', entity['templateId'])['tableIDs'].split(',')
                ]
                sources.sort(key=lambda item: math.hypot(
                    float(item['position']['x'])-float(data.get('x',0)),
                    float(item['position']['y'])-float(data.get('y',0))))
            if not sources:raise ValueError('Source not found')
            source=sources[0]
        if self.world._area(source)!=state['areaId'] or data.get('areaId')!=state['areaId']:
            raise ValueError('Task source must be in active area')
        if family=='3':
            definition=self.defs.item('material_source',source['templateId'])
            if int(definition['task'])!=task_id:raise ValueError('Task does not match resource source')
        target_position = None
        if equipment:
            _, _, area, table, coordinates = equipment
            if state['areaId'] != area:
                raise ValueError('Task equipment belongs in a different village')
            target = next((row for row in self.defs.rows(table) if row.get('taskId') == str(task_id)), None)
            if target is None:
                raise ValueError('Unknown original equipment task')
            target_position = tuple(map(float, target[coordinates].split(',')))
        if family=='4' and not any(v.get('taskId')==str(task_id) for v in self.defs.rows('farming_task')):
            raise ValueError('Unknown original farming recipe')
        if family=='1':
            workshop=self.defs.item('workshop',source['templateId'])
            if str(task['workAreaType']) not in workshop['tableIDs'].split(','):
                raise ValueError('Recipe requires another workshop table')
        # Original field coordinates are proximity checks, never authority for creating resources.
        position={k:data.get(k,0) for k in ('x','y','rotation')}
        if any(type(value) not in (int,float) or not math.isfinite(value) for value in position.values()):
            raise ValueError('Invalid task position')
        anchors = [(float(source['position']['x']), float(source['position']['y']))]
        if target_position is not None:
            anchors.append(target_position)
        if all(math.hypot(float(position['x']) - x, float(position['y']) - y) > 200 for x, y in anchors):
            raise ValueError('Task position is not close to the source')
        for previous in active_work(state):
            if previous['status']=='harvested':continue
            if previous['villagerId']==villager and previous['status']=='working' and previous['completionTime']>at:
                raise ValueError('Villager is already working')
            if family!='1' and previous['sourceId']==source['id']:
                raise ValueError('Resource source is already occupied')
        if family=='1':
            concurrent=sum(v['status']!='harvested' and v['sourceId']==source['id']
                           for v in active_work(state))
            if concurrent>=int(workshop['tableCount']):raise ValueError('Workshop is full')
        reward_set=task['rewardSet']
        rewards=matching(self.defs, 'reward_set_item', 'setId', reward_set) if reward_set!='0' else []
        if family in {'2','6'}:
            building=self.buildings.completion_definition(
                {'templateId':int(upgrade_definition['id'])} if upgrade_definition else source)
            if not any(str(row['materialType'])==str(building['materialType']) for row in rewards):
                rewards.append({'materialType':str(building['materialType']),'quantity':'1','chance':'1'})
        if not rewards or any(self._n(row['chance'])!=1 for row in rewards):
            raise NotImplementedError('Non-deterministic original reward selection is not recovered')
        level_requirements=[row for row in self.defs.rows('requirement_set_item')
                            if row['requirementSet']==str(task.get('levelRequirement','0'))]
        milestones = self.inventory.milestones(state)
        for requirement in level_requirements:
            key=str(requirement['materialType'])
            if self.inventory.requirement_quantity(state,key,milestones)<self._n(requirement['quantity']):
                raise ValueError('Task unlock requirement is not met: '+key)
        requirements=[row for row in self.defs.rows('requirement_set_item')
                      if row['requirementSet']==task['requirementSet']]
        costs={}
        for requirement in requirements:
            if requirement.get('villagers','undefined') not in ('undefined','0',''):
                raise NotImplementedError('Multi-villager task requirements not recovered')
            key=str(requirement['materialType'])
            cost=self._n(requirement['quantityUsed'])
            available=(self._n(state.get('inventory',{}).get(key,0)) if cost
                       else self.inventory.requirement_quantity(state,key,milestones))
            if available<self._n(requirement['quantity']):raise ValueError('Task material requirements not met')
            costs[key]=costs.get(key,Decimal(0))+cost
        for key,cost in costs.items():
            if self._n(state['inventory'].get(key,0))<cost:raise ValueError('Insufficient material for task')
        duration=self._duration(task,actor)
        response={'createdAt':at,'completionTime':at+duration,
                  'workAreaId':'local-work-'+uuid.uuid4().hex,'villager':{'id':villager}}
        for key,cost in costs.items():
            if key not in self.inventory.starter_tools:
                state['inventory'][key]=float(self._n(state['inventory'].get(key,0))-cost)
        record={'id':response['workAreaId'],'status':'working','family':family,
                'taskTypeId':task_id,'sourceId':source['id'],'villagerId':villager,
                'createdAt':at,'completionTime':response['completionTime'],
                'position':{**position,'areaId':state['areaId']},
                'rewards':[{'materialTypeId':int(row['materialType']),
                            'amount':float(self._n(row['quantity']))} for row in rewards],
                'startResponse':copy.deepcopy(response),
                'sourceRules':'authored task and chance-1 reward_set_item (no random modifiers)'}
        if family in {'2','6'} and source.get('templateType')=='building_task':
            record['sourceSnapshot']=copy.deepcopy(source)
        if upgrade_definition:record['upgradeDefinitionId']=int(upgrade_definition['id'])
        state.setdefault('workAreas',{})[record['id']]=record
        state['revision']=int(state.get('revision',0))+1
        return response

    def harvest(self,state:dict,data:dict,at:int)->dict:
        ident=data.get('workAreaId');job=state.get('workAreas',{}).get(ident)
        if not job:raise ValueError('Unknown work area')
        if data.get('taskTypeId')!=job['taskTypeId']:
            raise ValueError('Harvest task does not match assigned work')
        if job['status']=='harvested':return copy.deepcopy(job['harvestResponse'])
        if at<job['completionTime']:raise ValueError('Task is not complete yet')
        for reward in job['rewards']:
            key=str(reward['materialTypeId'])
            state['inventory'][key]=float(self._n(state['inventory'].get(key,0))+
                                         self._n(reward['amount']))
        objects=self.buildings.complete(state,job) if job.get('family') in {'2','6'} else []
        satisfied = []
        if objects and job.get('family') in {'2', '6'}:
            built = next(entity for entity in state['world']['entities'] if entity['id'] == objects[0]['id'])
            if built['templateType'] == 'fun_building':
                activity = self.defs.item('fun_building', built['templateId'])['funActivity']
                material = int(self.defs.item('fun_activity', activity)['materialType'])
                people = {entity['id'] for entity in state['world']['entities']
                          if entity.get('templateType') == 'villager_type'
                          and self.world._area(entity) == self.world._area(built)}
                satisfied = satisfy_wants(state, people, 3, at, material)
        answer={'objects':objects,'inventory':self.inventory.list_items(state),
                'SatisfiedWantModels':satisfied}
        job.update(status='harvested',harvestedAt=at,harvestResponse=copy.deepcopy(answer))
        state['revision']=int(state.get('revision',0))+1
        return answer

    def instant_complete(self,state:dict,data:dict,at:int)->dict:
        ident=data.get('workAreaId');job=state.get('workAreas',{}).get(ident)
        if not isinstance(job,dict):raise ValueError('Unknown work area')
        if job.get('status')=='harvested' or job.get('instantCompleteReceipt'):
            return {'completionTime':job['completionTime'],'inventory':self.inventory.list_items(state)}
        remaining=max(0,int(job['completionTime'])-at)
        cost=self._instant_price(remaining) if remaining else 0
        spend_gems(state,cost)
        original=job['completionTime'];job['completionTime']=min(at,original)
        job['status']='ready'
        if isinstance(job.get('startResponse'),dict):job['startResponse']['completionTime']=job['completionTime']
        job['instantCompleteReceipt']={'completedAt':at,'gemsSpent':float(cost),
            'originalCompletionTime':original,'rule':'original float32 task-time gem curve'}
        state['revision']=int(state.get('revision',0))+1
        return {'completionTime':job['completionTime'],'inventory':self.inventory.list_items(state)}

    def _instant_price(self,remaining:int)->int:
        def f(value):return struct.unpack('<f',struct.pack('<f',value))[0]
        globals_={row['label']:row['value'] for row in self.defs.rows('global')}
        try:
            xs=[f(float(globals_['gemCurveVariableTaskTime'+key]))
                for key in ('1min','1hour','1day','1week')]
            ys=[f(float(globals_['gemCalcTaskValue'+str(i)])) for i in range(1,5)]
        except (KeyError,ValueError) as exc:
            raise NotImplementedError('Original instant-finish curve is unavailable') from exc
        t=min(f(float(remaining)),xs[-1]);index=0 if t<xs[1] else 1 if t<xs[2] else 2
        scale=f(f(xs[index+1]-xs[index])/f(ys[index+1]-ys[index]))
        return max(1,math.floor(f(ys[index]+f(f(t-xs[index])/scale))))

    def overlay(self, state: dict, at: int, area_id: int) -> list[dict]:
        result=[]
        for job in active_work(state):
            if job.get('status') == 'harvested' or self.world._area(job) != area_id:
                continue
            task=self.defs.item('task',job['taskTypeId'])
            result.append({'id':job['id'],'templateType':'work_area','templateId':int(task['workAreaType']),
                           'taskTypeId':job['taskTypeId'],'serverPersisted':True,
                           'position':copy.deepcopy(job['position']),
                           'status':int(at>=job['completionTime']),
                           'villagerId':job['villagerId'] if at<job['completionTime'] else '',
                           'userMaterialSourceId':job['sourceId'],
                           'createdAt':job['createdAt'],'completionTime':job['completionTime']})
        return result
