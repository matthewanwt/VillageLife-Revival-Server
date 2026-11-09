"""Versioned world construction from original data, with explicit inferred rules."""
from pathlib import Path
from contextlib import closing
from functools import lru_cache
import sqlite3,json,copy,math,collections
import xml.etree.ElementTree as ET
DATABASE=Path(__file__).resolve().parents[1]/'analysis/private/game_tables.sqlite'

@lru_cache(maxsize=None)
def raw_rows(table):
 with closing(sqlite3.connect('file:'+str(DATABASE)+'?mode=ro',uri=True)) as conn:
  return tuple(v[0] for v in conn.execute('select fields_json from game_rows r join game_tables t on r.table_id=t.id where t.name=? order by r.ordinal',(table,)))
@lru_cache(maxsize=None)
def _parsed_rows(table):
 # Authored database records contain scalar fields. Keep parsed data private and
 # return independent records so callers cannot alter shared definitions.
 values=tuple(json.loads(v) for v in raw_rows(table))
 if any(isinstance(x,(dict,list)) for row in values for x in row.values()):raise ValueError('Nested authored table fields require deep-copy handling')
 return values

def rows(table):return [dict(v) for v in _parsed_rows(table)]
@lru_cache(maxsize=None)
def _id_index(table):
 index={}
 for record in _parsed_rows(table):
  if 'id' in record:index.setdefault(record['id'],record)
 return index

def by_id(table,ident):
 value=_id_index(table).get(str(ident))
 if value is None:raise StopIteration
 return dict(value)
@lru_cache(maxsize=None)
def global_value(label):return next(v['value'] for v in rows('global') if v['label']==label)
def current_age(character,at):
 seconds_per_year=float(global_value('hours_per_year'))*3600
 return character['startAge']+max(0,at-character['bornAt'])/seconds_per_year

def current_villager_type(character,at):
 """Resolve ordinary life stages from original age/gender/pregnancy definitions.
 Cached templateId is a spawn snapshot; the native client ages independently.
 Special infant forms retain their own template while within its age range.
 """
 cached=by_id('villager_type',character['templateId']);age=int(current_age(character,at))
 if cached['name']=='Dog Villager':return cached
 if int(cached['id'])>=20 and int(cached['minAge'])<=age<=int(cached['maxAge']):return cached
 gender=int(character.get('gender',cached['genderType']));pregnant='1' if str(character.get('pregnant','false')).lower() in {'true','1'} else '0'
 candidates=[v for v in _parsed_rows('villager_type') if int(v['id'])<=19 and int(v['genderType'])==gender and int(v['minAge'])<=age<=int(v['maxAge']) and v['isPregnant']==pregnant]
 if not candidates:return cached # Unknown special/unsupported lifecycle remains explicit in its cached class.
 return dict(candidates[0])

def can_work(character,at,task=None):
 definition=current_villager_type(character,at)
 if definition['canWork']!='1':return False
 return not task or not any(v['villagerType']==definition['id'] and v['villagerSet']==task.get('excludeVillagerSet','0') for v in rows('villager_set_item'))

def relation_context(state):
 # CreateXMLVillager stores relation.type directly as a relation_type row ID.
 # Canonical saves use Relationship groups0..4. Convert on the wire only.
 people={p['id']:p for p in state['world']['entities'] if p['templateType']=='villager_type'}
 people.update(state.get('externalVillagers',{}))
 kinds={(int(r['Relationship']),int(r['genderTypeId'])):int(r['id']) for r in rows('relation_type')}
 return people,kinds

def native_relations(state,person,context=None):
 if not person.get('relations'):return []
 people,kinds=relation_context(state) if context is None else context
 return [{'villagerId':r['villagerId'],'type':kinds[int(r['type']),int(people[r['villagerId']]['gender'])]} for r in person.get('relations',[])]

