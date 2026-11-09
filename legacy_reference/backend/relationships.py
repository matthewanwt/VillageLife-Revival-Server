"""Original dating wire formats; explicit local NPC provider, never human consent."""
import copy,hashlib,json
import family,world
SERVICES={'ClientVillagerService/Breakup','ClientVillager/GetCommunityVillagers','ClientVillagerService/OptIntoCommunity','ClientWant/GenerateRelationshipWants','ClientWant/SatisfyRelationshipWant','ClientRequest/AcceptDatingRequest','ClientVillagerService/GetPartnerVillager','ClientDeviceService/Push','ClientVillager/CommunityDateReceived'}

def dateable(person,at):
 return world.current_villager_type(person,at).get('isDateable')=='1' and not any(int(r['type']) in {2,4} for r in person.get('relations',[]))

def ensure_pool(state,owner_id,at):
 old=state.get('npcDatingPool',[]);expiry=int(world.global_value('communityDatesExpiry'));count=int(world.global_value('communityDatesAvailable'))
 pending={r['candidateId'] for r in state.get('npcDateRequests',[]) if r['status']=='pending' and not r['deleted'] and at-r['createdAt']<expiry}
 # Keep partners and outstanding offers intact; replace only unused stale candidates.
 pool=[p for p in old if p['relations'] or p['id'] in pending or (at-p['createdAt']<expiry and dateable(p,at))]
 serial=max(int(state.get('nextNpcSerial',1)),max((int(p['id'].split('_')[-1])+1 for p in old),default=1))
 for gender in [0,1]:
  needed=max(0,count-sum(p['gender']==gender and dateable(p,at) for p in pool))
  seeds=[r for r in world.rows('villager_starting_variation') if r.get('SpecialType','0')=='0' and int(r['Gender'])==gender and 18<=int(r['startAge'])<=39 and r.get('isPregnant','0')=='0']
  for _ in range(needed):
   seed=sorted(seeds,key=lambda r:hashlib.sha256((str(owner_id)+':'+str(serial)+':'+r['id']).encode()).hexdigest())[0]
   digest=int(hashlib.sha256((str(owner_id)+':npc:'+str(serial)).encode()).hexdigest()[:12],16)
   npc_owner=str(800000000000000+digest);raw=str(serial);serial+=1
   pool.append({'id':'Villager_'+npc_owner+'_'+raw,'ownerUserId':npc_owner,'ownerKind':'npc','seedId':seed['id'],'name':seed['name'],'equipment':seed['equipment'],'genetics':seed['genetics'],'templateId':int(seed['villagerType']),'startAge':int(seed['startAge']),'bornAt':at,'gender':gender,'rarity':0,'skills':[],'relations':[],'pregnant':'false','createdAt':at})
 if pool==old and 'npcDatingPool' in state:return False
 state['npcDatingPool']=pool;state['nextNpcSerial']=serial
 state.setdefault('rules',{})['npc_dating']={'status':'reconstructed_local_provider','evidence':'original GetCommunityVillagers/DateRequestParseCommunityDates encoded data contract; authored adult variations; communityDatesAvailable and communityDatesExpiry','policy':'explicit private NPC owners and persistent identities; keep partners and unexpired pending offers; replenish unused stale candidates on list access; never auto-consent or mutate a human player; original matchmaking algorithm unavailable'}
 return True

def candidate(person):
 user={'id':person['ownerUserId'],'name':'Local NPC Village','firstname':'Local NPC','identifier':{'pId':person['ownerUserId'],'fbId':'0'},'IsTablet':'true','Locale':'en'}
 villager={k:copy.deepcopy(person[k]) for k in ['id','name','equipment','startAge','bornAt','gender','skills']}
 villager.update(villagerTypeId=person['templateId'],Rarity=person['rarity'],rarity=person['rarity'],pregnant=0)
 return {'user':user,'villager':villager,'skills':copy.deepcopy(person['skills'])}

def catalogue(state,data,at,owner_id):
 gender=data.get('Gender')
 if isinstance(gender,bool) or not isinstance(gender,(str,int)) or str(gender) not in {'0','1'}:raise ValueError('Original Gender0 or1 required')
 changed=ensure_pool(state,owner_id,at)
 entries=[]
 for person in state['npcDatingPool']:
  if person['gender']==int(gender) and dateable(person,at):entries.append({'IsTablet':'true','Locale':'en','data':json.dumps(candidate(person),separators=(',',':'))})
 return {'result':entries[:int(world.global_value('communityDatesAvailable'))]},changed

