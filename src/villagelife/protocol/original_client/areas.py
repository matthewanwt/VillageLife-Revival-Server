"""Area unlocking, area 1/2/3 authored seeds and villager transfers.

The source-defined level gates are read from original material_type rows. New
area objects receive stable local IDs; villagers retain their original IDs.
Unknown worker/habitat invariants fail rather than damaging the save.
"""
from __future__ import annotations
import copy
import json
import time
from .catalog import OriginalDefinitions
from .world import OriginalWorldRules

class AreaRules:
    MATERIAL_MARKERS={1:'231',2:'232',3:'1536'}
    def __init__(self, definitions:OriginalDefinitions):
        self.definitions=definitions
        self.world=OriginalWorldRules(definitions)

    def destination(self, value)->int:
        if type(value) not in (int,str) or not str(value).isdigit() or int(value) not in self.MATERIAL_MARKERS:
            raise ValueError('Original area 1, 2 or 3 required')
        return int(value)

    def seed(self, state:dict, area_id:int, at:int)->bool:
        initialized=state.setdefault('initializedAreas',[1])
        if area_id in initialized:return False
        _area,scenario=self.definitions.scenario_for_area(area_id)
        scene=json.loads(scenario['clientData'])
        if not isinstance(scene,list):raise ValueError('Expected authored scenario entity list')
        authored=self.world.authored(area_id)
        auth={item['id'] for item in authored}
        existing={e['id'] for e in state['world']['entities']}
        created=[]
        for i,raw in enumerate(scene):
            item=copy.deepcopy(raw)
            key=str(item.get('id') or f'area-{area_id}-scene-{i}')
            if key in auth:continue
            if key in existing:
                item['originalSeedId']=key
                key=f'local-area-{area_id}-scene-{i}'
            item['id']=key
            item.setdefault('position',item.pop('posiiton',{}))['areaId']=area_id
            if key in existing:raise ValueError('Duplicate authored scenario object ID')
            existing.add(key);created.append(item)
        for i,item in enumerate(authored):
            value=copy.deepcopy(item);key=str(value['id'])
            if key in existing:
                value['originalSeedId']=key;key=f'local-area-{area_id}-authored-{i}'
            value['id']=key
            value.setdefault('position',{})['areaId']=area_id
            if key in existing:raise ValueError('Duplicate authored persistent object ID')
            existing.add(key);created.append(value)
        state['world']['entities'].extend(created)
        initialized.append(area_id)
        return True

    def unlock(self,state:dict, raw_area, now:int)->dict:
        area_id=self.destination(raw_area)
        maximum=int(state['user'].get('maxAreaId',1))
        if area_id>maximum:
            if area_id!=maximum+1:raise ValueError('Unlock preceding village first')
            marker=self.definitions.item('material_type',self.MATERIAL_MARKERS[area_id])
            if int(state['user']['userLevelID'])<int(marker['unlockLevel']):
                raise ValueError('Village level too low to unlock this area')
        self.seed(state,area_id,now)
        state['user']['maxAreaId']=max(area_id,maximum)
        state['revision']=int(state.get('revision',0))+1
        return {'userArea':{'areaId':area_id},'user':dict(state['user']),
                'inventory':copy.deepcopy(state.get('inventory',{}))}

    def view(self,state:dict,raw_area,now:int)->dict:
        area_id=self.destination(raw_area)
        if area_id>int(state['user'].get('maxAreaId',1)):
            raise ValueError('Area has not been unlocked')
        self.seed(state,area_id,now)
        if state['areaId']!=area_id:
            state['areaId']=area_id
            area,scenario=self.definitions.scenario_for_area(area_id)
            state['areaName']=area['name']
            state['user']['scenarioId']=int(scenario['serverScenarioId'])
        state['revision']=int(state.get('revision',0))+1
        return self.world.area_content(state,area_id,now)

    def move(self,state:dict,data:dict,now:int)->dict:
        area_id=self.destination(data.get('areaId'))
        if area_id>int(state['user'].get('maxAreaId',1)):
            raise ValueError('Destination area not unlocked')
        ids=data.get('villagerIds')
        if not isinstance(ids,list) or not 1<=len(ids)<=100 or not all(isinstance(v,str) for v in ids):
            raise ValueError('Owned villagerIds array required')
        if len(ids)!=len(set(ids)):raise ValueError('Duplicate villager ID')
        actors={e['id']:e for e in state['world']['entities'] if e.get('templateType')=='villager_type'}
        people=[]
        for ident in ids:
            if ident not in actors:raise ValueError('Unknown villager for this world')
            people.append(actors[ident])
        for person in people:
            if person.get('shelterBedId'):
                raise NotImplementedError('Moving villagers with assigned beds needs verified habitat transfer rules')
            if any(t.get('villagerId')==person['id'] and t.get('status')!='harvested'
                   for t in state.get('workAreas',{}).values()):
                raise ValueError('Complete existing villager work before transfer')
        self.seed(state,area_id,now)
        first=next((e.get('position') for e in state['world']['entities']
                    if self.world._area(e)==area_id and e.get('templateType')=='workshop'),None)
        if not first:raise NotImplementedError('Destination workshop location missing in authored data')
        for index,person in enumerate(people):
            if self.world._area(person)==area_id:continue
            person['position']={**first,'areaId':area_id,
                                 'x':float(first['x'])+40*(index+1)}
            person['updatedAt']=now
        state['revision']=int(state.get('revision',0))+1
        return {}
