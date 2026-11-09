"""Original foundation definitions and persistent placement transactions."""
import math,uuid,copy
import world
SUPPORTED_BUILD_KINDS={'fun_building','container_type','workshop','fire_type','decor_item','material_source','shelter','farm_building','farming_plot'}
def lookup(table,ident):
 try:return world.by_id(table,ident)
 except StopIteration:raise ValueError('Unknown '+table+' identifier') from None

def position(state,data):
 if isinstance(data.get('areaId'),bool) or data.get('areaId')!=state['areaId']:raise ValueError('Unknown placement area')
 if 'x' not in data or 'y' not in data:raise ValueError('Both placement coordinates are required')
 value={k:data.get(k,0) for k in ['x','y','rotation']}
 if any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) for v in value.values()):raise ValueError('Invalid placement coordinates')
 if not 0<=value['x']<=10000 or not 0<=value['y']<=10000:raise ValueError('Placement outside local world bounds')
 return {**value,'areaId':state['areaId']}

def placement_record(entity):
 import placement
 return {'userBuildingTaskId':entity['id'],'buildingTaskTypeId':entity['templateId'],'position':{**entity['position'],'id':placement.position_id(entity)}}

def place(state,data):
 raw=data.get('buildingTaskTypeId')
 if isinstance(raw,bool) or not str(raw).isdigit():raise ValueError('Invalid foundation type')
 definition=lookup('building_task',int(raw));pos=position(state,data)
 if definition['allowMultiple']=='0' and any(j['status']!='harvested' and j.get('sourceSnapshot',{}).get('templateId')==int(raw) for j in state.get('workAreas',{}).values()):raise ValueError('Building type is already under construction')
 for entity in state['world']['entities']:
  if entity['templateType']=='building_task' and entity['templateId']==int(raw):
   if entity['position']==pos:return {'userBuildingTask':placement_record(entity)},False
   if definition['allowMultiple']=='0':raise ValueError('Foundation type already placed')
 building=lookup('building_type',definition['buildingType'])
 if building['entityRef']=='farming_plot':
  # Reserve capacity for placed foundations as well as finished plots. The
  # original farm-house numPlots is the limit, not a fixed one-plot default.
  capacity=sum(int(lookup('farm_building',e['templateId'])['numPlots']) for e in state['world']['entities'] if e['templateType']=='farm_building' and e['position']['areaId']==pos['areaId'])
  used=sum(e['templateType']=='farming_plot' or (e['templateType']=='building_task' and lookup('building_type',lookup('building_task',e['templateId'])['buildingType'])['entityRef']=='farming_plot') for e in state['world']['entities'] if e.get('position',{}).get('areaId')==pos['areaId'])
  # Cancelled visual foundations may still have a paid job completing offscreen.
  ids={e['id'] for e in state['world']['entities']}
  used+=sum(j.get('family')=='2' and j['status']!='harvested' and j['sourceId'] not in ids and j.get('sourceSnapshot',{}).get('position',{}).get('areaId')==pos['areaId'] and lookup('building_type',lookup('building_task',j['sourceSnapshot']['templateId'])['buildingType'])['entityRef']=='farming_plot' for j in state.get('workAreas',{}).values())
  if used>=capacity:raise ValueError('Upgrade the farm house before adding another plot')
 existing=[e for e in state['world']['entities'] if e['templateType']==building['entityRef'] and e['templateId']==int(building['entityID'])]
 if definition['allowMultiple']=='0' and existing:
  # Authored storage objects already exist as native placeholders before the
  # first storage construction. Upgrade that object rather than duplicating it.
  placeholder=building['entityRef'] in {'container_type','workshop'} and len(existing)==1 and not existing[0].get('localCreated') and state['inventory'].get(building['materialType'],0)==0
  if not placeholder:raise ValueError('Building type already exists')
 entity={'id':'local-foundation-'+uuid.uuid4().hex,'templateType':'building_task','templateId':int(raw),'serverPersisted':True,'localCreated':True,'position':pos}
 state['world']['entities'].append(entity);state['revision']+=1
 return {'userBuildingTask':placement_record(entity)},True

def list_foundations(state):
 return {'userBuildingTasks':[placement_record(v) for v in state['world']['entities'] if v['templateType']=='building_task']}

def completion_definition(foundation):
 definition=lookup('building_task',foundation['templateId']);building=lookup('building_type',definition['buildingType'])
 if building['entityRef'] not in SUPPORTED_BUILD_KINDS:raise NotImplementedError('Building completion schema not recovered: '+building['entityRef'])
 lookup(building['entityRef'],building['entityID'])
 return building