def generate(state,at):
 wants=state.setdefault('wants',[]);changed=False;interval=int(world.global_value('WantIntervalRelationship'))
 for person in family.actors(state):
  if any(w['VillagerStringID']==person['id'] and w['wantableCategoryType']==5 for w in wants):continue
  material=340
  if not dateable(person,at):
   partner=next((r['villagerId'] for r in person.get('relations',[]) if int(r['type'])==4),None)
   accepted=next((r for r in state.get('npcDateRequests',[]) if r['localVillagerId']==person['id'] and r['candidateId']==partner and r['status']=='accepted'),None)
   if not accepted or at-accepted['acceptedAt']<int(world.global_value('marriage_want_delay')):continue
   if any(r['localVillagerId']==person['id'] and r['status'] in {'accepted','prepared'} for r in state.get('npcMarriageRequests',[])):continue
   import marriage
   try:marriage.pair(state,person['id'],partner,at)
   except (ValueError,PermissionError):continue
   material=342
  if at-state.get('relationshipWantSatisfiedAt',{}).get(person['id'],-interval)<interval:continue
  ident=int(state.get('nextWantId',1));state['nextWantId']=ident+1
  wants.append({'WantId':ident,'VillagerStringID':person['id'],'MaterialID':material,'wantableCategoryType':5,'updatedAt':at});changed=True
 return {'result':copy.deepcopy(wants)},changed

def npc(state,ident):
 value=next((p for p in state.get('npcDatingPool',[]) if p['id']==ident and p['ownerKind']=='npc'),None)
 if value is None:raise PermissionError('Unknown private NPC candidate')
 return value

def community(state,service,data,at,owner_id):
 import native_identity
 _,_,raw_in,_=native_identity.mappings(state,owner_id)
 records=state.get('npcDateRequests',[])
 if service=='CharacterRequest/Create':
  owners=data.get('ForUserIds');characters=data.get('CharacterIds')
  if not isinstance(owners,list) or not isinstance(characters,list) or len(owners)!=len(characters) or not 1<=len(owners)<=25:raise ValueError('Matching original recipient lists required')
  local_id=raw_in.get(str(data.get('FriendCharacterId')))
  person=family.actor(state,local_id)
  if not dateable(person,at) or not person.get('communityOptIn'):raise ValueError('An opted-in single adult is required')
  targets=[]
  for owner,raw in zip(owners,characters):
   candidate_id='Villager_'+str(owner)+'_'+str(raw);target=npc(state,candidate_id)
   if not dateable(target,at) or target['gender']==person['gender']:raise ValueError('Candidate is not eligible for this date')
   targets.append(target)
  changed=False
  state.setdefault('npcDateRequests',records)
  for target in targets:
   if any(r['localVillagerId']==local_id and r['candidateId']==target['id'] and r['status'] in {'pending','accepted'} for r in records):continue
   ident=str(int(state.get('nextNpcDateRequestId',1000000)));state['nextNpcDateRequestId']=int(ident)+1
   records.append({'id':ident,'localVillagerId':local_id,'candidateId':target['id'],'status':'pending','createdAt':at,'readyAt':at+int(world.global_value('date_return_time_seconds')),'deleted':False});changed=True
  return {},changed
 if service=='CharacterRequest/GetReceived':
  result=[]
  outward,_,_,_=native_identity.mappings(state,owner_id)
  for record in records:
   if record['status']!='pending' or record['deleted'] or at<record['readyAt']:continue
   if at-record['createdAt']>=int(world.global_value('communityDatesExpiry')):continue
   target=npc(state,record['candidateId']);person=family.actor(state,record['localVillagerId'])
   if not dateable(person,at) or not dateable(target,at):continue
   appearance={**candidate(target)['villager'],'stars':1,'SenderUserName':'Local NPC Village'}
   # Explicit reconstructed NPC reply, delivered through the original incoming-date UI.
   result.append({'ID':record['id'],'ByUserID':target['ownerUserId'],'ForUserID':str(owner_id),'CharacterID':outward[person['id']].split('_')[-1],'FriendCharacterID':target['id'].split('_')[-1],'FriendCharacterAppearance':json.dumps(appearance,separators=(',',':')),'createdAt':record['readyAt']})
  return {'CharacterRequests':result},False
 if service=='CharacterRequest/Delete':
  ids=data.get('CharacterRequestIds')
  if not isinstance(ids,list) or not 1<=len(ids)<=100:raise ValueError('CharacterRequestIds list required')
  selected=[]
  for ident in ids:
   record=next((r for r in records if r['id']==str(ident)),None)
   if record is None:raise PermissionError('Date request does not belong to this village')
   selected.append(record)
  changed=False
  for record in selected:
   if not record['deleted']:record['deleted']=True;changed=True
   if record['status']=='pending':record['status']='rejected'
  return {},changed
 raise NotImplementedError('Community relationship action not implemented')

def accept_date(state,data,at):
 record=next((r for r in state.get('npcDateRequests',[]) if r['id']==str(data.get('RequestID'))),None)
 if record is None:raise PermissionError('Unknown date request in this village')
 if record['status']=='accepted':return {},False
 if record['status']!='pending' or record['deleted'] or at<record['readyAt'] or at-record['createdAt']>=int(world.global_value('communityDatesExpiry')):raise ValueError('Date request is not available')
 person=family.actor(state,record['localVillagerId']);target=npc(state,record['candidateId'])
 if not dateable(person,at) or not dateable(target,at):raise ValueError('Both villagers must still be single eligible adults')
 family.add_relation(person,target,4);family.add_relation(target,person,4)
 state.setdefault('externalVillagers',{})[target['id']]=copy.deepcopy(target)
 record['status']='accepted';record['acceptedAt']=at
 for other in state.get('npcDateRequests',[]):
  if other is not record and other['status']=='pending' and (other['localVillagerId']==person['id'] or other['candidateId']==target['id']):other['status']='superseded'
 state['wants']=[w for w in state.get('wants',[]) if not (w['VillagerStringID']==person['id'] and w['wantableCategoryType']==5)]
 state.setdefault('relationshipWantSatisfiedAt',{})[person['id']]=at
 return {},True

