"""Shared task contracts; original table rules and atomic caller commit."""
import copy,math,uuid
from decimal import Decimal
import world,buildings,prerequisites

def row(table,ident):
 try:return world.by_id(table,ident)
 except StopIteration:raise ValueError('Unknown '+table+' identifier') from None

def inventory(state):
 import learning
 return learning.inventory(state)

def start(state,data,at,service="ClientTaskService/StartGatheringTask",receipt_key=None):
 villager=data.get('villagerId');source_id=data.get('userFarmPlotId') if service.endswith('StartFarmingTask') else data.get('userMaterialSourceId');task_id=data.get('taskTypeId')
 if not isinstance(villager,str) or (service.endswith('StartGatheringTask') and not isinstance(source_id,str)) or isinstance(task_id,bool) or not isinstance(task_id,int):raise ValueError('Invalid gathering identifiers')
 signature={'service':service,'data':copy.deepcopy(data)}
 old=state.get('taskStartReceipts',{}).get(receipt_key) if receipt_key else None
 if old:
  if old['request']!=signature:raise ValueError('Task start receipt reused for another request')
  job=state.get('workAreas',{}).get(old['workAreaId'])
  return copy.deepcopy(job['startResponse'] if job else old['response']),False
 position={k:data.get(k,0) for k in ['x','y','rotation']}
 if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in position.values()):raise ValueError('Invalid task position')
 actor=next((v for v in state['world']['entities'] if v['id']==villager and v['templateType']=='villager_type'),None)
 task=row('task',task_id)
 family={'ClientTaskService/StartGatheringTask':'3','ClientTaskService/StartCraftingTask':'1','ClientTaskService/StartBuildingTask':'2','ClientTaskService/StartFarmingTask':'4'}.get(service)
 if family=='2' and task['taskType']=='6':family='6'
 if task['taskType']!=family:raise ValueError('Task family mismatch')
 upgrade_definition=None
 if family=='3':
  source=next((v for v in state['world']['entities'] if v['id']==source_id and v['templateType']=='material_source'),None)
  if source is None or int(row('material_source',source['templateId'])['task'])!=task_id:raise ValueError('Task does not match source')
 elif family=='4':
  source=next((v for v in state['world']['entities'] if v['id']==source_id and v['templateType']=='farming_plot'),None)
  if source is None:raise ValueError('Saved farm plot required')
  if not any(v['taskId']==str(task_id) for v in world.rows('farming_task')):raise ValueError('Unknown farming recipe')
 elif family=='6':
  targets=[]
  for upgrade in world.rows('building_task'):
   if upgrade['taskId']!=str(task_id) or upgrade['parentId']=='-1':continue
   prior=row('building_type',row('building_task',upgrade['parentId'])['buildingType'])
   buildings.completion_definition({'templateId':int(upgrade['id'])})
   for existing in state['world']['entities']:
    if existing['templateType']==prior['entityRef'] and existing['templateId']==int(prior['entityID']) and world.entity_area(existing)==state['areaId']:targets.append((existing,upgrade))
  targets.sort(key=lambda pair:math.hypot(pair[0]['position']['x']-data.get('x',0),pair[0]['position']['y']-data.get('y',0)))
  if not targets:raise ValueError('No matching existing building to upgrade')
  source,upgrade_definition=targets[0];source_id=source['id']
 else:
  kind='workshop' if family=='1' else 'building_task'
  candidates=[v for v in state['world']['entities'] if v['templateType']==kind and world.entity_area(v)==state['areaId'] and (family=='1' or int(row('building_task',v['templateId'])['taskId'])==task_id)]
  candidates.sort(key=lambda v:math.hypot(v['position']['x']-data.get('x',0),v['position']['y']-data.get('y',0)))
  source=candidates[0] if candidates else None
  if source is None:raise ValueError('No matching workshop or foundation')
  source_id=source['id']
  if family=='2':buildings.completion_definition(source)
  else:
   workshop=row('workshop',source['templateId'])
   if str(task['workAreaType']) not in workshop['tableIDs'].split(','):raise ValueError('Recipe requires another workshop table')
 if actor is None:raise ValueError('Unknown villager')
 if world.entity_area(actor)!=state['areaId']:raise ValueError('Villager is in another area')
 if any(e.get('lightingVillagerId')==villager and at<e.get('lightingCompleteAt',0) for e in state['world']['entities']):raise ValueError('Villager is lighting a fire')
 if not world.can_work(actor,at,task):raise ValueError('Villager cannot work on this task at their current life stage')
 if data.get('areaId')!=state['areaId'] or source['position']['areaId']!=state['areaId']:raise ValueError('Wrong gathering area')
 position={k:data.get(k,0) for k in ['x','y','rotation']}
 if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in position.values()):raise ValueError('Invalid gathering position')
 if math.hypot(position['x']-source['position']['x'],position['y']-source['position']['y'])>200:raise ValueError('Gathering position is not near source')
 for job in state.get('workAreas',{}).values():
  if job['status']=='harvested':continue
  if job['villagerId']==villager and job['sourceId']==source_id and job['taskTypeId']==task_id:
   if receipt_key:
    state.setdefault('taskStartReceipts',{})[receipt_key]={'request':signature,'workAreaId':job['id'],'response':copy.deepcopy(job['startResponse'])};state['revision']+=1
   return copy.deepcopy(job['startResponse']),bool(receipt_key)
  if job['villagerId']==villager and job['status']=='working' and at<job['completionTime']:raise ValueError('Villager already has unfinished work')
  if family!='1' and job['sourceId']==source_id:raise ValueError('Resource source already has work')
 if family=='1' and sum(j['status']!='harvested' and j['sourceId']==source_id for j in state.get('workAreas',{}).values())>=int(workshop['tableCount']):raise ValueError('Workshop is full')
 rewards=[v for v in world.rows('reward_set_item') if task['rewardSet']!='0' and v['setId']==task['rewardSet']]
 if family in {'2','6'}:
  definition=buildings.completion_definition({'templateId':int(upgrade_definition['id'])} if upgrade_definition else source)
  if not any(v['materialType']==definition['materialType'] for v in rewards):rewards.append({'materialType':definition['materialType'],'quantity':'1','chance':'1'})
 if not rewards or any(Decimal(v['chance'])!=1 for v in rewards):raise NotImplementedError('Reward selection requires an unrecovered probability rule')
 for req in [v for v in world.rows('requirement_set_item') if v['requirementSet']==task.get('levelRequirement','0')]:
  if prerequisites.quantity(state,req['materialType'])<Decimal(req['quantity']):raise ValueError('Task unlock requirement is not met')
 requirements=[v for v in world.rows('requirement_set_item') if v['requirementSet']==task['requirementSet']]
 deductions={}
 for req in requirements:
  if req.get('villagers','undefined') not in {'undefined','0',''}:raise NotImplementedError('Additional villager requirement rule not recovered')
  key=req['materialType'];available=prerequisites.quantity(state,key) if Decimal(req['quantityUsed'])==0 else Decimal(str(state['inventory'].get(key,0)))
  if available<Decimal(req['quantity']):raise ValueError('Insufficient gathering requirement: '+key)
  if Decimal(req['quantityUsed']):deductions[key]=deductions.get(key,Decimal(0))+Decimal(req['quantityUsed'])
 for key,value in deductions.items():
  if Decimal(str(state['inventory'].get(key,0)))<value:raise ValueError('Insufficient gathering materials')
 duration=Decimal(task['duration'])
 if duration<0 or duration!=int(duration):raise ValueError('Unsupported gathering duration')
 ident='local-work-'+uuid.uuid4().hex
 response={'completionTime':at+int(duration),'createdAt':at,'workAreaId':ident,'villager':{'id':villager}}
 for key,value in deductions.items():state['inventory'][key]=float(Decimal(str(state['inventory'].get(key,0)))-value)
 job={'id':ident,'status':'working','family':family,'taskTypeId':task_id,'sourceId':source_id,'villagerId':villager,'createdAt':at,'completionTime':response['completionTime'],'position':{**position,'areaId':state['areaId']},'deductions':{k:str(v) for k,v in deductions.items()},'rewards':[{'materialTypeId':int(v['materialType']),'amount':float(v['quantity'])} for v in rewards],'startResponse':response,'rules':{'duration':'original task.duration; base seconds, skill/time modifiers not implemented','requirements':'original requirement_set_item.quantity/quantityUsed','reward':'original reward_set_item, deterministic chance=1 only'}}
 if upgrade_definition:job['upgradeDefinitionId']=int(upgrade_definition['id'])
 # Readiness is persisted only with a successful new start. A replay or rejected
 # request must not change unrelated jobs while returning changed=False.
 for previous in state.get('workAreas',{}).values():
  if previous['status']=='working' and at>=previous['completionTime']:previous['status']='ready'
 state.setdefault('workAreas',{})[ident]=job;state['revision']+=1;state['updatedAt']=at
 if receipt_key:state.setdefault('taskStartReceipts',{})[receipt_key]={'request':signature,'workAreaId':ident,'response':copy.deepcopy(response)}
 world.validate_world(state)
 return copy.deepcopy(response),True

