"""Original area RPCs, authored worlds and save-preserving local transfers."""
import copy,json
import world,habitats,family
SERVICES={'ClientUserService/UnlockArea','ClientVillagerService/MoveVillagers'}
MARKERS={1:'231',2:'232',3:'1536'}

def destination(state,value):
 if isinstance(value,bool) or not str(value).isdigit() or int(value) not in MARKERS:raise ValueError('Supported area1,2 or3 required')
 return int(value)

def seed(state,ident,at):
 initialized=state.setdefault('initializedAreas',[1])
 if ident in initialized:return False
 original=world.by_id('scenario',world.by_id('area',ident)['scenario'])
 # The client builds static scenery itself on area access. Retain clientData
 # for full startup too, then replace matching persistent authored records.
 values=json.loads(original['clientData']);authored=world.authored_area_entities(ident)
 authored_by_id={e['id']:e for e in authored};seen={e['id'] for e in state['world']['entities']};new=[]
 for index,value in enumerate(values):
  value=copy.deepcopy(value);raw=str(value.get('id') or ('scene-area'+str(ident)+'-'+str(index)))
  if raw in authored_by_id:continue
  value['id']=raw
  if raw in seen:value.update(originalSeedId=raw,id='local-area'+str(ident)+'-scene-'+str(index))
  value.setdefault('position',value.pop('posiiton',{}))['areaId']=ident
  seen.add(value['id']);new.append(value)
 for index,value in enumerate(authored):
  value=copy.deepcopy(value);raw=value['id']
  if raw in seen:value.update(originalSeedId=raw,id='local-area'+str(ident)+'-persistent-'+str(index))
  value.setdefault('position',{})['areaId']=ident
  seen.add(value['id']);habitats.initialize(value,at);new.append(value)
 state['world']['entities']+=new;initialized.append(ident)
 return True

def unlock(state,data,at):
 ident=destination(state,data.get('areaId'));maximum=int(state['user'].get('maxAreaId',1))
 if ident<=maximum:
  changed=seed(state,ident,at)
 else:
  if ident!=maximum+1:raise ValueError('Unlock the preceding area first')
  marker=world.by_id('material_type',MARKERS[ident])
  if state['user']['userLevelID']<int(marker['unlockLevel']):raise ValueError('Village level is too low for this area')
  seed(state,ident,at);state['user']['maxAreaId']=ident;changed=True
 if changed:state['revision']+=1
 import tasks
 return {'userArea':{'areaId':ident},'user':dict(state['user']),'inventory':tasks.inventory(state)},changed

def view(state,ident,at):
 ident=destination(state,ident)
 if ident>int(state['user'].get('maxAreaId',1)):raise ValueError('Area has not been unlocked')
 changed=seed(state,ident,at)
 if state['areaId']!=ident:
  state['areaId']=ident;state['areaName']=world.by_id('area',ident)['name']
  scenario=world.by_id('scenario',world.by_id('area',ident)['scenario'])
  state['user']['scenarioId']=int(scenario['serverScenarioId']);changed=True
 if changed:state['revision']+=1
 return changed

def move(state,data,at,key,owner):
 if not key:raise ValueError('Transfer receipt required')
 ident=destination(state,data.get('areaId'))
 if ident>int(state['user'].get('maxAreaId',1)):raise ValueError('Destination has not been unlocked')
 values=data.get('villagerIds')
 if not isinstance(values,list) or not 1<=len(values)<=100:raise ValueError('Owned villager list required')
 registry=state.get('nativeIdentityIds',{}).get(str(owner),{})
 inward={'Villager_'+str(owner)+'_'+raw:canonical for canonical,raw in registry.items()}
 raw_in={raw:canonical for canonical,raw in registry.items()}
 ids=[inward.get(str(v),raw_in.get(str(v),str(v))) for v in values]
 if len(ids)!=len(set(ids)):raise ValueError('Duplicate transfer villager')
 signature=json.dumps({'ids':ids,'areaId':ident},sort_keys=True)
 previous=state.get('areaMoveReceipts',{}).get(key)
 if previous:
  if previous!=signature:raise ValueError('Transfer receipt reused')
  return {},False
 people=[family.actor(state,i) for i in ids]
 for person in people:
  if any(j['villagerId']==person['id'] and j['status']!='harvested' for j in state.get('workAreas',{}).values()):raise ValueError('Collect existing work before moving this villager')
  if any(e.get('lightingVillagerId')==person['id'] and e.get('lightingCompleteAt',0)>at for e in state['world']['entities']):raise ValueError('Villager is lighting a fire')
 seed(state,ident,at)
 arrival=next((e['position'] for e in state['world']['entities'] if world.entity_area(e)==ident and e['templateType']=='workshop'),{'x':1800,'y':3100,'areaId':ident,'rotation':0})
 for index,person in enumerate(people):
  if world.entity_area(person)==ident:continue
  bed_id=person.get('shelterBedId')
  if bed_id:
   home,bed=habitats.bed(state,bed_id);bed['villagerId']=''
   if not any(b.get('villagerId') for b in home['beds']):home['happinessCollectedAt']=0
  person.update(shelterBedId='',position={**arrival,'areaId':ident,'x':arrival['x']+40*(index+1)},updatedAt=at)
 state.setdefault('areaMoveReceipts',{})[key]=signature;state['revision']+=1
 world.validate_world(state)
 return {},True