def validate_world(state):
 entities=state['world']['entities'];ids=[v['id'] for v in entities]
 if not all(isinstance(v,str) and v for v in ids) or len(ids)!=len(set(ids)):raise ValueError('World entity IDs must be distinct and non-empty')
 actors=[v for v in entities if v['templateType']=='villager_type'];actor_ids={v['id'] for v in actors}
 for actor in actors:
  if not math.isfinite(actor['position']['x']) or not math.isfinite(actor['position']['y']):raise ValueError('Invalid character position')
  if actor['startAge']<0 or actor['energyLevel']<0:raise ValueError('Invalid character attributes')
  for relation in actor['relations']:
   if relation['villagerId'] not in actor_ids:
    external=state.get('externalVillagers',{}).get(relation['villagerId'])
    if not external or int(relation['type'])!=4 or external.get('ownerKind')!='npc' or external['id']!=relation['villagerId'] or not any(p==external for p in state.get('npcDatingPool',[])) or not any(r['villagerId']==actor['id'] and int(r['type'])==4 for r in external['relations']):raise ValueError('Dangling family reference')
 for entity in entities:
  for bed in entity.get('beds',[]):
   if bed.get('villagerId') and bed['villagerId'] not in actor_ids:raise ValueError('Dangling bed reference')
 beds={}
 for item in entities:
  if item['templateType']=='shelter':
   for bed in item.get('beds',[]):
    if not isinstance(bed.get('id'),str) or not bed['id'] or bed['id'] in beds:raise ValueError('Bed IDs must be distinct and non-empty')
    beds[bed['id']]=bed
 for person in actors:
  ident=person.get('shelterBedId')
  if ident and (ident not in beds or beds[ident].get('villagerId')!=person['id']):raise ValueError('Dangling or inconsistent villager bed reference')
 for ident,bed in beds.items():
  occupant=bed.get('villagerId')
  if occupant and next(v for v in actors if v['id']==occupant).get('shelterBedId')!=ident:raise ValueError('Inconsistent bed occupant')
 active_actors=set();active_sources=set()
 for ident,job in state.get('workAreas',{}).items():
  if job['id']!=ident or job['villagerId'] not in actor_ids:raise ValueError('Invalid work identity or villager reference')
  if job['completionTime']<job['createdAt']:raise ValueError('Invalid work timer')
  if job['status'] not in {'working','ready','harvested'}:raise ValueError('Unknown work state')
  if job['status']=='harvested':continue
  if (job['sourceId'] not in ids and job.get('sourceSnapshot',{}).get('id')!=job['sourceId']) or (job['status']=='working' and job['villagerId'] in active_actors):raise ValueError('Dangling source or villager assigned twice')
  if job.get('family','3')!='1' and job['sourceId'] in active_sources:raise ValueError('Exclusive source assigned twice')
  if job['status']=='working':active_actors.add(job['villagerId'])
  active_sources.add(job['sourceId'])
 if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in state['inventory'].values()):raise ValueError('Inventory must be finite nonnegative numbers')

def authored_area_entities(area_id=1):
 scenario=by_id('scenario',by_id('area',area_id)['scenario'])
 def convert(element):
  if list(element):
   value=dict(element.attrib)
   for child in element:value[child.tag]=convert(child)
   return value
  text=(element.text or '').strip()
  if element.tag in {'x','y','rotation','amount','areaId'}:
   number=float(text or 0);return int(number) if number.is_integer() else number
  return text
 result=[]
 for entity in ET.fromstring(scenario['data']).find('entities'):
  if entity.tag!='entity':continue
  value=convert(entity);value['templateId']=int(value['templateId']);value['serverPersisted']=True
  result.append(value)
 counts=collections.Counter(v['id'] for v in result)
 for index,value in enumerate(result):
  if counts[value['id']]>1:
   value['originalSeedId']=value['id'];value['id']='local-area'+str(area_id)+'-authored-'+str(index)
 return result

