"""Original two-villager interactive activities, including caregiver feeding."""
import copy
from decimal import Decimal
import world,tasks,family
SERVICES={'ClientWant/GenerateInteractiveWants','ClientVillagerService/PerformInteractiveActivity'}

def member(person,set_id,at):
 typ=world.current_villager_type(person,at)['id']
 return any(v['villagerSet']==str(set_id) and v['villagerType']==typ for v in world.rows('villager_set_item'))

def requester_eligible(person,activity,at):
 if activity['id']=='10':return world.current_villager_type(person,at)['name']=='Dog Villager'
 return member(person,activity['requesterVillagerSet'],at)

def feeding_child(person,at):return member(person,'6',at)

def generate(state,at):
 wants=state.setdefault('wants',[]);people=family.actors(state);changed=False
 # Remove the first experimental food/milk wishes and obsolete wishes after aging.
 eligible={p['id'] for p in people if feeding_child(p,at)}
 kept=[w for w in wants if not (w['wantableCategoryType']==4 and w['MaterialID']==494) and not (w['VillagerStringID'] in eligible and w['wantableCategoryType'] in {1,2}) and not (w['wantableCategoryType']==8 and w['MaterialID']==494 and not any(p['id']==w['VillagerStringID'] and any(requester_eligible(p,a,at) for a in world.rows('interactive_activity') if a['isActive']=='1' and a['id']!='0') for p in people))]
 if kept!=wants:state['wants']=wants=kept;changed=True
 for person in people:
  for activity in world.rows('interactive_activity'):
   if activity['id']=='0' or activity['isActive']!='1' or activity['buildingType']!='0' or not requester_eligible(person,activity,at):continue
   if any(w['VillagerStringID']==person['id'] and w['wantableCategoryType']==8 for w in wants):continue
   last=state.get('interactiveLastAt',{}).get(person['id']+':'+activity['id'])
   if last is not None and at-last<int(activity['repeatDelaySecs']):continue
   ident=int(state.get('nextWantId',1));state['nextWantId']=ident+1
   wants.append({'WantId':ident,'VillagerStringID':person['id'],'MaterialID':int(activity['materialType']),'wantableCategoryType':8,'updatedAt':at});changed=True
 if changed:state['revision']+=1
 return {'result':copy.deepcopy(wants)},changed

def reply(state,satisfied):
 models=[{'VillagerStringID':p['id'],'Xp':p.get('xp',0)} for p in family.actors(state)]
 result={'inventory':tasks.inventory(state),'SatisfiedWantModels':copy.deepcopy(satisfied),'HappinessModels':models}
 return {**copy.deepcopy(result),'result':result}

def perform(state,data,at,key):
 if not key:raise ValueError('Interactive activity receipt required')
 value=data.get('activityId')
 if isinstance(value,bool) or not str(value).isdigit() or int(value)<=0:raise ValueError('Activity identifier required')
 try:activity=world.by_id('interactive_activity',value)
 except StopIteration:raise ValueError('Unknown original interactive activity') from None
 requester=family.actor(state,data.get('requesterVillagerId'));supplier=family.actor(state,data.get('supplierVillagerId'))
 if requester['id']==supplier['id']:raise ValueError('An activity needs two distinct villagers')
 previous=state.get('interactiveReceipts',{}).get(key)
 signature=[requester['id'],supplier['id'],activity['id']]
 if previous:
  if previous['participants']!=signature:raise ValueError('Interactive receipt reused for different participants')
  return reply(state,previous['satisfied']),False
 if activity['isActive']!='1':raise ValueError('This original activity is inactive')
 if not requester_eligible(requester,activity,at) or not member(supplier,activity['supplierVillagerSet'],at):raise ValueError('Villagers do not meet the original activity roles')
 clock=requester['id']+':'+activity['id'];last=state.get('interactiveLastAt',{}).get(clock)
 if last is not None and at-last<int(activity['repeatDelaySecs']):
  old=next((r for r in reversed(list(state.get('interactiveReceipts',{}).values())) if r['participants'][0]==requester['id'] and r['participants'][2]==activity['id']),None)
  if old and old['participants']==signature:return reply(state,old['satisfied']),False
  raise ValueError('Activity repeat delay has not elapsed')
 costs={}
 for req in world.rows('requirement_set_item'):
  if activity['requirementSet']=='0' or req['requirementSet']!=activity['requirementSet']:continue
  if Decimal(str(state['inventory'].get(req['materialType'],0)))<Decimal(req['quantity']):raise ValueError('Not enough activity materials: '+req['materialType'])
  costs[req['materialType']]=costs.get(req['materialType'],Decimal(0))+Decimal(req['quantityUsed'])
 for material,amount in costs.items():
  if Decimal(str(state['inventory'].get(material,0)))<amount:raise ValueError('Not enough activity materials')
 level=next(r for r in world.rows('user_level') if int(r['levelNumber'])==int(state['user']['userLevelID']))
 satisfied=[{'WantId':w['WantId'],'VillagerStringID':requester['id']} for w in state.get('wants',[]) if w['VillagerStringID']==requester['id'] and w['wantableCategoryType']==8 and w['MaterialID']==int(activity['materialType'])]
 for material,amount in costs.items():state['inventory'][material]=float(Decimal(str(state['inventory'].get(material,0)))-amount)
 for person,role in [(requester,'requester'),(supplier,'supplier')]:
  person['xp']=min(int(level['villagerXPCapacity']),person.get('xp',0)+int(activity['xpReward']))
  person['energyLevel']=max(0,person.get('energyLevel',0)-int(activity[role+'EnergyUsed']))
 ids={w['WantId'] for w in satisfied};state['wants']=[w for w in state.get('wants',[]) if w['WantId'] not in ids]
 state.setdefault('interactiveLastAt',{})[clock]=at
 state.setdefault('interactiveReceipts',{})[key]={'participants':signature,'satisfied':satisfied,'startedAt':at,'completionTime':at+int(activity['durationSecs']),'deductions':{k:str(v) for k,v in costs.items()}}
 state.setdefault('rules',{})['interactive_activities']={'status':'original_tables_reconstructed_server_policy','evidence':'Script2438, Script2637 and GenericListener; original interactive_activity role sets, requirements, XP and repeat delay','policy':'client handles arrival and paired animations; one server transaction at animation start; cap both participants XP; saved receipts and original repeat delay prevent duplicate spending/reward; only authored active feeding activities generated'}
 state['revision']+=1
 return reply(state,satisfied),True
