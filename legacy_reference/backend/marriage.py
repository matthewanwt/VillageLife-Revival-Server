"""Original marriage contracts; reconstructed private-NPC consent and tie policy."""
import copy
import family,world,relationships
SERVICES={'ClientUserService/GetUserNotifications','ClientUserService/HandleUserMessages','ClientRequestService/SendMarriageRequest','ClientRequestService/GetPaginatedSentRequests','ClientRequestService/GetPaginatedReceivedRequests','ClientRelationship/PrepareWedding','ClientNotification/ProcessAcceptedProposal','ClientRequestService/DeleteUserRequests','ClientVillagerService/GetNeighborVillagers','ClientUser/TrackMarriageAchievement','ClientUserService/HandleUserNotification'}

def pair(state,person_id,target_id,at):
 person=family.actor(state,person_id);target=relationships.npc(state,target_id)
 if person['gender']==target['gender']:raise ValueError('Original marriage requires opposite genders')
 for p,other in [(person,target),(target,person)]:
  if not int(world.global_value('minAgeForDating'))<=world.current_age(p,at)<=int(world.global_value('maxAgeForMarriage')):raise ValueError('Villager is outside original marriage age bounds')
  links=[r for r in p['relations'] if int(r['type']) in {2,4}]
  if len(links)!=1 or links[0]['villagerId']!=other['id'] or int(links[0]['type'])!=4:raise ValueError('A reciprocal dating pair is required')
 return person,target

def request_record(state,data):
 ids=[str(data[k]) for k in ['RequestID','RequestStringID','userRequestId'] if k in data and str(data[k]) not in {'','0','-1'}]
 if not ids or len(set(ids))!=1:raise ValueError('One matching marriage request identifier required')
 record=next((r for r in state.get('npcMarriageRequests',[]) if r['id']==ids[0]),None)
 if record is None:raise PermissionError('Marriage request does not belong to this village')
 return record

def request_wire(state,record,at,owner):
 person=family.actor(state,record['localVillagerId']);target=record['npcSnapshot']
 sender={'user':{'id':str(owner),'name':state['user'].get('name','Your village'),'firstname':'','IsTablet':'true','Locale':'en'},'villager':{'id':person['id'],'name':person['name'],'equipment':person['equipment'],'pregnant':int(family.is_pregnant(person)),'villagerTypeId':int(world.current_villager_type(person,at)['id']),'rarity':person.get('rarity',0)}}
 recipient=relationships.candidate(target)
 return {'id':int(record['id']),'userRequestId':record['id'],'requestTypeId':1,'requestStatusTypeId':1 if at>=record['readyAt'] else 0,'createdAt':record['createdAt'],'isIncoming':'false','isCommunityVillager':1,'sender':sender,'recipient':recipient}

def notification_id(record):return str(4000000+int(record['id']))

def notifications(state,at,owner):
 return [*copy.deepcopy(state.get('notifications',[])),*[{'id':notification_id(r),'notificationTypeId':12,'createdAt':r['readyAt'],'data':request_wire(state,r,at,owner)} for r in state.get('npcMarriageRequests',[]) if r['status'] in {'accepted','prepared'} and at>=r['readyAt'] and not r.get('notificationHandled',False)]]

def message_id(record):return str(8000000+int(record['id']))

def messages(state,at,owner):
 # ServerProcessMessages dispatches messageTypeId7 to NotificationParser;
 # its data is the same native type12 notification used at startup.
 ready={n['id']:n for n in notifications(state,at,owner) if n.get('notificationTypeId')==12}
 return [{'id':message_id(r),'messageTypeId':7,'data':ready[notification_id(r)]} for r in state.get('npcMarriageRequests',[]) if notification_id(r) in ready and not r.get('messageHandled',False)]