def apply_authored_start(state):
 """Recover omitted server-authored area objects and required initial age classes."""
 seed=authored_area_entities();existing={v['id'] for v in state['world']['entities']}
 for entity in seed:
  if entity['templateType']!='villager_type' and entity['id'] not in existing:
   state['world']['entities'].append(entity);existing.add(entity['id'])
 expected={v['refId']:v for v in seed if v['templateType']=='villager_type'}
 for actor in state['world']['entities']:
  if actor['templateType']!='villager_type' or actor.get('refId') not in expected:continue
  source=next(v for v in rows('villager_starting_variation') if v['id']==str(actor.get('villagerBaseId')))
  typ=by_id('villager_type',expected[actor['refId']]['templateId'])
  actor['startAge']=min(max(int(source['startAge']),int(typ['minAge'])),int(typ['maxAge']))
  actor['templateId']=int(typ['id']);actor['energyLevel']=min(actor['energyLevel'],int(typ['maxEnergy']))
 state.setdefault('rules',{}).pop('parent_age_jump',None)
 state['rules']['authored_area_objects']={'evidence':'original scenario serverScenarioId=2/data XML; all 62 non-character objects','status':'original_authored_seed'}
 state['rules']['starting_age_classes']={'evidence':'same XML character templateIds; villager_type age bounds','status':'reconstructed','inference':'chosen variation age clamped to authored template range; retained IDs, names and appearance'}
 validate_world(state)


def build_bridge_world(tutorial,at):
 """Construct a reviewable first-world state; assumptions travel with the save."""
 scenario=next(v for v in rows('scenario') if v['serverScenarioId']=='2')
 area=next(v for v in rows('area') if v['scenario']==scenario['id'])
 steps=rows('seq_state_tablet_ftue')
 start=next(i for i,v in enumerate(steps) if v['persist']=='410')
 positions={};camera=None
 for step in steps[start:start+30]:
  data=json.loads(step['dataJSON']) if step['dataJSON'].startswith('{') else {}
  if step['sequenceType']=='51':positions[data['villagerRefId']]={'x':int(data['x']),'y':int(data['y']),'areaId':int(area['id']),'rotation':0}
  if step['sequenceType']=='0' and camera is None:camera={'x':int(data['x']),'y':int(data['y']),'zoom':1}
 identities=tutorial['userHash']['data']['villagers']
 actors=[]
 for identity in identities:
  ref=identity['refId']
  if ref not in positions:continue
  source=by_id('villager_starting_variation',identity['variationId'])
  gender=int(source['Gender']);age=int(source['startAge'])
  typ=next(v for v in rows('villager_type') if int(v['genderType'])==gender and int(v.get('isPregnant','0'))==0 and int(v['minAge'])<=age<=int(v['maxAge']))
  actor={'id':identity['id'],'refId':ref,'name':identity['name'],'templateType':'villager_type','templateId':int(typ['id']),'serverPersisted':True,'villagerBaseId':int(source['id']),'startingArea':int(area['id']),'birthType':0,'specialType':int(source.get('SpecialType','0')),'energyLevel':int(typ['maxEnergy']),'energyTimeStamp':at,'startAge':age,'bornAt':at,'updatedAt':at,'pregnant':'false','pregnancyTryCount':0,'pregnancyStartTime':0,'gender':gender,'xp':int(source.get('Xp','0')),'rarity':0,'shelterBedId':'','position':positions[ref],'equipment':source['equipment'],'genetics':source['genetics'],'relations':[],'skills':[],'wants':[],'clothing':[],'isCommunityVillager':'false','retireAt':0,'retireEventID':0}
  actors.append(actor)
 mapping={v['refId']:v['id'] for v in actors}
 for actor in actors:
  ref=actor['refId']
  if ref in {'steve','jill'}:
   spouse='jill' if ref=='steve' else 'steve'
   actor['relations'].append({'villagerId':mapping[spouse],'type':2})
  elif ref in {'baby male','baby female'}:
   actor['relations'] += [{'villagerId':mapping['jill'],'type':0},{'villagerId':mapping['steve'],'type':0}]
 inventory={}
 for step in steps[:start]:
  if step['sequenceType']=='64':
   inventory.update({str(k):int(v) for k,v in json.loads(step['dataJSON']).get('inventory',{}).items()})
 entities=json.loads(scenario['clientData'])
 for index,entity in enumerate(entities):
  if not entity.get('id'):entity['id']='scene-2-'+str(index)
  elif not isinstance(entity['id'],str):entity['id']=str(entity['id'])
 entities+=actors
 level=by_id('user_level',0)
 state={'schemaVersion':2,'revision':1,'transitionKey':'bridge-1-to-2','scenarioId':2,'areaId':int(area['id']),'areaName':area['name'],'createdAt':at,'updatedAt':at,'world':{'camera':camera,'entities':entities},'inventory':inventory,'user':{'name':'Local Village','firstname':'Local','userLevel':int(level['levelNumber']),'userLevelID':int(level['levelNumber']),'xp':0,'populationCap':int(level['populationCap']),'scenarioId':2,'maxAreaId':int(area['id']),'segmentId':0,'isBuyer':False,'lastLoginAt':at,'loginAt':at,'NextDailySpinAt':0,'NextDailySpinIncrement':0},'quests':[],'bundles':[],'payments':[],'rules':{'hours_per_year':{'value':int(global_value('hours_per_year')),'evidence':'packaged global.hours_per_year'},'starting_world':{'evidence':'packaged scenario.serverScenarioId=2/clientData and area relation'},'spawn_positions':{'evidence':'original sequenceType=51 following persist checkpoint 410'},'character_ids':{'evidence':'preserved from validated tutorial state'},'initial_inventory':{'status':'inferred','reason':'original explicit sequenceType=64 assignments; unrecorded gathering/consumption is not recoverable yet'},'villager_base_id':{'status':'inferred','reason':'uses original starting-variation row ID; requires runtime verification'},'anonymous_scene_ids':{'status':'local_identity_policy','reason':'stable scene/index IDs for original nonpersistent objects without IDs'},'offline_simulation':{'status':'not_implemented'}}}
 apply_authored_start(state)
 repair_starter_family(state)
 state['schemaVersion']=3
 import habitats
 habitats.migrate(state,at)
 validate_world(state)
 return state