def complete(state,job):
 foundation=next((v for v in state['world']['entities'] if v['id']==job['sourceId']),None) or job.get('sourceSnapshot')
 if foundation is None:raise ValueError('Missing saved foundation')
 upgrading=job.get('family')=='6';old=copy.deepcopy(foundation) if upgrading else None
 if upgrading:foundation={**foundation,'templateId':job['upgradeDefinitionId']}
 definition=completion_definition(foundation)
 entity={'id':'local-building-'+uuid.uuid4().hex,'templateType':definition['entityRef'],'templateId':int(definition['entityID']),'position':copy.deepcopy(foundation['position']),'serverPersisted':True,'localCreated':True,'sourceWorkAreaId':job['id']}
 if upgrading:
  entity.update(id=old['id'],position=copy.deepcopy(old['position']))
  previous=lookup('building_type',lookup('building_task',lookup('building_task',job['upgradeDefinitionId'])['parentId'])['buildingType'])
  key=previous['materialType']
  if key!=definition['materialType']:state['inventory'][key]=max(0,state['inventory'].get(key,0)-1)
 if entity['templateType'] in {'container_type','workshop'} and not upgrading:
  construction=lookup('building_task',foundation['templateId']);parent=construction['parentId']
  old_type=definition
  if parent!='-1':old_type=lookup('building_type',lookup('building_task',parent)['buildingType'])
  previous=[e for e in state['world']['entities'] if e['templateType']==entity['templateType'] and e['templateId']==int(old_type['entityID'])]
  if len(previous)>1:raise ValueError('Ambiguous storage upgrade target')
  if previous:
   old=previous[0];entity.update(id=old['id'],position=copy.deepcopy(old['position']))
   state['world']['entities']=[e for e in state['world']['entities'] if e['id']!=old['id']]
   if old_type['materialType']!=definition['materialType']:
    key=old_type['materialType'];state['inventory'][key]=max(0,state['inventory'].get(key,0)-1)
 entity['positionId']=old.get('positionId',old.get('position',{}).get('id',old['id']+'-position')) if old else foundation['id']+'-position'
 import fun
 fun.initialize(entity)
 import habitats
 if upgrading and entity['templateType']=='shelter':entity['beds']=copy.deepcopy(old.get('beds',[]))
 habitats.initialize(entity,job['completionTime'])
 if upgrading and entity['templateType']=='shelter':
  occupied=[b for b in old.get('beds',[]) if b.get('villagerId')]
  if len(occupied)>len(entity['beds']):raise ValueError('Upgraded shelter cannot hold its saved occupants')
  # Existing beds and their actor references retain their exact identities.
  entity['happinessCollectedAt']=old.get('happinessCollectedAt',entity['happinessCollectedAt'])
 state['world']['entities']=[v for v in state['world']['entities'] if v['id']!=foundation['id']]+[entity]
 result={'id':entity['id'],'entityId':entity['templateId']}
 if entity['templateType']=='shelter':
  import placement
  result.update(beds=copy.deepcopy(entity['beds']),happinessCollectedAt=entity['happinessCollectedAt'],position={**entity['position'],'id':placement.position_id(entity)})
 return [result]


def delete(state,data):
 ident=data.get('userBuildingTaskId')
 if not isinstance(ident,str) or not ident:raise ValueError('Foundation identifier required')
 if ident in state.get('deletedFoundations',[]):return {},False
 foundation=next((v for v in state['world']['entities'] if v['id']==ident and v['templateType']=='building_task'),None)
 if foundation is None:
  if any(j['sourceId']==ident and j.get('family')=='2' and j['status']=='harvested' for j in state.get('workAreas',{}).values()):
   state.setdefault('deletedFoundations',[]).append(ident);state['revision']+=1;return {},True
  raise ValueError('Unknown foundation')
 for job in state.get('workAreas',{}).values():
  if job['status']!='harvested' and job['sourceId']==ident:job['sourceSnapshot']=copy.deepcopy(foundation)
 state['world']['entities']=[v for v in state['world']['entities'] if v['id']!=ident]
 state.setdefault('deletedFoundations',[]).append(ident);state['revision']+=1
 return {},True


def delete_fun(state,data):
 ident=data.get('userFunBuildingTypeId')
 if not isinstance(ident,str) or not ident:raise ValueError('Fun building identifier required')
 if ident in state.get('deletedFunBuildings',[]):return {},False
 entity=next((v for v in state['world']['entities'] if v['id']==ident and v['templateType']=='fun_building'),None)
 if entity is None:raise ValueError('Unknown fun building')
 if any(j['status']!='harvested' and j['sourceId']==ident for j in state.get('workAreas',{}).values()):raise ValueError('Building is in use')
 definition=lookup('fun_building',entity['templateId']);material=str(definition['materialType'])
 state['world']['entities']=[v for v in state['world']['entities'] if v['id']!=ident]
 state['inventory'][material]=max(0,state['inventory'].get(material,0)-1)
 if not state['inventory'][material]:state['wants']=[v for v in state.get('wants',[]) if str(v['MaterialID'])!=material]
 state.setdefault('deletedFunBuildings',[]).append(ident);state['revision']+=1
 return {},True
