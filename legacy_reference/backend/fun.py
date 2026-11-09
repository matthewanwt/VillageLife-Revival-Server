"""Recovered fun-building use counters, actor eligibility and completion response."""
import copy,math
from decimal import Decimal
import world,tasks

def actor(state,ident):
 value=next((v for v in state['world']['entities'] if v['id']==ident and v['templateType']=='villager_type'),None)
 if value is None:raise ValueError('Unknown villager')
 if world.entity_area(value)!=state['areaId']:raise ValueError('Villager is in another area')
 return value

def eligible(person,activity,at):
 typ=int(world.current_villager_type(person,at)['id'])
 return any(int(v['villagerType'])==typ for v in world.rows('villager_set_item') if v['villagerSet']==activity['usedBy'])

def initialize(entity):
 if entity['templateType']!='fun_building' or 'amount' in entity:return False
 definition=world.by_id('fun_building',entity['templateId']);activity=world.by_id('fun_activity',definition['funActivity'])
 entity['amount']=int(activity['itemWear'])
 if entity['amount']==-1 and activity.get('unbreakable')=='1':
  entity['amount']=1000000000;entity['counterPolicy']='local positive wire sentinel for original unbreakable activity'
 elif entity['amount']<=0:raise NotImplementedError('Nonpositive fun use counter requires separate rules')
 entity['funCounterEvidence']='original fun_activity.itemWear; native world loader reads amount; native completion decrements one use'
 return True

def migrate(state):
 changed=False
 for entity in state['world']['entities']:changed=initialize(entity) or changed
 if changed:state['revision']+=1
 return changed

def available(state,person,at):
 result=[]
 for building in state['world']['entities']:
  if building['templateType']!='fun_building' or building.get('amount',0)<=0:continue
  definition=world.by_id('fun_building',building['templateId']);activity=world.by_id('fun_activity',definition['funActivity'])
  if eligible(person,activity,at):result.append((building,activity))
 return result

def reply(state,person,building,satisfied):
 happy={'VillagerStringId':person['id'],'VillagerStringID':person['id'],'Xp':person.get('xp',0)}
 return {'user':dict(state['user']),'inventory':tasks.inventory(state),'HappinessModel':happy,'SatisfiedWantModels':copy.deepcopy(satisfied),'userFunBuildingType':{'id':building['id'],'amount':building.get('amount',0)} if building else {}}

def perform(state,data,at,receipt_key):
 person=actor(state,data.get('villagerId'));ident=data.get('funActivityId');building_id=data.get('userFunBuildingTypeId')
 if isinstance(ident,bool) or not isinstance(ident,int):raise ValueError('Fun activity identifier required')
 receipt=state.get('funReceipts',{}).get(receipt_key)
 building=next((v for v in state['world']['entities'] if v['id']==building_id and v['templateType']=='fun_building'),None)
 if receipt:
  if receipt['actor']!=person['id'] or receipt['activity']!=ident or receipt['building']!=building_id:raise ValueError('Fun call identifier reused')
  return reply(state,person,building,receipt['satisfied']),False
 try:activity=world.by_id('fun_activity',ident)
 except StopIteration:raise ValueError('Unknown original fun activity') from None
 portable=building_id is None
 if portable:
  if any(b['funActivity']==str(ident) for b in world.rows('fun_building')):raise ValueError('Saved fun building required')
  if state['inventory'].get(activity['materialType'],0)<=0:raise ValueError('Portable fun item is not owned')
 else:
  if building is None:raise ValueError('Saved fun building required')
  if world.entity_area(building)!=state['areaId']:raise ValueError('Fun building is in another area')
  definition=world.by_id('fun_building',building['templateId'])
  if int(definition['funActivity'])!=ident:raise ValueError('Activity does not match building')
 if not eligible(person,activity,at):raise ValueError('This age group cannot use that activity')
 if any(v['villagerId']==person['id'] and v['status']=='working' and v['completionTime']>at for v in state.get('workAreas',{}).values()):raise ValueError('Villager still working')
 if building is not None and building.get('amount',0)<=0:raise ValueError('Fun building has no uses remaining')
 last=state.get('lastFunAt',{}).get(person['id'])
 if last is not None and at-last<int(activity['durationSecs']):
  # Native request is sent at animation completion; reject duplicate completions without spending.
  return reply(state,person,building,[]),False
 rewards=[v for v in world.rows('reward_set_item') if v['setId']==activity['rewardSet']] if activity['rewardSet']!='0' else []
 if any(Decimal(v['chance'])!=1 for v in rewards):raise NotImplementedError('Probabilistic fun rewards not recovered')
 level=next(v for v in world.rows('user_level') if int(v['levelNumber'])==state['user']['userLevelID'])
 person['xp']=min(int(level['villagerXPCapacity']),person.get('xp',0)+int(activity['xpReward']))
 if state['user']['userLevelID']>=int(activity['energyDeductionLevel']):person['energyLevel']=max(0,person['energyLevel']-int(activity['energyCost']))
 if activity.get('unbreakable','0')!='1':
  if building is not None:building['amount']-=1
  elif int(activity['itemWear'])>0:
   material=activity['materialType'];state['inventory'][material]=float(max(Decimal(0),Decimal(str(state['inventory'][material]))-Decimal(1)/Decimal(activity['itemWear'])))
 if portable:state.setdefault('rules',{})['portable_fun']={'status':'original_client_wear_reconstructed_server_policy','evidence':'Script2632 has no-building RPC and deducts 1/itemWear; Script2538 selects owned portable items','policy':'same original eligibility, XP, energy and reward tables; global per-character completion cooldown and receipts; no virtual building created'}
 for reward in rewards:
  key=reward['materialType'];state['inventory'][key]=state['inventory'].get(key,0)+float(reward['quantity'])
 wants=[w for w in state.get('wants',[]) if w['VillagerStringID']==person['id'] and w['MaterialID']==int(activity['materialType']) and w['wantableCategoryType']==3]
 satisfied=[{'WantId':w['WantId'],'VillagerStringID':person['id']} for w in wants]
 ids={w['WantId'] for w in wants};state['wants']=[w for w in state.get('wants',[]) if w['WantId'] not in ids]
 state.setdefault('needSatisfiedAt',{})[person['id']+':3']=at;state.setdefault('lastFunAt',{})[person['id']]=at
 state.setdefault('funReceipts',{})[receipt_key]={'actor':person['id'],'activity':ident,'building':building_id,'satisfied':satisfied,'completedAt':at}
 state['revision']+=1
 return reply(state,person,building,satisfied),True