def startup(state,at):
 validate_world(state)
 # The original parser explicitly finds user; world is first for WorldModelInit.
 projected=copy.deepcopy(state['world'])
 projected['entities']=[e for e in projected['entities'] if entity_area(e)==state['areaId']]
 relations=relation_context(state)
 for entity in projected['entities']:
  import placement
  placement.project_position(entity)
  if entity['templateType']=='villager_type':
   entity['templateId']=int(current_villager_type(entity,at)['id']);entity['pregnant']=int(str(entity.get('pregnant','false')).lower() in {'true','1'});entity['relations']=native_relations(state,entity,relations)
 return {'world':projected,'user':{**state['user'],'loginAt':at},'OfflineConsumptionMessageModel':[]}


def entity_area(entity):return int(entity.get('position',entity.get('posiiton',{})).get('areaId',1))

def area_content(state,area_id,at=None):
 if isinstance(area_id,bool) or not isinstance(area_id,int) or area_id!=state['areaId']:raise ValueError('Unknown local area')
 validate_world(state)
 import time
 at=int(time.time()) if at is None else at
 # LoadMyWorld first builds the original static scenario locally, then overlays
 # areaJson.entities. Return saved actors/resources/structures, excluding static scenery.
 entities=[copy.deepcopy(v) for v in state['world']['entities'] if v.get('serverPersisted') and entity_area(v)==area_id]
 # Mode 2 in LoadMyWorld skips authored objects marked serverPersisted=true.
 # Keep canonical persistence on disk, project renderable authored templates.
 authored_ids={v['id'] for v in authored_area_entities(area_id) if v['templateType']!='villager_type'}
 relations=relation_context(state)
 for entity in entities:
  import placement
  placement.project_position(entity)
  if entity['templateType']=='villager_type':
   entity['templateId']=int(current_villager_type(entity,at)['id']);entity['pregnant']=int(str(entity.get('pregnant','false')).lower() in {'true','1'});entity['relations']=native_relations(state,entity,relations)
  if entity['id'] in authored_ids or entity.get('localCreated'):entity['serverPersisted']=False
  if entity['templateType']=='shelter':
   # WorldModelUpdate in JSON overlay mode descends an extra child per bed.
   # Harvest completion uses flat bed records; keep canonical save records flat.
   entity['beds']=[{'bed':value} for value in entity.get('beds',[])]
 import tasks
 entities+=[e for e in tasks.work_overlay(state,at) if entity_area(e)==area_id]
 return {'areaJson':{'entities':entities},'user':dict(state['user'])}


