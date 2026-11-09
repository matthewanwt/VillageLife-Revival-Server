"""Persistent original decoration placement and object movement contracts."""
import copy,uuid
from decimal import Decimal
import world,buildings,tasks,prerequisites
SERVICES={'ClientUserDecorItemService/CreateUserDecorItem','ClientUserDecorItemService/DeleteUserDecorItem','ClientUtilityService/UpdatePosition'}
EDITABLE=buildings.SUPPORTED_BUILD_KINDS|{'building_task'}

def position_id(entity):return entity.get('positionId') or entity.get('position',{}).get('id') or entity['id']+'-position'

def project_position(entity):
 if entity.get('templateType') in EDITABLE and 'position' in entity:entity['position']['id']=position_id(entity)

def reply(state,entity):
 return {'userDecorItem':{'userDecorItemId':entity['id'],'decorItemId':entity['templateId'],'position':{**entity['position'],'id':position_id(entity)}},'inventory':tasks.inventory(state)}

def requirement_quantity(state,material):
 return prerequisites.quantity(state,material)

def operate(state,service,data,key):
 if service.endswith('/UpdatePosition'):
  if not key:raise ValueError('Movement receipt required')
  ident=data.get('positionId')
  point=buildings.position(state,data);signature={'positionId':ident,**point}
  old=state.get('positionUpdateReceipts',{}).get(key)
  if old:
   if old['request']!=signature:raise ValueError('Movement receipt reused for a different position')
   # A delayed retry must not revert a newer move or resurrect a deleted item.
   return {},False
  matches=[e for e in state['world']['entities'] if e['templateType'] in EDITABLE and position_id(e)==ident and world.entity_area(e)==state['areaId']]
  if len(matches)!=1:raise ValueError('Saved editable position required')
  entity=matches[0];moves=any(entity['position'].get(k)!=v for k,v in point.items())
  if moves and any(j['sourceId']==entity['id'] and j['status']!='harvested' for j in state.get('workAreas',{}).values()):raise ValueError('Complete and collect construction before moving this object')
  if moves:entity['position'].update(point)
  # Record even an accepted no-op, otherwise its retry can undo a later move.
  state.setdefault('positionUpdateReceipts',{})[key]={'request':signature,'entityId':entity['id']}
  state['revision']+=1;return {},True
 if service.endswith('/DeleteUserDecorItem'):
  ident=data.get('userDecorItemId')
  if ident in state.get('deletedDecorItems',[]):return {},False
  entity=next((e for e in state['world']['entities'] if e['id']==ident and e['templateType']=='decor_item'),None)
  if entity is None:raise ValueError('Unknown saved decoration')
  state['world']['entities'].remove(entity);state.setdefault('deletedDecorItems',[]).append(ident);state['revision']+=1;return {},True
 if not key:raise ValueError('Decoration placement receipt required')
 ident=data.get('decorItemId')
 if isinstance(ident,bool) or not isinstance(ident,int):raise ValueError('Original decoration identifier required')
 point=buildings.position(state,data);signature={'decorItemId':ident,**point}
 old=state.get('decorPlacementReceipts',{}).get(key)
 if old:
  if old['request']!=signature:raise ValueError('Placement receipt reused for another object')
  entity=next((e for e in state['world']['entities'] if e['id']==old['entityId']),None)
  return reply(state,entity) if entity else {'inventory':tasks.inventory(state)},False
 try:definition=world.by_id('decor_item',ident)
 except StopIteration:raise ValueError('Unknown original decoration') from None
 material=definition['material_type'];owned=state['inventory'].get(material,0)>=1
 if not owned:
  if definition['hidden']=='1':raise ValueError('This decoration is not offered by the original shop')
  for req in world.rows('requirement_set_item'):
   if definition['requirement_set']!='0' and req['requirementSet']==definition['requirement_set'] and requirement_quantity(state,req['materialType'])<Decimal(req['quantity']):raise ValueError('Original decoration unlock requirement not met')
  costs={'323':int(definition['price_gems']),'325':int(definition['price_coins'])}
  if any(amount<0 or state['inventory'].get(k,0)<amount for k,amount in costs.items()):raise ValueError('Not enough decoration currency')
 else:costs={material:1}
 for k,amount in costs.items():state['inventory'][k]=state['inventory'].get(k,0)-amount
 entity={'id':'local-decor-'+uuid.uuid4().hex,'templateType':'decor_item','templateId':ident,'serverPersisted':True,'localCreated':True,'position':point}
 state['world']['entities'].append(entity);state.setdefault('decorPlacementReceipts',{})[key]={'request':signature,'entityId':entity['id'],'costs':costs}
 state.setdefault('rules',{})['decoration_placement']={'status':'original_contract_reconstructed_server_policy','evidence':'Script2354 request, Script2408 listener, original decor_item prices and requirement set; canonical bridge-1-to-2 transition satisfies non-consumed Bridge130 milestone','policy':'consume an owned decoration first, otherwise charge original shop currencies; recognize only the proven completed bridge milestone without granting stock; one object per saved receipt; native client checks collision/preview; preserve original placement coordinates and stable position IDs; deletion does not invent a refund'}
 state['revision']+=1;return reply(state,entity),True
