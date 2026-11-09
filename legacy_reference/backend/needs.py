"""Local basic-needs policy using recovered categories, fields and interval values.
Selection of food/fun targets is a declared deterministic reconstruction.
"""
import copy,math
from decimal import Decimal
import world,tasks
GENERATORS={
 'GenerateWaterWants':(1,6,'thirstIntervalSec'),
 'GenerateFoodWants':(2,107,'hungerIntervalSec'),
 'GenerateFunWants':(3,132,'funWantDelay'),
}
DEFERRED={'GenerateFireWants','GenerateShelterWants','GenerateRetirementWants'}

def actor_by_id(state,ident):
 actor=next((v for v in state['world']['entities'] if v['id']==ident and v['templateType']=='villager_type'),None)
 if actor is None:raise ValueError('Unknown villager')
 return actor

def reconcile_fun_wishes(state,at):
 """Clear owned-building and obsolete-age wishes, returning native removals."""
 import fun
 all_wants=state.setdefault('wants',[])
 people={a['id']:a for a in state['world']['entities'] if a['templateType']=='villager_type'}
 owned={ident:{int(activity['materialType']) for _,activity in fun.available(state,a,at)} for ident,a in people.items()}
 activities=world.rows('fun_activity')
 def keep(want):
  if want['wantableCategoryType']!=3:return True
  person=people.get(want['VillagerStringID'])
  if person is None:return False
  return want['MaterialID'] not in owned[person['id']] and any(int(a['materialType'])==want['MaterialID'] and fun.eligible(person,a,at) for a in activities)
 removed=[w for w in all_wants if not keep(w)]
 if removed:
  ids={w['WantId'] for w in removed};all_wants[:]=[w for w in all_wants if w['WantId'] not in ids]
 return [{'WantId':w['WantId'],'VillagerStringID':w['VillagerStringID']} for w in removed]

def generate(state,service,at):
 method=service.rsplit('/',1)[-1];all_wants=state.setdefault('wants',[])
 if method=='GenerateRelationshipWants':
  import relationships
  return relationships.generate(state,at)
 if method in {'GenerateBirthWants','GenerateChildWants'}:
  import family
  return family.generate_child_wishes(state,at)
 if method=='GenerateInteractiveWants':
  import interactive
  return interactive.generate(state,at)
 if method in DEFERRED:
  # This local deployment disables these unrecovered event simulations.
  changed=method not in state.get('deferredNeedSystems',[])
  if changed:state.setdefault('deferredNeedSystems',[]).append(method)
  return {'result':copy.deepcopy(all_wants)},changed
 if method not in GENERATORS:raise NotImplementedError('Unknown needs generator')
 category,material,interval_key=GENERATORS[method];changed=False
 if category==3:
  import fun
  # A category-3 wish asks for a fun building. The native baby's idle-fun
  # gate requires zero wishes (Script_2534); creating a new ownership wish
  # for an already usable building prevents Script_2648 from entering it.
  # Retain age-valid wishes for missing/worn buildings. Generation of new
  # missing-building wishes remains deferred until its selection rules are recovered.
  changed=bool(reconcile_fun_wishes(state,at))
  policy={'status':'reconstructed_local_policy','evidence':'Script_2675 maps material category 35 to want category 3; Script_2534 blocks idle fun while wishes exist; native toddler crÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¨che completion observed with no wishes','policy':'usable owned buildings satisfy ownership wishes; preserve age-valid missing/worn-building wishes; new ownership-wish selection deferred; original client runs physical fun activities'}
  if state.get('rules',{}).get('fun_wishes')!=policy:state.setdefault('rules',{})['fun_wishes']=policy;changed=True
  if changed:state['revision']+=1
  return {'result':copy.deepcopy(all_wants)},changed
 interval=int(world.global_value(interval_key));clock=state.setdefault('needSatisfiedAt',{})
 for actor in [v for v in state['world']['entities'] if v['templateType']=='villager_type']:
  import interactive
  if interactive.feeding_child(actor,at):continue
  selected=material
  if any(w['VillagerStringID']==actor['id'] and w['wantableCategoryType']==category for w in all_wants):continue
  if at-clock.get(actor['id']+':'+str(category),-interval)<interval:continue
  ident=int(state.get('nextWantId',1));state['nextWantId']=ident+1
  all_wants.append({'WantId':ident,'VillagerStringID':actor['id'],'MaterialID':selected,'wantableCategoryType':category,'updatedAt':at});changed=True
 if changed:
  state['revision']+=1;state.setdefault('rules',{})['basic_needs']={'status':'reconstructed_local_policy','evidence':'native ForceVillagerWant category mapping and global hunger/thirst intervals','policy':'food 107 and water 6 for non-feeding age classes; baby/toddler bottle wishes are original paired interactive activity 1; stable one want/category/character; physical fun uses separate ownership-wish reconciliation; complex event systems deferred'}
 return {'result':copy.deepcopy(all_wants)},changed

