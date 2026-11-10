"""Transactional original-client gather/craft/farm jobs, source-authored rules.

Only deterministic chance-1 reward sets can be collected. Building
construction/upgrades, alternative loot weighting, and instant-finish curves
are deliberately excluded until their coupled rules are verified.
"""
from __future__ import annotations
import copy
from decimal import Decimal
import math
import time
import uuid
from .catalog import OriginalDefinitions
from .world import OriginalWorldRules
from .inventory import OriginalInventoryRules

class OriginalWorkRules:
    TYPES={'ClientTaskService/StartGatheringTask':'3',
           'ClientTaskService/StartCraftingTask':'1',
           'ClientTaskService/StartFarmingTask':'4'}
    def __init__(self,defs:OriginalDefinitions,inventory:OriginalInventoryRules|None=None):
        self.defs=defs
        self.world=OriginalWorldRules(defs)
        self.inventory=inventory or OriginalInventoryRules(defs)

    @staticmethod
    def _n(value):
        number=Decimal(str(value))
        if not number.is_finite() or number<0:raise ValueError('Invalid material amount')
        return number

    def start(self,state:dict,service:str,data:dict,at:int)->dict:
        expected=self.TYPES.get(service)
        if not expected:raise NotImplementedError('Original building task rules are not yet complete')
        task_id=data.get('taskTypeId')
        if type(task_id) is not int:raise ValueError('Task type ID must be integer')
        task=self.defs.item('task',task_id)
        if task.get('taskType')!=expected:raise ValueError('Task family mismatch')
        villager=data.get('villagerId')
        if not isinstance(villager,str):raise ValueError('Villager identifier required')
        source_id=(data.get('userFarmPlotId') if expected=='4' else data.get('userMaterialSourceId'))
        if not isinstance(source_id,str):raise ValueError('Source identifier required')
        actors=[v for v in state['world']['entities'] if v.get('id')==villager and v.get('templateType')=='villager_type']
        if len(actors)!=1:raise ValueError('Villager not found in this world')
        actor=actors[0]
        if self.world._area(actor)!=state['areaId']:raise ValueError('Villager in another village')
        source_type={'3':'material_source','4':'farming_plot','1':'workshop'}[expected]
        sources=[v for v in state['world']['entities'] if v.get('id')==source_id and v.get('templateType')==source_type]
        if expected=='1' and not sources:
            sources=[v for v in state['world']['entities'] if v.get('templateType')==source_type and self.world._area(v)==state['areaId']]
            sources.sort(key=lambda item:math.hypot(float(item['position']['x'])-float(data.get('x',0)),
                                                     float(item['position']['y'])-float(data.get('y',0))))
        if not sources:raise ValueError('Source not found')
        source=sources[0]
        if self.world._area(source)!=state['areaId'] or data.get('areaId')!=state['areaId']:
            raise ValueError('Task source must be in active area')
        if expected=='3':
            definition=self.defs.item('material_source',source['templateId'])
            if int(definition['task'])!=task_id:raise ValueError('Task does not match resource source')
        if expected=='4' and not any(v.get('taskId')==str(task_id) for v in self.defs.rows('farming_task')):
            raise ValueError('Unknown original farming recipe')
        if expected=='1':
            workshop=self.defs.item('workshop',source['templateId'])
            if str(task['workAreaType']) not in workshop['tableIDs'].split(','):
                raise ValueError('Recipe requires another workshop table')
        # Original field coordinates are proximity checks, never authority for creating resources.
        position={k:data.get(k,0) for k in ('x','y','rotation')}
        if any(type(value) not in (int,float) or not math.isfinite(value) for value in position.values()):
            raise ValueError('Invalid task position')
        if math.hypot(float(position['x'])-float(source['position']['x']),
                      float(position['y'])-float(source['position']['y']))>200:
            raise ValueError('Task position is not close to the source')
        for previous in state.get('workAreas',{}).values():
            if previous['status']=='harvested':continue
            if previous['villagerId']==villager and previous['status']=='working' and previous['completionTime']>at:
                raise ValueError('Villager is already working')
            if expected!='1' and previous['sourceId']==source['id']:
                raise ValueError('Resource source is already occupied')
        if expected=='1':
            concurrent=sum(v['status']!='harvested' and v['sourceId']==source['id']
                           for v in state.get('workAreas',{}).values())
            if concurrent>=int(workshop['tableCount']):raise ValueError('Workshop is full')
        reward_set=task['rewardSet']
        rewards=[row for row in self.defs.rows('reward_set_item') if reward_set!='0' and row['setId']==reward_set]
        if not rewards or any(self._n(row['chance'])!=1 for row in rewards):
            raise NotImplementedError('Non-deterministic original reward selection is not recovered')
        if task.get('levelRequirement','0')!='0':
            raise NotImplementedError('Original task unlock requirements need verification')
        requirements=[row for row in self.defs.rows('requirement_set_item')
                      if row['requirementSet']==task['requirementSet']]
        costs={}
        for requirement in requirements:
            if requirement.get('villagers','undefined') not in ('undefined','0',''):
                raise NotImplementedError('Multi-villager task requirements not recovered')
            key=str(requirement['materialType'])
            available=self._n(state.get('inventory',{}).get(key,0))
            if available<self._n(requirement['quantity']):raise ValueError('Task material requirements not met')
            cost=self._n(requirement['quantityUsed'])
            costs[key]=costs.get(key,Decimal(0))+cost
        for key,cost in costs.items():
            if self._n(state['inventory'].get(key,0))<cost:raise ValueError('Insufficient material for task')
        duration=self._n(task['duration'])
        if duration!=int(duration):raise NotImplementedError('Nonintegral duration rule not recovered')
        response={'createdAt':at,'completionTime':at+int(duration),
                  'workAreaId':'local-work-'+uuid.uuid4().hex,'villager':{'id':villager}}
        for key,cost in costs.items():
            state['inventory'][key]=float(self._n(state['inventory'].get(key,0))-cost)
        record={'id':response['workAreaId'],'status':'working','family':expected,
                'taskTypeId':task_id,'sourceId':source['id'],'villagerId':villager,
                'createdAt':at,'completionTime':response['completionTime'],
                'position':{**position,'areaId':state['areaId']},
                'rewards':[{'materialTypeId':int(row['materialType']),
                            'amount':float(self._n(row['quantity']))} for row in rewards],
                'startResponse':copy.deepcopy(response),
                'sourceRules':'authored task and chance-1 reward_set_item (no random modifiers)'}
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
        if job['family'] not in ('1','3','4'):
            raise NotImplementedError('Building completion requires verified construction rules')
        for reward in job['rewards']:
            key=str(reward['materialTypeId'])
            state['inventory'][key]=float(self._n(state['inventory'].get(key,0))+
                                         self._n(reward['amount']))
        answer={'objects':[],'inventory':self.inventory.list_items(state),
                'SatisfiedWantModels':[]}
        job.update(status='harvested',harvestedAt=at,harvestResponse=copy.deepcopy(answer))
        state['revision']=int(state.get('revision',0))+1
        return answer

    def overlay(self,state:dict,at:int)->list[dict]:
        result=[]
        for job in state.get('workAreas',{}).values():
            if job.get('status')=='harvested':continue
            task=self.defs.item('task',job['taskTypeId'])
            result.append({'id':job['id'],'templateType':'work_area','templateId':int(task['workAreaType']),
                           'taskTypeId':job['taskTypeId'],'serverPersisted':True,
                           'position':copy.deepcopy(job['position']),
                           'status':int(at>=job['completionTime']),
                           'villagerId':job['villagerId'] if at<job['completionTime'] else '',
                           'userMaterialSourceId':job['sourceId'],
                           'createdAt':job['createdAt'],'completionTime':job['completionTime']})
        return result