def harvest(state,data,at):
 ident=data.get('workAreaId');job=state.get('workAreas',{}).get(ident) if isinstance(ident,str) else None
 if job is None:raise ValueError('Unknown gathering work area')
 if data.get('taskTypeId')!=job['taskTypeId']:raise ValueError('Harvest task mismatch')
 if job['status']=='harvested':return copy.deepcopy(job['harvestResponse']),False
 if at<job['completionTime']:raise ValueError('Gathering task is not complete')
 for reward in job['rewards']:
  key=str(reward['materialTypeId']);state['inventory'][key]=float(Decimal(str(state['inventory'].get(key,0)))+Decimal(str(reward['amount'])))
 objects=buildings.complete(state,job) if job.get('family') in {'2','6'} else []
 satisfied=[]
 if objects:
  import needs
  satisfied=needs.reconcile_fun_wishes(state,at)
 import starter_tools
 starter_tools.recover(state,at)
 response={'objects':objects,'inventory':inventory(state),'SatisfiedWantModels':satisfied}
 job.update(status='harvested',harvestedAt=at,harvestResponse=copy.deepcopy(response));state['revision']+=1;state['updatedAt']=at
 world.validate_world(state)
 return response,True


def work_overlay(state,at):
 result=[]
 for job in state.get('workAreas',{}).values():
  if job['status']=='harvested':continue
  definition=row('task',job['taskTypeId'])
  entity={'id':job['id'],'templateType':'work_area','templateId':int(definition['workAreaType']),'taskTypeId':job['taskTypeId'],'serverPersisted':True,'position':copy.deepcopy(job['position']),'status':int(at>=job['completionTime']),'villagerId':job['villagerId'] if at<job['completionTime'] else '','userMaterialSourceId':job['sourceId'],'createdAt':job['createdAt'],'completionTime':job['completionTime']}
  result.append(entity)
 return result


