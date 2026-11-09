"""Translate private canonical villager IDs to the numeric IDs required by native RPCs.
The save is unchanged. Original community JSON interpolates the ID suffix unquoted.
"""
import copy,hashlib,json
import family
FIELDS={'requesterVillagerId','supplierVillagerId','id','ID','villagerId','VillagerStringID','VillagerStringId','relativeVillagerId','partnerVillagerId','senderVillagerId','recipientVillagerId','motherId','fatherId','neighborVillagerId','FriendCharacterId','FriendCharacterID','CharacterID','villagerIds','VillagerIDs','CharacterIds','lightingVillagerId','villagerID','VillagerID','villagerStringId','villagerStringID'}
FIELDS|={'motherVillagerId','fatherVillagerId'}

def reserve_ids(state,owner,pending_ids=()):
 if not state:return False
 registries=state.setdefault('nativeIdentityIds',{});registry=registries.setdefault(str(owner),{});used={int(v) for v in registry.values()}
 if len(used)!=len(registry) or any(v<1 or v>0xffffff for v in used):raise ValueError('Invalid saved native identity registry')
 changed=False
 for ident in [p['id'] for p in family.actors(state)]+list(pending_ids):
  if ident in registry:continue
  raw=int(hashlib.sha256((str(owner)+':'+ident).encode()).hexdigest()[:6],16) or 1
  while raw in used:raw=raw%0xffffff+1
  used.add(raw);registry[ident]=str(raw);changed=True
 return changed

def mappings(state,owner):
 outward={};inward={};raw_in={};raw_out={}
 if not state:return outward,inward,raw_in,raw_out
 reserve_ids(state,owner);registry=state['nativeIdentityIds'][str(owner)]
 for person in family.actors(state):
  raw=registry[person['id']];native='Villager_'+str(owner)+'_'+raw
  outward[person['id']]=native;inward[native]=person['id'];raw_in[raw]=person['id']
  # Accept old in-flight/string IDs without emitting the unsafe float32 suffix.
  legacy=str(int(hashlib.sha256((str(owner)+':'+person['id']).encode()).hexdigest()[:12],16)+1)
  inward['Villager_'+str(owner)+'_'+legacy]=person['id'];raw_in[legacy]=person['id']
  if person.get('serverBirthId'):raw_out[person['serverBirthId']]=raw
 return outward,inward,raw_in,raw_out

def translate(value,mapping,raw_birth=None,key=None):
 if isinstance(value,dict):return {k:translate(v,mapping,raw_birth,k) for k,v in value.items()}
 if isinstance(value,list):return [translate(v,mapping,raw_birth,key) for v in value]
 if isinstance(value,str) and key=='villagerIds' and value.lstrip().startswith(('{','[')):
  try:return json.dumps(translate(json.loads(value),mapping,raw_birth,key),separators=(',',':'))
  except (ValueError,TypeError):return value # Handler owns validation of malformed input.
 if key in FIELDS:
  if raw_birth and key=='ID' and str(value) in raw_birth:return raw_birth[str(value)]
  return mapping.get(str(value),value)
 return value

def process(request):
 import session
 with session.LOCK:
  # Authenticate before reading any player's private identity mapping.
  try:path=session.authenticated_tutorial_path(request)
  except PermissionError:return session.process(request) # Preserve per-call denial envelope; never read a save.
  saved=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
  if reserve_ids(saved.get('normal'),request['pId']):session.atomic_json(path,saved)
  _,inward,_,_=mappings(saved.get('normal'),request['pId'])
  canonical=copy.deepcopy(request)
  for call in canonical.get('data',{}).get('calls',[]):call['data']=translate(call.get('data',{}),inward)
  response=session.process(canonical)
  saved=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
  if reserve_ids(saved.get('normal'),request['pId']):session.atomic_json(path,saved)
  outward,_,_,raw_birth=mappings(saved.get('normal'),request['pId'])
  # Service results only: never translate call IDs or authentication fields.
  result=copy.deepcopy(response)
  result['messages']=translate(result.get('messages',[]),outward,raw_birth)
  for source,call in zip(canonical.get('data',{}).get('calls',[]),result.get('data',{}).get('calls',[])):
   if source.get('service')=='ClientFriendService/GetFriendStartupInfo' and call.get('code')==200:
    import social
    target=source.get('data',{}).get('friendUserId');profile,friend_saved=social.profiles(session.STATE)[target]
    friend_map,_,_,_=mappings(friend_saved.get('normal'),profile['pId'])
    call['data']=translate(call.get('data',{}),friend_map)
   else:call['data']=translate(call.get('data',{}),outward,raw_birth)
  return result
