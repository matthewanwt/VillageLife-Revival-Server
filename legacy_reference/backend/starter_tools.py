"""Explicit local fallback for exhausted authored starter tools with no recipe.
This is a reconstruction policy, not recovered original server economy.
"""
import json
from functools import lru_cache
import world

@lru_cache(maxsize=1)
def definitions():
 seed=next(v for v in world.rows('seq_state_tablet_ftue') if v['sequenceType']=='64' and 'inventory' in json.loads(v['dataJSON']))
 inventory=json.loads(seed['dataJSON'])['inventory']
 craft_sets={v['rewardSet'] for v in world.rows('task') if v['taskType']=='1'}
 craftable={v['materialType'] for v in world.rows('reward_set_item') if v['setId'] in craft_sets and float(v['quantity'])>0 and float(v['chance'])>0}
 return tuple((str(ident),float(amount),seed['id']) for ident,amount in inventory.items() if float(amount)>0 and world.by_id('material_type',ident)['categoryId']=='12' and str(ident) not in craftable)

def recover(state,at):
 changed=False
 for ident,amount,source in definitions():
  current=state['inventory'].get(ident,0)
  if isinstance(current,bool) or not isinstance(current,(int,float)) or current<0:raise ValueError('Invalid starter tool stock')
  if current!=0:continue
  state['inventory'][ident]=amount
  record=state.setdefault('starterToolRecovery',{}).setdefault(ident,{'replacements':0})
  record.update(replacements=record['replacements']+1,lastAt=at,quantity=amount,originalSeedSequence=source)
  changed=True
 if changed:
  state.setdefault('rules',{})['starter_tool_recovery']={'status':'reconstructed_local_fallback','evidence':'original FTUE initial inventory; original material category12; no original crafting task rewards these tools','policy':'replace an exhausted uncraftable starter tool with its authored starting quantity at login or task collection; no gems, XP or changes to craftable/nonstarter tools'}
  state['revision']+=1;state['updatedAt']=at
 return changed