def propose(state,data,at,owner):
 person=family.actor(state,data.get('senderVillagerId'));target_id=data.get('recipientVillagerId')
 existing=next((r for r in state.get('npcMarriageRequests',[]) if r['localVillagerId']==person['id'] and r['candidateId']==target_id and r['status'] in {'accepted','prepared','completed'}),None)
 if existing:
  if str(data.get('recipientUserId'))!=existing['npcSnapshot']['ownerUserId']:raise PermissionError('Wrong NPC village owner')
  return {'userRequest':request_wire(state,existing,at,owner)},False
 person,target=pair(state,person['id'],target_id,at)
 if str(data.get('recipientUserId'))!=target['ownerUserId']:raise PermissionError('Wrong NPC village owner')
 # The original UI displays one star and sends the zero-based stars value0. More-skilled hosting
 # must be recovered before accepting an unverified higher-star claim.
 stars=data.get('stars')
 if isinstance(stars,bool) or not str(stars).isdigit() or not 0<=int(stars)<=6:raise ValueError('Original marriage star value required')
 if int(stars) not in {int(person.get('rarity',0)),int(target.get('rarity',0))}:raise ValueError('Marriage star value does not match either saved partner')
 # Derive hosting from saved actors; a high-star local villager must not be
 # blocked from inviting a lower-star NPC by the old one-star-only fallback.
 if int(target.get('rarity',0))>int(person.get('rarity',0)):raise ValueError('The higher-star NPC would host this wedding; outward transfers are not supported')
 if family.free_places(state)<1:raise ValueError('Village population capacity reached')
 if any(r['status'] in {'accepted','prepared'} and (r['localVillagerId']==person['id'] or r['candidateId']==target['id']) for r in state.get('npcMarriageRequests',[])):raise ValueError('An active marriage proposal already exists')
 ident=str(int(state.get('nextNpcMarriageRequestId',2000000)))
 record={'id':ident,'localVillagerId':person['id'],'candidateId':target['id'],'npcSnapshot':copy.deepcopy(target),'status':'accepted','createdAt':at,'readyAt':at+int(world.global_value('date_return_time_seconds')),'hostUserId':str(owner),'guestUserId':target['ownerUserId'],'hidden':False}
 state.setdefault('npcMarriageRequests',[]).append(record);state['nextNpcMarriageRequestId']=int(ident)+1
 state['wants']=[w for w in state.get('wants',[]) if not (w['VillagerStringID']==person['id'] and w['wantableCategoryType']==5)]
 state.setdefault('rules',{})['npc_marriage']={'status':'reconstructed_private_npc_policy','evidence':'original SendMarriageRequest, PrepareWedding, PlaceWeddingGuests and ProcessAcceptedProposal client contracts; requestStatusTypeId1 accepted','policy':'private NPC consent after original date reply delay; equal one-star couples stay with local player; higher-star transfers explicitly blocked pending recovery; capacity rechecked at commit; no invented wedding XP; human consent never simulated'}
 return {'userRequest':request_wire(state,record,at,owner)},True

def wedding_actor(person,at):
 return {'Name':person['name'],'VillagerType':int(world.current_villager_type(person,at)['id']),'IsPregnant':'true' if family.is_pregnant(person) else 'false','Xp':person.get('xp',0),'Equipment':person['equipment']}

def prepare(state,data,at,owner):
 record=request_record(state,data)
 if record['status'] not in {'accepted','prepared','completed'} or at<record['readyAt']:raise ValueError('Marriage request is not ready')
 person=family.actor(state,record['localVillagerId']);target=record['npcSnapshot']
 if record['status']!='completed':
  person,target=pair(state,person['id'],record['candidateId'],at)
  if family.free_places(state)<1:raise ValueError('Village population capacity reached')
 changed=record['status']=='accepted'
 if changed:record.update(status='prepared',preparedAt=at)
 bride,groom=(person,target) if int(person['gender']) else (target,person)
 return {'result':{'Bride':wedding_actor(bride,at),'Groom':wedding_actor(groom,at),'Congregation':[],'NeighbourCongregation':[],'IsUserBride':'true' if person['gender'] else 'false','IsUserHost':'true'},'data':{'users':{'host':{'id':str(owner),'name':'Your village'},'guest':{'id':record['guestUserId'],'name':'Local NPC Village'}},'villagers':{'host':{'id':person['id'],'name':person['name']},'guest':{'id':record['candidateId'],'name':target['name']}}}},changed