def instant_price(remaining):
 import struct
 def f(v):return struct.unpack('<f',struct.pack('<f',v))[0]
 xs=[f(float(world.global_value('gemCurveVariableTaskTime'+v))) for v in ['1min','1hour','1day','1week']]
 ys=[f(float(world.global_value('gemCalcTaskValue'+str(i)))) for i in range(1,5)]
 t=min(f(remaining),xs[-1]);index=0 if t<xs[1] else 1 if t<xs[2] else 2
 scale=f(f(xs[index+1]-xs[index])/f(ys[index+1]-ys[index]))
 return max(1,math.floor(f(ys[index]+f(f(t-xs[index])/scale))))

def instant_complete(state,data,at):
 job=state.get('workAreas',{}).get(data.get('workAreaId'))
 if job is None:raise ValueError('Unknown work area')
 if 'instantCompleteReceipt' in job or job['status']=='harvested':
  return {'completionTime':job['completionTime'],'inventory':inventory(state)},False
 remaining=max(0,job['completionTime']-at);cost=instant_price(remaining) if remaining else 0
 if state['inventory'].get('323',0)<cost:raise ValueError('Not enough gems for instant finish')
 state['inventory']['323']=state['inventory'].get('323',0)-cost
 original=job['completionTime'];job['completionTime']=min(at,original);job['status']='ready';job['startResponse']['completionTime']=job['completionTime']
 job['instantCompleteReceipt']={'completedAt':at,'gemsSpent':cost,'originalCompletionTime':original,'rule':'original task curve: float32 interpolation, floor, minimum one; naturally finished zero'}
 state['revision']+=1
 world.validate_world(state)
 return {'completionTime':job['completionTime'],'inventory':inventory(state)},True
