"""Authored modern WofSet/WofSetItem prizes; original client response schema.
Server-side selection is reconstructed as normalized original Chance weights.
"""
import copy,secrets
from decimal import Decimal,ROUND_HALF_UP
import world
SERVICES={'ClientFortune/GetWOFSpinResult'}

def choose(rows,field='Chance'):
 rows=[r for r in rows if Decimal(r[field])>0]
 weights=[int(Decimal(r[field])*1000000000) for r in rows]
 total=sum(weights)
 if not total:raise ValueError('Original reward pool has no positive weights')
 ticket=secrets.randbelow(total)
 for row,weight in zip(rows,weights):
  if ticket<weight:return row
  ticket-=weight
 raise ValueError('Invalid reward selection')

def draw(set_id,multiplier=1):
 item=choose([r for r in world.rows('WofSetItem') if r['WofSet']==str(set_id)])
 if item['MaterialType']!='0':prizes=[{'materialType':item['MaterialType'],'quantity':item['Quantity']}]
 else:
  entries=[r for r in world.rows('reward_set_item') if r['setId']==item['RewardSet']]
  # Shared orderReference denotes alternative outcomes in this original pool.
  prizes=[choose(entries,'chance')]
 result=[]
 for prize in prizes:
  amount=Decimal(prize['quantity'])*(Decimal(str(multiplier)) if item['ShouldMultiply']=='1' else 1)
  amount=int(amount.to_integral_value(rounding=ROUND_HALF_UP))
  if amount>0:result.append({'MaterialTypeId':int(prize['materialType']),'Amount':amount})
 return {'ResultIndex':int(item['SlotIndex']),'MaterialTypes':result}

def credit(state,model):
 for reward in model['MaterialTypes']:
  key=str(reward['MaterialTypeId']);state['inventory'][key]=state['inventory'].get(key,0)+reward['Amount']

def level_spin(state,level):
 model=draw(6 if level==2 else 3);credit(state,model)
 state.setdefault('rules',{})['fortune_rewards']={'status':'authored_prizes_reconstructed_server_policy','evidence':'original WofSet, WofIncrement, WofSetItem and native WOFResultParse','policy':'normalized positive Chance weights; level-two authored FTUE set; later original level set; prize saved with level receipt before animation; nested reward pool selects one weighted outcome; multiplied quantities round half up'}
 return model

def operate(state,service,data,at,key):
 if not key:raise ValueError('Fortune request receipt required')
 kind=data.get('WheelOfFortuneTypeID')
 if isinstance(kind,bool) or not isinstance(kind,int) or kind!=1:raise ValueError('This path requires a daily spin; level spins are awarded with level-up')
 previous=state.get('fortuneReceipts',{}).get(key)
 if previous:return copy.deepcopy(previous),False
 next_at=state['user'].get('NextDailySpinAt',0)
 if at<next_at:raise ValueError('Daily spin is not ready')
 history=state.get('dailySpin',{})
 increment=(int(history.get('increment',0))%7+1) if history and at-history['at']<172800 else 1
 definition=next(v for v in world.rows('WofIncrement') if v['Increment']==str(increment) and v['WofSet'] in {'2','7'})
 model=draw(int(definition['WofSet']),definition['Multiplier']);credit(state,model)
 state['dailySpin']={'at':at,'increment':increment}
 state['user'].update(NextDailySpinAt=at+86400,NextDailySpinIncrement=increment%7+1)
 response={'result':{'WheelOfFortuneModel':model},'user':dict(state['user'])}
 state.setdefault('fortuneReceipts',{})[key]=copy.deepcopy(response);state['revision']+=1
 state.setdefault('rules',{})['daily_spin_clock']={'status':'reconstructed_server_policy','policy':'one daily spin every 86400 seconds; streak continues within 48 hours, cycles after day seven; ignore client-provided reward set and multiplier'}
 return response,True