def complete(state,data,at,owner):
 record=request_record(state,data)
 if record['status']=='completed':return {},False
 if record['status']!='prepared':raise ValueError('Wedding must be prepared before completion')
 person,target=pair(state,record['localVillagerId'],record['candidateId'],at)
 if family.free_places(state)<1:raise ValueError('Village population capacity reached')
 # Stable canonical identity remains; native_identity projects the new owner's ID.
 moved={k:copy.deepcopy(target[k]) for k in ['id','name','equipment','genetics','templateId','startAge','bornAt','gender','rarity','skills']}
 moved['startingArea']=state['areaId']
 typ=world.current_villager_type(target,at)
 moved.update(refId='',templateType='villager_type',templateId=int(typ['id']),villagerBaseId=int(target['seedId']),serverPersisted=True,ownerUserId=str(owner),originNpcUserId=target['ownerUserId'],birthType=0,specialType=0,energyLevel=int(typ['maxEnergy']),energyTimeStamp=at,updatedAt=at,pregnant='false',pregnancyTryCount=0,pregnancyStartTime=0,xp=int(target.get('xp',0)),shelterBedId='',relations=[],wants=[],clothing=[],isCommunityVillager='false',retireAt=0,retireEventID=0,position={**person['position'],'x':person['position']['x']+40})
 for key in ['serverBirthId','familyBirthId','communityOptIn','lastChildBornAt']:moved.pop(key,None)
 person['relations']=[r for r in person['relations'] if not (r['villagerId']==target['id'] and int(r['type'])==4)]
 family.add_relation(person,moved,2);family.add_relation(moved,person,2)
 state['world']['entities'].append(moved);state['externalVillagers'].pop(target['id'],None)
 state['npcDatingPool']=[p for p in state['npcDatingPool'] if p['id']!=target['id']]
 for r in state.get('npcDateRequests',[]):
  if r['localVillagerId']==person['id'] and r['candidateId']==target['id'] and r['status']=='accepted':r['status']='married'
 record.update(status='completed',completedAt=at,hidden=True,movedVillagerId=moved['id'])
 state['wants']=[w for w in state.get('wants',[]) if not (w['VillagerStringID']==person['id'] and w['wantableCategoryType']==5)]
 return {},True

def operate(state,service,data,at,owner):
 if service=='ClientUserService/GetUserNotifications':response={'userNotifications':notifications(state,at,owner)};changed=False
 elif service.endswith('/SendMarriageRequest'):response,changed=propose(state,data,at,owner)
 elif service.endswith('/PrepareWedding'):response,changed=prepare(state,data,at,owner)
 elif service.endswith('/ProcessAcceptedProposal'):response,changed=complete(state,data,at,owner)
 elif service in {'ClientRequestService/GetPaginatedSentRequests','ClientRequestService/GetPaginatedReceivedRequests'}:
  count=data.get('count',500)
  if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=500:raise ValueError('Invalid request page size')
  records=[r for r in state.get('npcMarriageRequests',[]) if not r['hidden'] and r['status'] in {'accepted','prepared'}] if service.endswith('SentRequests') else []
  response={'userRequests':[request_wire(state,r,at,owner) for r in records[:count]]};changed=False
 elif service.endswith('/DeleteUserRequests'):
  ids=data.get('userRequestIds')
  if not isinstance(ids,str) or not ids or len(ids)>2000:raise ValueError('Original comma-separated request IDs required')
  records=[request_record(state,{'userRequestId':i.strip()}) for i in ids.split(',')];changed=False
  for record in records:
   if not record['hidden']:record['hidden']=True;changed=True
  response={}
 elif service.endswith('/GetNeighborVillagers'):
  ident=str(data.get('neighborUserId'))
  if ident==str(owner):people=family.actors(state)
  else:
   records=[r for r in state.get('npcMarriageRequests',[]) if r['guestUserId']==ident and r['status'] in {'prepared','completed'}]
   if not records:raise PermissionError('Only the prepared private NPC wedding village is available')
   people=[r['npcSnapshot'] for r in records]
  response={'villagers':[{'id':p['id'],'name':p['name'],'equipment':p['equipment'],'villagerTypeId':int(world.current_villager_type(p,at)['id']),'pregnant':int(family.is_pregnant(p)),'xp':p.get('xp',0)} for p in people]};changed=False
 elif service.endswith('/HandleUserMessages'):
  value=data.get('userMessageIds')
  if not isinstance(value,str) or not value or len(value)>2000:raise ValueError('Original comma-separated message IDs required')
  selected=[]
  for ident in value.split(','):
   record=next((r for r in state.get('npcMarriageRequests',[]) if message_id(r)==ident.strip()),None)
   if record is None:raise PermissionError('Unknown private NPC marriage message')
   selected.append(record)
  changed=any(not r.get('messageHandled',False) for r in selected)
  for record in selected:record['messageHandled']=True
  response={}
 elif service.endswith('/HandleUserNotification'):
  ident=str(data.get('userNotificationId'));record=next((r for r in state.get('npcMarriageRequests',[]) if notification_id(r)==ident),None)
  if record is None and ident!='0':raise ValueError('Unknown wedding notification')
  changed=record is not None and not record.get('notificationHandled',False)
  if changed:record['notificationHandled']=True
  response={}
 elif service.endswith('/TrackMarriageAchievement'):
  response={};changed=False # No invented reward; completion count is derivable from saved records.
 else:raise NotImplementedError(service)
 if changed:state['revision']+=1;state['updatedAt']=at
 return response,changed
