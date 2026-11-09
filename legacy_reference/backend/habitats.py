"""Recovered fire/shelter wire contracts and table rules, with explicit local policies."""
import copy,json,hashlib
from decimal import Decimal
import world
SHELTER_INTERVAL=86400 # Original Script2381 literal0x47a8c000; native UI shows24h.
# Screenshot-confirmed ordinary Woodland shelter capacities. Slot IDs are
# stable logical identifiers in the native bed records, not asset coordinates.
SHELTER_CAPACITIES={0:2,1:4,2:6,3:2,4:4,5:6,6:2,7:2}
SERVICES={'ClientUserFireService/StartFire','ClientUserFireService/OilFire','ClientUserShelterService/AssignBedToVillager','ClientUserShelterService/EmptyBed','ClientUserShelterService/CollectShelterHappiness','ClientUserShelterService/ResetHappinessTimer'}

def initialize(entity,at):
 changed=False
 if entity['templateType']=='fire_type':
  defaults={'isBurning':0,'startsAt':0,'endsAt':0,'oilAppliedAt':0}
 elif entity['templateType']=='shelter':
  defaults={'happinessCollectedAt':0,'beds':[]}
 else:return False
 for key,value in defaults.items():
  if key not in entity:entity[key]=value;changed=True
 if entity['templateType']=='shelter':
  capacity=SHELTER_CAPACITIES.get(entity['templateId'],2)
  # Append only. Keep existing IDs, occupancy, timestamps and any extra legacy
  # beds; migration must never evict someone from an existing save.
  while len(entity['beds'])<capacity:
   index=len(entity['beds']);slot=12+index
   used={b.get('shelterSlotID') for b in entity['beds']}
   while slot in used:slot+=1
   entity['beds'].append({'id':'local-bed-'+hashlib.sha256((entity['id']+':'+str(index)).encode()).hexdigest()[:24],'shelterSlotID':slot,'villagerId':''});changed=True
 return changed

def migrate(state,at):
 changed=False
 for entity in state['world']['entities']:changed=initialize(entity,at) or changed
 if changed:state.setdefault('rules',{})['habitats']={'contracts':'native StartFire/OilFire/AssignBedToVillager/EmptyBed and world fields','timers_costs_rewards':'original fire_task, task requirements/rewards, fire_type.oilQuantity, oilBurnDuration and shelter happiness tables','bed_layout':'Woodland shelter capacities match supplied native shop screenshots:2/4/6/2/4/6/2/2 by template0..7; stable logical slot IDs extend original legacy12/13 policy; other shelter capacities remain unverified','occupancy':'append missing slots without replacing existing bed IDs, occupants or happiness timer; never shrink an existing shelter'}
 return changed

def entity(state,ident,kind):
 if not isinstance(ident,str) or not ident:raise ValueError('Object identifier required')
 found=next((e for e in state['world']['entities'] if e['id']==ident and e['templateType']==kind),None)
 if found is None:raise ValueError('Unknown '+kind+' in this village')
 if found['position'].get('areaId',state['areaId'])!=state['areaId']:raise ValueError('Object is in another area')
 return found

def actor(state,ident):return entity(state,ident,'villager_type')

def inventory(state):
 import learning
 return learning.inventory(state)

def fire_response(state,fire):
 return {'userFire':{k:copy.deepcopy(fire[k]) for k in ['id','isBurning','startsAt','endsAt','oilAppliedAt']},'userMaterialTypes':inventory(state),'SatisfiedWantModels':[]}

def sync(state,at):
 changed=False
 for fire in state['world']['entities']:
  if fire['templateType']!='fire_type' or not fire.get('isBurning') or at<fire['endsAt']:continue
  fire['isBurning']=0
  # Treat deterministic task fire tokens as active-fire inventory, not permanent loot.
  for key,amount in fire.pop('activeReward',{}).items():state['inventory'][key]=max(0,state['inventory'].get(key,0)-amount)
  changed=True
 return changed

def spend(state,requirements):
 deductions={}
 for req in requirements:
  if req.get('villagers','undefined') not in {'undefined','0',''}:raise NotImplementedError('Additional villager requirement not recovered')
  key=req['materialType'];available=Decimal(str(state['inventory'].get(key,0)))
  if available<Decimal(req['quantity']):raise ValueError('Missing fire material: '+key)
  deductions[key]=deductions.get(key,Decimal(0))+Decimal(req['quantityUsed'])
 for key,amount in deductions.items():
  if Decimal(str(state['inventory'].get(key,0)))<amount:raise ValueError('Insufficient fire materials')
 for key,amount in deductions.items():state['inventory'][key]=float(Decimal(str(state['inventory'].get(key,0)))-amount)