def current_receipt(state,receipt):
 response=copy.deepcopy(receipt['response'])
 person=actor_by_id(state,receipt['villagerId'])
 response.setdefault('result',{}).update(VillagerStringID=person['id'],Xp=person.get('xp',0))
 satisfied=response.get('SatisfiedWantModels',[])
 want_id=next((v.get('WantId',v.get('WantID')) for v in satisfied),None)
 if want_id is not None:response.setdefault('result',{}).update(VillagerStringID=person['id'],Xp=person.get('xp',0),WantID=want_id,wantID=want_id)
 for happy in [response.get('HappinessModel',{}),response.get('result',{}).get('HappinessModel',{})]:
  happy.update(VillagerStringId=person['id'],VillagerStringID=person['id'],Xp=person.get('xp',0))
 # Never overwrite a newer client inventory with an old receipt snapshot.
 for target in [response,response.get('result',{})]:
  target['inventory']=tasks.inventory(state)
  for want in target.get('SatisfiedWantModels',[]):
   if 'WantID' in want:want['WantId']=want.pop('WantID')
 return response

def consumption_category(material):
 definition=world.by_id('material_type',material);category=definition['categoryId'];seen=set()
 while category not in seen and category!='-1':
  if category=='5':return 1
  if category=='41':return 2
  seen.add(category)
  try:category=world.by_id('material_category',category)['parentId']
  except StopIteration:break
 raise ValueError('Direct consumption requires original food or drink category')

def consume(state,data,at,receipt_key=None):
 ident=data.get('VillagerStringID');material=data.get('MaterialTypeID');requested=data.get('WantID')
 if isinstance(material,bool) or not isinstance(material,int):raise ValueError('Material identifier required')
 actor=actor_by_id(state,ident);category=consumption_category(material)
 if receipt_key and receipt_key in state.get('directConsumptionReceipts',{}):
  receipt=state['directConsumptionReceipts'][receipt_key]
  if receipt['villagerId']!=ident or receipt['materialId']!=material:raise ValueError('Consumption receipt mismatch')
  return current_receipt(state,receipt),False
 if requested is not None:
  if not str(requested).isdigit():raise ValueError('Invalid want identifier')
  receipt=state.get('consumptionReceipts',{}).get(str(requested))
  if receipt:
   if receipt['villagerId']!=ident or receipt['materialId']!=material:raise ValueError('Consumption receipt mismatch')
   return current_receipt(state,receipt),False
 want=next((w for w in state.get('wants',[]) if w['VillagerStringID']==ident and w['MaterialID']==material and (requested is None or w['WantId']==int(requested))),None)
 if want is None:
  # The original quick-drink path omits WantID, including retries after success.
  if requested is None:
   matches=[r for r in [*state.get('consumptionReceipts',{}).values(),*state.get('directConsumptionReceipts',{}).values()] if r['villagerId']==ident and r['materialId']==material and at-r.get('consumedAt',state.get('needSatisfiedAt',{}).get(ident+(':'+str(category)),0))<=int(world.global_value('thirstIntervalSec' if category==1 else 'hungerIntervalSec'))]
   if matches:return current_receipt(state,matches[-1]),False
  if requested is not None:raise ValueError('Matching saved want required')
  # Native ServerConsume deliberately omits WantID when its third argument is -1.
  # Reconstructed policy: allow stocked food/water once per original need interval.
  definition=world.by_id('material_type',material)
  if not receipt_key:raise ValueError('Direct consumption requires a request receipt key')
  want={'wantableCategoryType':category,'WantId':None}
 if want['wantableCategoryType'] not in {1,2}:raise NotImplementedError('Fun, housing and equipment consumption need their own interaction rules')
 key=str(material)
 if state['inventory'].get(key,0)<1:raise ValueError('Not enough material to satisfy want')
 definition=world.by_id('material_type',material);level=next(v for v in world.rows('user_level') if int(v['levelNumber'])==state['user']['userLevelID'])
 state['inventory'][key]=float(Decimal(str(state['inventory'][key]))-1)
 actor['xp']=min(int(level['villagerXPCapacity']),actor.get('xp',0)+float(definition['xpRewardPerUnitConsumed']))
 state['wants']=[w for w in state.get('wants',[]) if w['WantId']!=want['WantId']]
 state.setdefault('needSatisfiedAt',{})[ident+':'+str(want['wantableCategoryType'])]=at
 happy={'VillagerStringID':ident,'VillagerStringId':ident,'Xp':actor['xp']}
 result={'VillagerStringID':ident,'Xp':actor['xp'],'WantID':want['WantId'],'wantID':want['WantId'],'inventory':tasks.inventory(state),'HappinessModel':happy,'HappinessModels':[happy],'SatisfiedWantModels':[{'WantId':want['WantId'],'VillagerStringID':ident,'Xp':actor['xp']}]}
 response={**result,'result':copy.deepcopy(result)}
 if want['WantId'] is None:
  for target in [response,response['result']]:
   target.pop('WantID',None);target.pop('wantID',None);target['SatisfiedWantModels']=[]
  receipts=state.setdefault('directConsumptionReceipts',{});key=receipt_key
 else:receipts=state.setdefault('consumptionReceipts',{});key=str(want['WantId'])
 receipts[key]={'villagerId':ident,'materialId':material,'response':copy.deepcopy(response),'consumedAt':at}
 if receipt_key:state.setdefault('directConsumptionReceipts',{})[receipt_key]=copy.deepcopy(receipts[key])
 state['revision']+=1
 return response,True

def release_xp(state,data):
 actor=actor_by_id(state,data.get('VillagerStringID'));amount=actor.get('xp',0)
 state['user']['xp']+=amount;actor['xp']=0
 response={'result':{'UserXp':state['user']['xp']},'user':dict(state['user']),'villager':{'id':actor['id'],'xp':0},'Xp':0}
 if amount:state['revision']+=1
 return response,bool(amount)