def breakup(state,data,at):
 """Original Breakup contract, restricted to this player's private NPC partner."""
 person=family.actor(state,data.get('villagerId'));target=npc(state,data.get('partnerVillagerId'))
 records=[r for r in state.get('npcDateRequests',[]) if r['localVillagerId']==person['id'] and r['candidateId']==target['id']]
 mine=any(r['villagerId']==target['id'] and int(r['type'])==4 for r in person['relations'])
 theirs=any(r['villagerId']==person['id'] and int(r['type'])==4 for r in target['relations'])
 if not mine and not theirs:
  if any(r['status']=='broken_up' for r in records):return {},False
  raise ValueError('These villagers are not dating')
 if not mine or not theirs:raise ValueError('Dating relationship is inconsistent')
 # Never turn this operation into divorce or mutate another player's villager.
 if any(int(r['type'])==2 for p in [person,target] for r in p['relations']):raise ValueError('Breakup cannot end a marriage')
 if not any(r['status']=='accepted' for r in records):raise ValueError('Accepted NPC date record required')
 person['relations']=[r for r in person['relations'] if not (r['villagerId']==target['id'] and int(r['type'])==4)]
 target['relations']=[r for r in target['relations'] if not (r['villagerId']==person['id'] and int(r['type'])==4)]
 for record in records:
  if record['status']=='accepted':record.update(status='broken_up',brokenUpAt=at)
 external=state.setdefault('externalVillagers',{})
 if any(r['villagerId']==target['id'] for p in family.actors(state) for r in p['relations']):external[target['id']]=copy.deepcopy(target)
 else:external.pop(target['id'],None)
 state['wants']=[w for w in state.get('wants',[]) if not (w['VillagerStringID']==person['id'] and w['wantableCategoryType'] in {5,6})]
 state.setdefault('relationshipWantSatisfiedAt',{})[person['id']]=at
 for request in state.get('npcMarriageRequests',[]):
  if request['localVillagerId']==person['id'] and request['candidateId']==target['id'] and request['status'] in {'accepted','prepared'}:request.update(status='cancelled',cancelledAt=at,hidden=True)
 return {},True

def operate(state,service,data,at,owner_id):
 if service=='ClientVillagerService/Breakup':response,changed=breakup(state,data,at)
 elif service=='ClientRequest/AcceptDatingRequest':response,changed=accept_date(state,data,at)
 elif service=='ClientVillagerService/GetPartnerVillager':
  person=family.actor(state,data.get('villagerId'));partner=next((r['villagerId'] for r in person['relations'] if int(r['type'])==4),None)
  if partner is None:raise ValueError('Villager has no dating partner')
  response=candidate(npc(state,partner));changed=False
 elif service in {'ClientDeviceService/Push','ClientVillager/CommunityDateReceived'}:
  key='UserIDs' if service.endswith('/Push') else 'VillagerIDs';ids=data.get(key)
  allowed={p['ownerUserId'] if key=='UserIDs' else p['id'].split('_')[-1] for p in state.get('npcDatingPool',[])}
  if not isinstance(ids,list) or not ids or any(str(i) not in allowed for i in ids):raise NotImplementedError('External player notifications require the multiplayer provider')
  response={};changed=False # Local NPC requests use the saved community inbox; no external push.
 elif service=='ClientVillager/GetCommunityVillagers':response,changed=catalogue(state,data,at,owner_id)
 elif service=='ClientVillagerService/OptIntoCommunity':
  person=family.actor(state,data.get('villagerId'))
  if not dateable(person,at):raise ValueError('Villager is not eligible to date')
  changed=not person.get('communityOptIn',False);person['communityOptIn']=True;response={}
 elif service=='ClientWant/GenerateRelationshipWants':response,changed=generate(state,at)
 elif service=='ClientWant/SatisfyRelationshipWant':
  person=family.actor(state,data.get('VillagerStringID'));before=state.get('wants',[])
  removed=[w for w in before if w['VillagerStringID']==person['id'] and w['wantableCategoryType']==5]
  state['wants']=[w for w in before if w not in removed];changed=bool(removed)
  if changed:state.setdefault('relationshipWantSatisfiedAt',{})[person['id']]=at
  response={'result':{'SatisfiedWantModels':[{'WantId':w['WantId'],'VillagerStringID':person['id']} for w in removed]}}
 else:raise NotImplementedError('Unrecovered relationship operation')
 if changed:state['revision']+=1;state['updatedAt']=at
 return response,changed