def start_fire(state,data,at):
 fire=entity(state,data.get('userFireId'),'fire_type');person=actor(state,data.get('villagerId'))
 if not world.can_work(person,at):raise ValueError('Villager cannot light a fire at their current life stage')
 if fire['isBurning'] and at<fire['endsAt']:return fire_response(state,fire),False
 if any(j['villagerId']==person['id'] and j['status']=='working' and at<j['completionTime'] for j in state.get('workAreas',{}).values()):raise ValueError('Villager is working')
 if any(e.get('lightingVillagerId')==person['id'] and at<e.get('lightingCompleteAt',0) for e in state['world']['entities']):raise ValueError('Villager is lighting another fire')
 definition=next((v for v in world.rows('fire_task') if v['fireType']==str(fire['templateId'])),None)
 if definition is None:raise NotImplementedError('No original fire task for this fire')
 task=world.by_id('task',definition['taskId']);rewards=[r for r in world.rows('reward_set_item') if r['setId']==task['rewardSet']]
 if not rewards or any(Decimal(r['chance'])!=1 for r in rewards):raise NotImplementedError('Fire probability rule not recovered')
 spend(state,[r for r in world.rows('requirement_set_item') if r['requirementSet']==task['requirementSet']])
 fire.update(isBurning=1,startsAt=at,endsAt=at+int(definition['burnDuration']),oilAppliedAt=0,lightingVillagerId=person['id'],lightingCompleteAt=at+int(task['duration']))
 fire['activeReward']={}
 for reward in rewards:
  key=reward['materialType'];amount=float(reward['quantity']);state['inventory'][key]=state['inventory'].get(key,0)+amount;fire['activeReward'][key]=fire['activeReward'].get(key,0)+amount
 return fire_response(state,fire),True

def oil_fire(state,data,at):
 fire=entity(state,data.get('userFireId'),'fire_type')
 if not fire['isBurning'] or at>=fire['endsAt']:raise ValueError('Light this fire before adding oil')
 duration=int(world.global_value('oilBurnDuration'));maximum=int(world.global_value('oilMaxBurnDuration'))
 if fire['endsAt']-at+duration>maximum:raise ValueError('Fire burn-time limit reached')
 cost=int(world.by_id('fire_type',fire['templateId'])['oilQuantity'])
 if state['inventory'].get('8',0)<cost:raise ValueError('Not enough oil')
 state['inventory']['8']-=cost;fire['endsAt']+=duration;fire['oilAppliedAt']=at
 return fire_response(state,fire),True

def bed(state,ident):
 if not isinstance(ident,str) or not ident:raise ValueError('Bed identifier required')
 for shelter in state['world']['entities']:
  if shelter['templateType']=='shelter':
   for value in shelter['beds']:
    if value['id']==ident:return shelter,value
 raise ValueError('Unknown bed in this village')

def assign(state,data,at):
 person=actor(state,data.get('villagerId'));shelter,target=bed(state,data.get('shelterBedId'))
 if target.get('villagerId') not in {'',None,person['id']}:raise ValueError('Bed is occupied')
 if person.get('shelterBedId')==target['id'] and target.get('villagerId')==person['id']:return {},False
 # Client controls age/couple selection; do not invent an extra assignment restriction.
 old=person.get('shelterBedId')
 if old:
  old_shelter,old_bed=bed(state,old);old_bed['villagerId']=''
  if not any(v.get('villagerId') for v in old_shelter['beds']):old_shelter['happinessCollectedAt']=0
 occupied=any(v.get('villagerId') for v in shelter['beds'])
 target['villagerId']=person['id'];person['shelterBedId']=target['id']
 if not occupied:shelter['happinessCollectedAt']=at
 return {},True

def empty(state,data,at):
 shelter,target=bed(state,data.get('shelterBedId'));ident=target.get('villagerId')
 if not ident:return {},False
 person=actor(state,ident);person['shelterBedId']='';target['villagerId']=''
 if not any(v.get('villagerId') for v in shelter['beds']):shelter['happinessCollectedAt']=0
 return {},True

def happiness(state,data,at,reset=False):
 shelter=entity(state,data.get('userShelterId'),'shelter');stamp=shelter['happinessCollectedAt']
 if reset:
  changed=not stamp and any(v.get('villagerId') for v in shelter['beds'])
  if changed:shelter['happinessCollectedAt']=at
  return {'userShelter':{'id':shelter['id'],'happinessCollectedAt':shelter['happinessCollectedAt']}},changed
 if not any(v.get('villagerId') for v in shelter['beds']):raise ValueError('Shelter has no occupants')
 if at-stamp<SHELTER_INTERVAL:raise ValueError('Shelter happiness is not ready')
 reward=int(world.by_id('shelter',shelter['templateId'])['happinessReward'])*sum(bool(v.get('villagerId')) for v in shelter['beds']);state['user']['xp']+=reward;shelter['happinessCollectedAt']=at
 return {'userShelter':{'id':shelter['id'],'happinessCollectedAt':at},'xp':reward},True

def operate(state,service,data,at,receipt_key=None):
 key=service+':'+receipt_key if receipt_key else None;signature=json.dumps(data,sort_keys=True,separators=(',',':'))
 receipt=state.get('habitatReceipts',{}).get(key) if key else None
 if receipt:
  if receipt['request']!=signature:raise ValueError('Request identifier reused for another habitat action')
  return copy.deepcopy(receipt['response']),False
 if service.endswith('/StartFire'):response,changed=start_fire(state,data,at)
 elif service.endswith('/OilFire'):response,changed=oil_fire(state,data,at)
 elif service.endswith('/AssignBedToVillager'):response,changed=assign(state,data,at)
 elif service.endswith('/EmptyBed'):response,changed=empty(state,data,at)
 else:response,changed=happiness(state,data,at,service.endswith('/ResetHappinessTimer'))
 if key:
  state.setdefault('habitatReceipts',{})[key]={'request':signature,'response':copy.deepcopy(response)};changed=True
 if changed:state['revision']+=1;state['updatedAt']=at
 return response,changed
