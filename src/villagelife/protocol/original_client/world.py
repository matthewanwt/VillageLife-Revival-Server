"""Source-derived first normal world. Does not invent ongoing production rules.

The original client seeds scenery from packaged scenario data and overlays
server-persisted entities. This reconstructs only the documented bridge from
FTUE checkpoint 217 into scenario 2 (area 1).
"""
from __future__ import annotations
import copy
import json
import time
from functools import cached_property
import xml.etree.ElementTree as ET
from .birth_skills import skill_type
from .catalog import OriginalDefinitions

class OriginalWorldRules:
    def __init__(self, definitions: OriginalDefinitions):self.defs=definitions

    @cached_property
    def global_values(self) -> dict[str, str]:
        return {row['label']:row['value'] for row in self.defs.rows('global')}

    def global_value(self, label: str) -> str:
        if label not in self.global_values:
            raise KeyError(f'Missing original global {label}')
        return self.global_values[label]

    @cached_property
    def ordinary_villager_types(self) -> list[dict]:
        return [row for row in self.defs.rows('villager_type') if int(row['id']) <= 19]

    @cached_property
    def seconds_per_year(self) -> int:
        return int(float(self.global_value('hours_per_year')) * 3600)

    def current_age(self, character: dict, at: int) -> float:
        elapsed = max(0, at - int(character.get('bornAt', at)))
        return float(character.get('startAge', 0)) + elapsed / self.seconds_per_year

    def current_villager_type(self, character: dict, at: int) -> dict:
        cached = self.defs.item('villager_type', character['templateId'])
        if 'startAge' not in character or 'bornAt' not in character:
            return cached
        age = int(self.current_age(character, at))
        if cached.get('name') == 'Dog Villager':
            return cached
        if (int(cached['id']) >= 20 and
                int(cached['minAge']) <= age <= int(cached['maxAge'])):
            return cached
        gender = int(character.get('gender', cached['genderType']))
        pregnant = '1' if str(character.get('pregnant', 'false')).lower() in {'true', '1'} else '0'
        return next((row for row in self.ordinary_villager_types
                     if int(row['genderType']) == gender
                     and int(row['minAge']) <= age <= int(row['maxAge'])
                     and row.get('isPregnant', '0') == pregnant), cached)

    def can_work(self, character: dict, at: int, task: dict | None = None) -> bool:
        kind=self.current_villager_type(character,at)
        if kind.get('canWork')!='1':return False
        if task is None:return True
        excluded=task.get('excludeVillagerSet','0')
        return not (excluded not in {'0',''} and any(
            row.get('villagerType')==str(kind.get('id', character['templateId'])) and
            row.get('villagerSet')==excluded
            for row in self.defs.rows('villager_set_item')))

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

    def reconcile_authored(self, state: dict, area_id: int, at: int) -> bool:
        """Backfill missing server-authored objects in an existing saved area.

        Older local saves may have been created before the full authored area
        seed was available. Preserve existing entities and player placements;
        only restore missing, authored non-villager IDs.
        """
        world = state.get('world')
        entities = world.get('entities') if isinstance(world, dict) else None
        if not isinstance(entities, list):
            return False
        existing = {str(entity.get('id')) for entity in entities if isinstance(entity, dict)}
        changed = False
        deleted_foundations = set(state.get('deletedFoundations', []))
        deleted_foundations.update(job.get('sourceId')
                                   for job in state.get('workAreas', {}).values()
                                   if job.get('family') == '2' and job.get('status') == 'harvested')
        for entity in self.authored(area_id):
            ident = str(entity.get('id', ''))
            if (not ident or ident in existing or ident in deleted_foundations
                    or entity.get('templateType') == 'villager_type'
                    or self._area(entity) != area_id):
                continue
            entities.append(copy.deepcopy(entity))
            existing.add(ident)
            changed = True
        if changed:
            state['revision'] = int(state.get('revision', 0)) + 1
            state['updatedAt'] = at
        return changed

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
        grant = tutorial.get('startingGemGrant')
        if type(grant) is int and grant > 0:
            inventory['323'] = grant
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
        if type(grant) is int and grant > 0:
            state['startingGemsGranted'] = grant
        return state

    def project_relations(self, state: dict, entities: list[dict]) -> None:
        people = {p['id']: p for p in state['world']['entities'] if p.get('templateType') == 'villager_type'}
        people.update(state.get('externalVillagers', {}))
        if not any(e.get('relations') for e in entities if e.get('templateType') == 'villager_type'):
            return
        kinds = {(int(row['Relationship']), int(row['genderTypeId'])): int(row['id'])
                 for row in self.defs.rows('relation_type')}
        for entity in entities:
            if entity.get('templateType') != 'villager_type':
                continue
            links = []
            for relation in entity.get('relations', []):
                ident = relation['villagerId']
                relative = people.get(ident)
                if relative is not None:
                    kind = kinds.get((int(relation['type']), int(relative.get('gender', 0))))
                    if kind is not None:
                        links.append({'villagerId': ident, 'type': kind})
            entity['relations'] = links

    @staticmethod
    def project_skills(entities: list[dict]) -> None:
        # CreateXMLVillager expects type here. The standalone skill lookup
        # uses skilltypeId and the birth listener uses SkillTypeID.
        for entity in entities:
            if entity.get('templateType') == 'villager_type' and entity.get('skills'):
                entity['skills'] = [{'type': skill_type(row), 'skillOriginType': int(row['skillOriginType'])}
                                    for row in entity['skills']]

    def project_life_stages(self, entities: list[dict], at: int) -> None:
        for entity in entities:
            if entity.get('templateType') != 'villager_type' or 'startAge' not in entity or 'bornAt' not in entity:
                continue
            try:
                kind = self.current_villager_type(entity, at)
            except KeyError:
                # Keep an unknown imported template available to the client.
                continue
            if int(kind['id']) != int(entity['templateId']):
                # CreateXMLVillager recalculates the model from startAge and
                # bornAt. Fold in elapsed whole years on the wire so a scene
                # reload uses the resolved age even while its clock syncs.
                starting_age = float(entity['startAge'])
                current_age = int(self.current_age(entity, at))
                entity['startAge'] = current_age
                entity['bornAt'] = int(entity['bornAt']) + round(
                    (current_age - starting_age) * self.seconds_per_year)
            entity['templateId'] = int(kind['id'])
            entity['pregnant'] = int(str(entity.get('pregnant', 'false')).lower() in {'true', '1'})

    def startup(self, world: dict, at:int) -> dict:
        output = {key: copy.deepcopy(value) for key, value in world['world'].items() if key != 'entities'}
        area_id = world['areaId']
        # The native startup parser builds the world-map roster from villager
        # records and reads each villager's own position.areaId. The later
        # scene overlay remains local to the map being viewed.
        output['entities'] = [copy.deepcopy(entity) for entity in world['world']['entities']
                              if entity.get('templateType') == 'villager_type' or self._area(entity) == area_id]
        if area_id != 1:
            # Later authored scenes have no XML camera. Center their saved
            # startup on the local shrine instead of reusing Woodland's camera.
            shrine = next((entity['position'] for entity in output['entities']
                           if entity.get('templateType') == 'shrine'), None)
            if shrine is not None:
                output['camera'] = {'x': shrine['x'], 'y': shrine['y'], 'zoom': 1}
        self.project_relations(world, output['entities'])
        self.project_life_stages(output['entities'], at)
        self.project_skills(output['entities'])
        return {'world':output,'user':{**world['user'],'loginAt':at},
                'OfflineConsumptionMessageModel':[]}

    def area_content(self, world:dict, area_id:int, at:int)->dict:
        if type(area_id) is not int or area_id!=world['areaId']:
            raise NotImplementedError('Other area content needs verified original state projection')
        # LoadMyWorld first creates the static scene from client assets. In its
        # mode-2 area overlay, serverPersisted=true means "already exists; skip
        # creation". Authored objects therefore need false in this wire copy,
        # while remaining true in the canonical saved world.
        authored_ids={entity['id'] for entity in self.authored(area_id)
                      if entity.get('templateType')!='villager_type'}
        # The original client matches villager IDs before creating them and
        # filters models by position.areaId in its area-only loading mode.
        # Send the full owned roster after travel so the move dialog can read
        # its source area. Terrain, structures and work stay area-local.
        entities = [copy.deepcopy(e) for e in world['world']['entities']
                    if e.get('serverPersisted') and
                    (e.get('templateType') == 'villager_type' or self._area(e) == area_id)]
        self.project_relations(world, entities)
        self.project_life_stages(entities, at)
        self.project_skills(entities)
        editable={'fun_building','container_type','workshop','fire_type','decor_item',
                  'material_source','shelter','farm_building','farming_plot','building_task','HuntingLodgeType','fishing_hut','fishing_boat','HuntingSledType'}
        for entity in entities:
            if entity['id'] in authored_ids or entity.get('originalSeedId') in authored_ids or entity.get('localCreated'):
                entity['serverPersisted']=False
            if entity.get('templateType') == 'shelter' and 'beds' in entity:
                # WorldModelUpdate descends one child per bed in area JSON.
                # Construction harvest uses flat rows, as does the save.
                entity['beds'] = [{'bed': bed} for bed in entity['beds']]
            if entity.get('templateType') in editable and isinstance(entity.get('position'),dict):
                entity['position']['id']=str(entity.get('positionId') or
                    entity['position'].get('id') or entity['id']+'-position')
        from .work import OriginalWorkRules
        entities += OriginalWorkRules(self.defs).overlay(world, at, area_id)
        return {'areaJson':{'entities':entities},'user':dict(world['user'])}
