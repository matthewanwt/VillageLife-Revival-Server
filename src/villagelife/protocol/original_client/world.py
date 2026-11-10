"""Source-derived first normal world. Does not invent ongoing production rules.

The original client seeds scenery from packaged scenario data and overlays
server-persisted entities. This reconstructs only the documented bridge from
FTUE checkpoint 217 into scenario 2 (area 1).
"""
from __future__ import annotations
import copy
import json
import time
import xml.etree.ElementTree as ET
from .catalog import OriginalDefinitions

class OriginalWorldRules:
    def __init__(self, definitions: OriginalDefinitions):self.defs=definitions

    @staticmethod
    def _area(entity: dict) -> int:
        return int(entity.get('position',entity.get('posiiton',{})).get('areaId',1))

    @staticmethod
    def _entity_from_xml(element: ET.Element) -> dict:
        def convert(node):
            if len(node):
                value=dict(node.attrib)
                for child in node:value[child.tag]=convert(child)
                return value
            raw=(node.text or '').strip()
            if node.tag in {'x','y','rotation','amount','areaId'}:
                value=float(raw or 0)
                return int(value) if value.is_integer() else value
            return raw
        result=convert(element)
        result['templateId']=int(result['templateId'])
        result['serverPersisted']=True
        return result

    def authored(self, area_id: int) -> list[dict]:
        _area,scenario=self.defs.scenario_for_area(area_id)
        root=ET.fromstring(scenario['data'])
        entities=root.find('entities')
        if entities is None:raise ValueError('Missing original authored entities')
        result=[self._entity_from_xml(element) for element in entities if element.tag=='entity']
        seen=set()
        for index,item in enumerate(result):
            key=item.get('id') or f'authored-{area_id}-{index}'
            if key in seen:key=f'authored-{area_id}-{index}'
            item['id']=key;seen.add(key)
        return result

    def bridge(self, tutorial:dict, now:int|None=None)->dict:
        at=int(time.time()) if now is None else now
        scenario=next((v for v in self.defs.rows('scenario') if v.get('serverScenarioId')=='2'),None)
        if not scenario:raise ValueError('Original normal scenario definition missing')
        area=next((v for v in self.defs.rows('area') if v.get('scenario')==scenario['id']),None)
        if not area:raise ValueError('Original starting area definition missing')
        steps=self.defs.rows('seq_state_tablet_ftue')
        start=next(i for i,row in enumerate(steps) if row['persist']=='410')
        locations={};camera=None
        for step in steps[start:start+30]:
            raw=step.get('dataJSON','')
            data=json.loads(raw) if raw.startswith('{') else {}
            if step['sequenceType']=='51':
                locations[data['villagerRefId']]={'x':int(data['x']),'y':int(data['y']),
                                                   'areaId':int(area['id']),'rotation':0}
            if step['sequenceType']=='0' and camera is None:
                camera={'x':int(data['x']),'y':int(data['y']),'zoom':1}
        actors=[]
        variations={v['id']:v for v in self.defs.rows('villager_starting_variation')}
        types=self.defs.rows('villager_type')
        for person in tutorial['userHash']['data']['villagers']:
            ref=person['refId']
            if ref not in locations:continue
            source=variations[str(person['variationId'])]
            gender=int(source['Gender']);age=int(source['startAge'])
            kind=next((v for v in types if int(v['genderType'])==gender and
                       int(v.get('isPregnant','0'))==0 and
                       int(v['minAge'])<=age<=int(v['maxAge'])),None)
            if kind is None:raise ValueError('Missing original villager life-stage definition')
            actors.append({'id':person['id'],'refId':ref,'name':person['name'],
                'templateType':'villager_type','templateId':int(kind['id']),
                'serverPersisted':True,'villagerBaseId':int(source['id']),
                'startingArea':int(area['id']),'birthType':0,
                'specialType':int(source.get('SpecialType','0')),
                'energyLevel':int(kind['maxEnergy']),'energyTimeStamp':at,
                'startAge':age,'bornAt':at,'updatedAt':at,'pregnant':'false',
                'pregnancyTryCount':0,'pregnancyStartTime':0,'gender':gender,
                'xp':int(source.get('Xp','0')),'rarity':0,'shelterBedId':'',
                'position':locations[ref],'equipment':source['equipment'],
                'genetics':source['genetics'],'relations':[],'skills':[],
                'wants':[],'clothing':[],'isCommunityVillager':'false',
                'retireAt':0,'retireEventID':0})
        by_ref={v['refId']:v for v in actors}
        for actor in actors:
            ref=actor['refId']
            if ref in {'steve','jill'}:
                other='jill' if ref=='steve' else 'steve'
                if other in by_ref:actor['relations'].append({'villagerId':by_ref[other]['id'],'type':2})
            if ref in {'baby male','baby female'}:
                for parent in ('jill','steve'):
                    if parent in by_ref:
                        actor['relations'].append({'villagerId':by_ref[parent]['id'],'type':0})
        inventory={}
        for step in steps[:start]:
            if step['sequenceType']=='64':
                inventory.update({str(k):int(v) for k,v in json.loads(step['dataJSON']).get('inventory',{}).items()})
        entities=json.loads(scenario['clientData'])
        if not isinstance(entities,list):raise ValueError('Original scenario entities expected')
        for index,e in enumerate(entities):
            e['id']=str(e.get('id') or f'scene-2-{index}')
        entities+=actors
        seen={str(e['id']) for e in entities}
        for i,e in enumerate(self.authored(int(area['id']))):
            if e['templateType']=='villager_type' or e['id'] in seen:continue
            entities.append(e);seen.add(e['id'])
        level=self.defs.item('user_level',0)
        state={'schemaVersion':3,'revision':1,'transitionKey':'bridge-1-to-2',
               'scenarioId':2,'areaId':int(area['id']),'areaName':area['name'],
               'createdAt':at,'updatedAt':at,
               'world':{'camera':camera,'entities':entities},'inventory':inventory,
               'user':{'name':'Local Village','firstname':'Local',
                       'userLevel':int(level['levelNumber']),
                       'userLevelID':int(level['levelNumber']),
                       'xp':0,'populationCap':int(level['populationCap']),
                       'scenarioId':2,'maxAreaId':int(area['id']),
                       'segmentId':0,'isBuyer':False,'lastLoginAt':at,
                       'loginAt':at,'NextDailySpinAt':0,'NextDailySpinIncrement':0},
               'quests':[],'bundles':[],'payments':[],
               'rules':{'bridge_seed':{'evidence':'Original scenario data, FTUE 410 positions',
                                        'status':'partial-reconstruction'},
                        'building_production':{'status':'not-implemented'},
                        'riverside_mountain':{'status':'not-fully-implemented'}}}
        return state

    def startup(self, world: dict, at:int) -> dict:
        output=copy.deepcopy(world['world'])
        output['entities']=[entity for entity in output['entities'] if self._area(entity)==world['areaId']]
        return {'world':output,'user':{**world['user'],'loginAt':at},
                'OfflineConsumptionMessageModel':[]}

    def area_content(self, world:dict, area_id:int, at:int)->dict:
        if type(area_id) is not int or area_id!=world['areaId']:
            raise NotImplementedError('Other area content needs verified original state projection')
        entities=[copy.deepcopy(e) for e in world['world']['entities']
                  if e.get('serverPersisted') and self._area(e)==area_id]
        from .work import OriginalWorkRules
        entities+=OriginalWorkRules(self.defs).overlay(world,at)
        entities=[e for e in entities if self._area(e)==area_id]
        return {'areaJson':{'entities':entities},'user':dict(world['user'])}