def migrate_level_numbers(state):
 """Repair schema-1 row-ID zero, retaining all progress and character state."""
 if state.get('schemaVersion',1)!=1:return False
 user=state['user']
 if user.get('userLevel')==0 and user.get('userLevelID')==0:
  level=by_id('user_level',0)
  user.update(userLevel=int(level['levelNumber']),userLevelID=int(level['levelNumber']),populationCap=int(level['populationCap']))
  state.setdefault('rules',{})['wire_level']={'evidence':'UserLevelDBVO stores levelNumber at +4; ShrineDisplay compares userLevelID against that field','tableRowId':0,'levelNumber':int(level['levelNumber'])}
 state['schemaVersion']=2
 state['revision']+=1
 return True


def migrate_authored_area(state):
 if state.get('schemaVersion',1)>=3:return False
 apply_authored_start(state)
 state['schemaVersion']=3;state['revision']+=1
 return True


def repair_starter_family(state):
 """Remove the old blanket-parent assumption; preserve genuine later births.
 Original FTUE204/216/217 identifies only the two babies as this couple's
 children. FTUE330 and dialogue33..35 introduce the other two as newcomers.
 Their mutual parentage is not established in the shipped records.
 """
 people=[p for p in state['world']['entities'] if p['templateType']=='villager_type']
 refs={p.get('refId'):p for p in people if p.get('refId')}
 parents={refs[r]['id'] for r in ['steve','jill'] if r in refs}
 newcomers={refs[r]['id'] for r in ['brother','sister'] if r in refs and not refs[r].get('familyBirthId')}
 by_id={p['id']:p for p in people};changed=False
 children={p['id'] for p in people if any(int(r['type'])==0 and r['villagerId'] in parents for r in p.get('relations',[]))}-newcomers
 for person in people:
  kept=[]
  for relation in person.get('relations',[]):
   other=relation['villagerId'];kind=int(relation['type']);ident=person['id']
   invalid=(ident in newcomers and other in parents and kind==0) or (ident in parents and other in newcomers and kind==1)
   invalid=invalid or (kind==3 and ((ident in newcomers and other in children) or (other in newcomers and ident in children)))
   if invalid:changed=True
   else:kept.append(relation)
  person['relations']=kept
 for ref in ['baby male','baby female']:
  child=refs.get(ref)
  if not child:continue
  for parent_id in parents:
   parent=by_id[parent_id]
   for person,other,kind in [(child,parent,0),(parent,child,1)]:
    if not any(r['villagerId']==other['id'] and int(r['type'])==kind for r in person['relations']):person['relations'].append({'villagerId':other['id'],'type':kind});changed=True
 if 'baby male' in refs and 'baby female' in refs:
  for a,b in [('baby male','baby female'),('baby female','baby male')]:
   if not any(r['villagerId']==refs[b]['id'] and int(r['type'])==3 for r in refs[a]['relations']):refs[a]['relations'].append({'villagerId':refs[b]['id'],'type':3});changed=True
 if changed:state['revision']+=1
 return changed
