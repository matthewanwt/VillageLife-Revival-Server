"""Replay explicit original tutorial inventory assignments once per saved world."""
from decimal import Decimal
import json,math,struct,copy
import world
from functools import lru_cache

@lru_cache(maxsize=1)
def _script_steps():
 # Private read-only cache; never stored in, or returned as, player state.
 return tuple(world.rows('seq_state_tablet_ftue'))

def sync_inventory_assignments(saved):
 state=saved.get('normal')
 if state is None:return False
 checkpoint=str(saved.get('gameSettings',{}).get('activeSequenceId','410'))
 steps=_script_steps()
 targets=[v for v in steps if v['persist']==checkpoint]
 if checkpoint=='-1' and str(saved.get('gameSettings',{}).get('isFtueComplete','')).lower() in {'1','true'}:
  limit=max(Decimal(v['order']) for v in steps)
 elif targets:limit=max(Decimal(v['order']) for v in targets)
 else:return False
 applied=state.get('scriptEffects',{}).get('inventoryAssignments',[])
 pending=[v for v in steps if v['sequenceType']=='64' and Decimal('3')<=Decimal(v['order'])<=limit and v['id'] not in applied]
 xp_applied=state.get('scriptEffects',{}).get('shrineXp',[])
 xp_steps=[v for v in steps if v['sequenceType']=='114' and Decimal('3')<=Decimal(v['order'])<=limit and v['id'] not in xp_applied]
 if not pending and not xp_steps:return False
 # A completed village may predate these tutorial receipts. Absolute tutorial
 # inventory assignments are not evidence of its current balance: replaying
 # them can reset purchased gems, earned silver and player stock on a read.
 # Retire missing old assignments without granting or removing inventory.
 complete=str(saved.get('gameSettings',{}).get('isFtueComplete','')).lower() in {'1','true'}
 preserve_xp=complete and (int(state['user']['userLevelID'])>1 or state['user']['xp']!=0)
 effects=state.setdefault('scriptEffects',{}).setdefault('inventoryAssignments',[])
 for step in sorted(pending,key=lambda v:Decimal(v['order'])):
  values=json.loads(step['dataJSON'])['inventory']
  if not complete:
   for key,value in values.items():state['inventory'][key]=float(Decimal(value))
  effects.append(step['id'])
 for step in sorted(xp_steps,key=lambda v:Decimal(v['order'])):
  delta=int(Decimal(json.loads(step['dataJSON'])['xp']))
  if not preserve_xp:state['user']['xp']=max(0,state['user']['xp']+delta)
  state.setdefault('scriptEffects',{}).setdefault('shrineXp',[]).append(step['id'])
 state['revision']+=1
 world.validate_world(state)
 return True


def paid_level_price(state):
 # Script1926: current and previous cumulative XP thresholds, fillCost,
 # LevelupMinGemCost; float32 interpolation then -floor(-value).
 f=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]
 current=int(state['user']['userLevelID']);levels={int(v['levelNumber']):v for v in world.rows('user_level')}
 level=levels[current];threshold=f(float(level['experienceRequired']));previous=f(float(levels[current-1]['experienceRequired'])) if current>1 else 0.0
 xp=f(float(state['user']['xp']));minimum=f(float(world.global_value('LevelupMinGemCost')))
 if xp>=threshold:return 0
 span=f(threshold-previous)
 if span<=0:raise ValueError('Invalid original level XP interval')
 fraction=f(f(f(float(level['fillCost']))-minimum)/span)
 remaining=f(f(threshold-previous)-f(xp-previous))
 return max(0,math.ceil(f(minimum+f(fraction*remaining))))

