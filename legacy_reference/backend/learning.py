"""Original material-learning contract, with explicit local selection policy.
Existing inventory keys retain their pre-learning unlocked status on old saves.
"""
import math,struct
from decimal import Decimal
from functools import lru_cache
import world,prerequisites
SERVICES={'ClientMaterialService/'+s+'LearningMaterial' for s in ['Start','Complete','Skip']}

def unlocked(state,ident,milestones=None):
 key=str(ident);record=state.get('materialLearning',{}).get(key)
 if record:return record['status']=='unlocked'
 # Preserve the legacy restoration's granted items; do not revoke player progress.
 if key in state['inventory']:return True
 if key in (prerequisites.milestones(state) if milestones is None else milestones):return True
 try:return int(world.by_id('material_type',key)['learnDurationSec'])==0
 except StopIteration:return False

def inventory(state):
 milestones=prerequisites.milestones(state)
 keys=set(state['inventory'])|set(state.get('materialLearning',{}))|milestones
 return [{'materialTypeId':int(k),'amount':max(state['inventory'].get(k,0),int(k in milestones)),'isUnlocked':k in milestones or unlocked(state,k,milestones),'learningStartedAt':state.get('materialLearning',{}).get(k,{}).get('startedAt',0)} for k in sorted(keys,key=int)]

def price(remaining):
 if remaining<=0:return 0
 def f(v):return struct.unpack('<f',struct.pack('<f',v))[0]
 xs=[f(float(world.global_value('gemCurveVariableTime'+v))) for v in ['1min','1hour','1day','1week']]
 ys=[f(float(world.global_value('gemCalcValue'+str(i)))) for i in range(1,5)]
 t=min(f(remaining),xs[-1]);index=0 if t<xs[1] else 1 if t<xs[2] else 2
 scale=f(f(xs[index+1]-xs[index])/f(ys[index+1]-ys[index]))
 return max(1,math.floor(f(ys[index]+f(f(t-xs[index])/scale))))

@lru_cache(maxsize=None)
def requirements(ident):
 # Match original task reward -> material lookup, then its levelRequirement set.
 sets={r['setId'] for r in world.rows('reward_set_item') if r['materialType']==str(ident)}
 task=next((t for t in world.rows('task') if t['rewardSet'] in sets and t['id']!='0'),None)
 return tuple(r for r in world.rows('requirement_set_item') if task and r['requirementSet']==task['levelRequirement'])

def reply(state,record):
 return {'result':{'UpdatedTime':record.get('startedAt',0),'Gem':state['inventory'].get('323',0)},'inventory':inventory(state)}

def operate(state,service,data,at):
 ident=data.get('materialTypeId')
 if isinstance(ident,bool) or not isinstance(ident,int) or ident<=0:raise ValueError('Material identifier required')
 try:definition=world.by_id('material_type',ident)
 except StopIteration:raise ValueError('Unknown material') from None
 duration=int(definition['learnDurationSec']);key=str(ident);record=state.get('materialLearning',{}).get(key)
 if duration<=0:raise ValueError('Material does not require learning')
 if record and record['status']=='unlocked':return reply(state,record),False
 if service.endswith('StartLearningMaterial'):
  if record:return reply(state,record),False
  if unlocked(state,ident):return reply(state,{}),False
  if int(definition['unlockLevel'])>state['user']['userLevelID']:raise ValueError('Learning requires a higher village level')
  parent=int(definition['parentID'])
  if parent>0 and not unlocked(state,parent):raise ValueError('Learn the parent material first')
  if int(definition['area'])>state['areaId']:raise ValueError('Material belongs to an unavailable area')
  for req in requirements(ident):
   if prerequisites.quantity(state,req['materialType'])<Decimal(req['quantity']):raise ValueError('Learning prerequisite is not met')
  seasonal=int(definition['seasonal'])!=0
  limit=int(world.global_value('learningMaxSeasonal' if seasonal else 'learningMax'))
  active=sum(r['status']=='learning' and r['seasonal']==seasonal for r in state.get('materialLearning',{}).values())
  if active>=limit:raise ValueError('All learning slots in this category are occupied')
  # Start costs no gems in the original dialog. Legacy keysRequired is not charged:
  # its use by this client version has not been recovered.
  record={'status':'learning','startedAt':at,'duration':duration,'seasonal':seasonal,'gemsSpent':0}
  state.setdefault('materialLearning',{})[key]=record
 elif service.endswith(('CompleteLearningMaterial','SkipLearningMaterial')):
  if not record:raise ValueError('Start learning this material first')
  remaining=max(0,record['startedAt']+record['duration']-at)
  if remaining and service.endswith('CompleteLearningMaterial'):raise ValueError('Learning timer has not finished')
  cost=price(remaining) if service.endswith('SkipLearningMaterial') else 0
  if state['inventory'].get('323',0)<cost:raise ValueError('Not enough gems to finish learning')
  if cost:state['inventory']['323']-=cost
  record.update(status='unlocked',completedAt=at,gemsSpent=cost)
 else:raise NotImplementedError(service)
 state['revision']+=1
 state.setdefault('rules',{})['material_learning']={'status':'reconstructed_server_policy','evidence':'native ServerStart/Complete/SkipLearningMaterial, UnlockingModelUpdate and inventory parser; original material timer, parent/level and learning slot definitions','policy':'original timers and shared skip curve; separate regular/seasonal slots; preserve legacy granted inventory; no inferred key charges; seasonal calendar availability not recovered'}
 return reply(state,record),True
