"""Original quest-type and story definitions with persistent, validated objectives."""
import uuid,copy
from decimal import Decimal
import world

def lookup(table,ident):
 try:return world.by_id(table,ident)
 except StopIteration:raise ValueError('Unknown '+table+' identifier') from None

def add(state,data,at):
 typ=data.get('questTypeId');obj=str(data.get('objectId',''));amount=data.get('amount',1)
 if isinstance(typ,bool) or not isinstance(typ,int) or isinstance(amount,bool) or not isinstance(amount,(int,float)) or amount<=0:raise ValueError('Invalid quest request')
 definition=lookup('quest_type',typ);target=definition['targetObjectType']
 if target not in {'material_type','building_task','story','progression_object','fire_type','decor_item','quest_item','interactive_activity'}:raise NotImplementedError('Quest objective rules not recovered: '+target)
 lookup(target,obj)
 for q in state['quests']:
  if q['questTypeId']==typ and q['objectId']==obj:return {'userQuest':copy.deepcopy(q)},False
 q={'id':'local-quest-'+uuid.uuid4().hex,'questTypeId':typ,'objectId':obj,'amount':amount,'createdAt':at,'villagerId':str(data.get('villagerId',''))}
 state['quests'].append(q);state['revision']+=1
 return {'userQuest':copy.deepcopy(q)},True

def complete(state,data,at):
 ident=data.get('userQuestId')
 if not isinstance(ident,str):raise ValueError('Quest identifier required')
 if ident in state.get('completedQuests',{}):return copy.deepcopy(state['completedQuests'][ident]['response']),False
 q=next((v for v in state['quests'] if v['id']==ident),None)
 if q is None:raise ValueError('Unknown local quest')
 target=lookup('quest_type',q['questTypeId'])['targetObjectType'];obj=q['objectId'];amount=q['amount'];reward_set='0'
 if target=='story':
  story=lookup('story',obj);target=lookup('quest_type',story['questType'])['targetObjectType'];obj=story['questObjectId'];amount=float(story['questAmount']);reward_set=story['rewardSet']
 if target=='interactive_activity':
  matches=[r for r in state.get('interactiveReceipts',{}).values() if r['participants'][2]==str(obj) and r['completionTime']<=at and r['startedAt']>=q.get('createdAt',0) and (not q.get('villagerId') or q['villagerId'] in r['participants'][:2])]
  if len(matches)<amount:raise ValueError('Interactive quest objective has not completed')
 elif target=='material_type':
  if state['inventory'].get(str(obj),0)<amount:raise ValueError('Quest objective has not been reached')
 else:raise NotImplementedError('Quest completion condition not recovered: '+target)
 reward_rows=[] if reward_set=='0' else [v for v in world.rows('reward_set_item') if v['setId']==reward_set]
 if any(Decimal(v['chance'])!=1 for v in reward_rows):raise NotImplementedError('Quest reward probability rule not recovered')
 for reward in reward_rows:
  key=reward['materialType'];state['inventory'][key]=float(Decimal(str(state['inventory'].get(key,0)))+Decimal(reward['quantity']))
 import tasks
 response={'inventory':tasks.inventory(state)}
 state['quests']=[v for v in state['quests'] if v['id']!=ident];state.setdefault('completedQuests',{})[ident]={'quest':q,'completedAt':at,'response':copy.deepcopy(response)};state['revision']+=1
 return response,True