def increase_level(state,data,receipt_key=None):
 paid=str(data.get('IsPaid','false')).lower()
 if paid not in {'true','false'}:raise ValueError('Invalid paid level-up flag')
 paid=paid=='true'
 if paid and not receipt_key:raise ValueError('Paid level-up requires a request receipt')
 if receipt_key and receipt_key in state.get('levelCallReceipts',{}):
  old=state['levelCallReceipts'][receipt_key]
  if old['paid']!=paid:raise ValueError('Level-up request identifier reused')
  return copy.deepcopy(old['response']),False
 current=int(state['user']['userLevelID']);level=next((r for r in world.rows('user_level') if int(r['levelNumber'])==current),None)
 target=next((r for r in world.rows('user_level') if int(r['levelNumber'])==current+1),None)
 if level is None or target is None:raise ValueError('No next level in original table')
 cost=paid_level_price(state) if paid else 0
 if paid and state['inventory'].get('323',0)<cost:raise ValueError('Not enough gems for level-up')
 if not paid and state['user']['xp']<int(level['experienceRequired']):
  receipt=state.get('levelReceipts',{}).get(str(current))
  if receipt:return receipt,False
  raise ValueError('Not enough shrine XP')
 # Rewards belong to the level reached, as displayed by the original milestone UI.
 rewards=[]
 if target['rewardSetId1']!='0':
  for item in [v for v in world.rows('reward_set_item') if v['setId']==target['rewardSetId1']]:
   if Decimal(item['chance'])!=1:raise NotImplementedError('Level reward probability rule not recovered')
   key=item['materialType'];amount=float(item['quantity']);state['inventory'][key]=state['inventory'].get(key,0)+amount
   rewards.append({'MaterialTypeId':int(key),'Amount':amount})
 if cost:state['inventory']['323']-=cost
 if paid:state['user']['xp']=max(state['user']['xp'],int(level['experienceRequired']))
 state['user'].update(userLevel=current+1,userLevelID=current+1,populationCap=int(target['populationCap']))
 import fortune
 spin=fortune.level_spin(state,current+1)
 response={'result':{'Rewards':rewards,'PopulationCap':int(target['populationCap']),'WheelOfFortuneModel':spin}}
 state.setdefault('levelReceipts',{})[str(current+1)]=response
 if receipt_key:state.setdefault('levelCallReceipts',{})[receipt_key]={'paid':paid,'gemsSpent':cost,'response':copy.deepcopy(response)}
 state.setdefault('rules',{})['paid_level_price']={'evidence':'original Script1926 float32 XP/fillCost interpolation, LevelupMinGemCost, ceiling; Script0484 deducts gems optimistically','status':'original_client_formula_default_variant','policy':'default multiplier one; server charges and fills missing cumulative XP atomically; request receipts prevent replay'}
 state['revision']+=1
 return response,True


def reconcile_level_rewards(state):
 """Repair only earned payouts proven missing by old saved receipts/deferrals."""
 import fortune
 changed=False
 receipts=state.get('levelReceipts',{})
 for pending in state.get('pendingLevelBonuses',[]):
  level=int(pending['level']);receipt=receipts.get(str(level))
  if pending.get('status')!='deferred_unrecovered_wheel_payout' or not receipt or level>int(state['user']['userLevelID']):continue
  model=receipt.get('result',{}).get('WheelOfFortuneModel')
  if model is None:
   model=fortune.level_spin(state,level);receipt.setdefault('result',{})['WheelOfFortuneModel']=copy.deepcopy(model)
  pending.update(status='restored_from_authored_prize_table',awardedModel=copy.deepcopy(model));changed=True
 # Count recorded milestone grants, including rewards already received one level late.
 expected={};actual={}
 definitions={int(v['levelNumber']):v for v in world.rows('user_level')}
 for number,receipt in receipts.items():
  if not str(number).isdigit() or int(number)>int(state['user']['userLevelID']):continue
  definition=definitions.get(int(number))
  if definition and definition['rewardSetId1']!='0':
   for reward in [r for r in world.rows('reward_set_item') if r['setId']==definition['rewardSetId1'] and r['chance']=='1']:
    key=reward['materialType'];expected[key]=expected.get(key,0)+float(reward['quantity'])
  for reward in receipt.get('result',{}).get('Rewards',[]):
   key=str(reward['MaterialTypeId']);actual[key]=actual.get(key,0)+reward['Amount']
 for key,amount in state.get('milestoneRewardRepairs',{}).items():actual[key]=actual.get(key,0)+amount
 for key,amount in expected.items():
  missing=max(0,amount-actual.get(key,0))
  if missing:
   state['inventory'][key]=state['inventory'].get(key,0)+missing
   repairs=state.setdefault('milestoneRewardRepairs',{});repairs[key]=repairs.get(key,0)+missing;changed=True
 if changed:state['revision']+=1
 return changed
