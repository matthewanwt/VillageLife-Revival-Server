"""Original family wire contracts with explicitly reconstructed server policies."""
import copy,hashlib,json,secrets,uuid,struct,math
import world,tasks
WISH_SERVICES={'ClientWant/GenerateBirthWants','ClientWant/GenerateChildWants'}
SERVICES=WISH_SERVICES|{'ClientVillager/CanConcievePregnancy','ClientVillager/SkipRetryConcievePregnancy','ClientVillager/DesignPregnancy','ClientVillager/Birth','ClientVillagerService/SetName','ClientVillagerService/SkipPregnancy'}

READ_SERVICES={'ClientVillagerService/GetVillagerRelations','ClientVillagerService/GetVillagerSkills'}

def skills(state,data):
 # Original wrappers send a JSON object encoded inside the villagerIds string.
 value=data.get('villagerIds')
 if not isinstance(value,str) or len(value)>20000:raise ValueError('Encoded villagerIds object required')
 try:parsed=json.loads(value)
 except (ValueError,TypeError) as error:raise ValueError('Invalid encoded villagerIds') from error
 ids=parsed.get('villagerIds') if isinstance(parsed,dict) else None
 if not isinstance(ids,list) or not 1<=len(ids)<=100 or any(not isinstance(i,str) or not i for i in ids):raise ValueError('Invalid villagerIds list')
 allowed={p['id']:p for p in actors(state)}
 allowed.update({p['id']:p for p in state.get('npcDatingPool',[]) if p.get('ownerKind')=='npc'})
 if any(i not in allowed for i in ids):raise ValueError('Unknown villager in this village or its private NPC pool')
 people=[allowed[i] for i in dict.fromkeys(ids)];result=[]
 for person in people:
  for skill in person.get('skills',[]):
   kind=int(skill['skilltypeId'] if 'skilltypeId' in skill else skill['skillTypeId'])
   world.by_id('villager_skill',kind)
   result.append({'villagerId':person['id'],'skilltypeId':kind,'skillOriginType':int(skill['skillOriginType'])})
 return {'villagerSkills':result}

def history(state,data,at,owner_id):
 # VillageHistoryModelParse reads these two arrays at the response root.
 # Canonical relationship groups differ from the gendered relation_type row IDs.
 if str(data.get('userId',''))!=str(owner_id):raise PermissionError('Family history is limited to the authenticated village')
 people=actors(state)+list(state.get('externalVillagers',{}).values());by_id={p['id']:p for p in people};villagers=[];relations=[]
 kinds={(int(r['Relationship']),int(r['genderTypeId'])):int(r['id']) for r in world.rows('relation_type')}
 for person in people:
  villagers.append({'id':person['id'],'name':person['name'],'birthType':int(person.get('birthType',0)),'startAge':person['startAge'],'bornAt':person['bornAt'],'villagerTypeId':int(world.current_villager_type(person,at)['id']),'equipment':person['equipment'],'gender':int(person['gender']),'userId':str(person.get('ownerUserId',owner_id)),'neighborUserId':'','neighborVillagerId':''})
  for relation in person.get('relations',[]):
   relative=by_id.get(relation['villagerId'])
   if relative is None:raise ValueError('Unresolved family-history relative')
   # ProcessFamilyTree consumes subject-role rows: a child's outgoing 2/3
   # edges identify its parents; incoming 2/3 edges identify its children.
   # This differs from the world's relative-role projection.
   group=int(relation['type']);group={0:1,1:0}.get(group,group)
   kind=kinds[(group,int(person['gender']))]
   ident=hashlib.sha256((person['id']+':'+relative['id']+':'+str(kind)).encode()).hexdigest()
   relations.append({'id':ident,'villagerId':person['id'],'relativeVillagerId':relative['id'],'relationTypeId':kind,'createdAt':max(person['bornAt'],relative['bornAt'])})
 return {'villagers':villagers,'villagerRelations':relations}

def child_wish_eligible(state,mother,at):
 try:mother,father=couple(state,mother['id'],at)
 except ValueError:return False
 if is_pregnant(mother) or free_places(state)<1:return False
 married_at=max(mother.get('marriedAt',0),father.get('marriedAt',0),state.get('createdAt',at))
 for record in state.get('npcMarriageRequests',[]):
  if record['status']=='completed' and {record['localVillagerId'],record.get('movedVillagerId')}=={mother['id'],father['id']}:married_at=max(married_at,record['completedAt'])
 if at-married_at<int(world.global_value('childWantDelayAfterMarriage')):return False
 last=state.get('pregnancies',{}).get(mother['id'],{})
 last_birth=max(mother.get('lastChildBornAt',0),father.get('lastChildBornAt',0),last.get('bornAt',0) if last.get('status')=='born' else 0)
 if last_birth and at-last_birth<int(world.global_value('childWantDelayAfterLastChild')):return False
 if state.get('areaId')==2:
  # Authored Riverside limits. Selection/random pacing on the old server is unknown.
  if population(state)>=int(world.global_value('maxVillagersForChildWantArea2')):return False
  child_ids={r['villagerId'] for r in mother['relations'] if int(r['type'])==1}
  child_ids.update(p['id'] for p in actors(state) if any(int(r['type'])==0 and r['villagerId']==mother['id'] for r in p['relations']))
  if any(world.current_age(actor(state,ident),at)<int(world.global_value('ageOfMaxChildrenForChildWantArea2')) for ident in child_ids):return False
 return True

def generate_child_wishes(state,at):
 people={p['id']:p for p in actors(state)};before=state.get('wants',[])
 eligible={p['id'] for p in people.values() if int(p['gender'])==1 and child_wish_eligible(state,p,at)}
 kept=[w for w in before if not (w['MaterialID']==343 and w['wantableCategoryType']==5 and w['VillagerStringID'] not in eligible)]
 changed=kept!=before;state['wants']=kept
 for ident in sorted(eligible):
  if any(w['VillagerStringID']==ident and w['wantableCategoryType']==5 for w in kept):continue
  last=state.get('childWantGeneratedAt',{}).get(ident)
  if last is not None and at-last<int(world.global_value('waitDurationAfterLastChildWantGen')):continue
  record=state.get('pregnancies',{}).get(ident,{})
  if record.get('status')=='failed' and at-record['attemptedAt']<int(world.global_value('pregnancySkipRetryDuration')):continue
  want_id=int(state.get('nextWantId',1));state['nextWantId']=want_id+1
  kept.append({'WantId':want_id,'VillagerStringID':ident,'MaterialID':343,'wantableCategoryType':5,'updatedAt':at})
  state.setdefault('childWantGeneratedAt',{})[ident]=at;changed=True
 policy={'status':'reconstructed_eligibility_using_original_wire_and_globals','evidence':'DoWantAction category5/material343 calls CanConcievePregnancy; original childWant age/wait globals','policy':'one persistent wish per eligible owned mother; reciprocal adult spouses in one hut; capacity and post-marriage/post-birth bounds; original Riverside population/young-child limits; per-mother generation interval reconstructed; no spontaneous pregnancy or invented server selection randomness'}
 if state.get('rules',{}).get('child_wishes')!=policy:state.setdefault('rules',{})['child_wishes']=policy;changed=True
 return {'result':copy.deepcopy(kept)},changed

def roll(limit):return secrets.randbelow(limit)
def actors(state):return [e for e in state['world']['entities'] if e['templateType']=='villager_type']
def actor(state,ident):
 value=next((a for a in actors(state) if a['id']==ident),None)
 if value is None:raise ValueError('Unknown villager in this village')
 return value

def is_pregnant(person):return str(person.get('pregnant','false')).lower() in {'true','1'}
def spouse(state,person):
 ids=[r['villagerId'] for r in person.get('relations',[]) if int(r['type'])==2]
 if len(ids)!=1:raise ValueError('A single married partner is required')
 other=actor(state,ids[0])
 if not any(r['villagerId']==person['id'] and int(r['type'])==2 for r in other.get('relations',[])):raise ValueError('Marriage references must agree')
 return other

def couple(state,mother_id,at,require_beds=True):
 mother=actor(state,mother_id);father=spouse(state,mother)
 if int(mother['gender'])!=1 or int(father['gender'])!=0:raise ValueError('Original pregnancy requires an adult mother and father')
 if world.current_age(mother,at)<int(world.global_value('minAgeForDating')) or world.current_age(father,at)<int(world.global_value('minAgeForDating')):raise ValueError('Both parents must be adults')
 if world.current_age(mother,at)>int(world.global_value('childWantFemaleMaxAge')):raise ValueError('Mother is outside the original child-want age range')
 if require_beds:
  beds={b['id']:(e,b) for e in state['world']['entities'] if e['templateType']=='shelter' for b in e.get('beds',[])}
  mb=beds.get(mother.get('shelterBedId'));fb=beds.get(father.get('shelterBedId'))
  if not mb or not fb or mb[0]['id']!=fb[0]['id'] or mb[1].get('villagerId')!=mother['id'] or fb[1].get('villagerId')!=father['id']:raise ValueError('Both married parents must occupy the same shelter')
 return mother,father

def population(state):return sum(world.by_id('villager_type',p['templateId'])['name']!='Dog Villager' for p in actors(state))
def free_places(state,excluding=None):
 reserved=sum(len(p.get('children',[])) or 1 for ident,p in state.get('pregnancies',{}).items() if ident!=excluding and p['status']=='pregnant')
 return int(state['user']['populationCap'])-population(state)-reserved

def pregnancy_reply(person,satisfied=None):
 return {'result':{'ErrorCode':0,'PregnancyInfo':{'pregnant':int(is_pregnant(person)),'pregnancyStartTime':person.get('pregnancyStartTime',0),'pregnancyTryCount':person.get('pregnancyTryCount',0)},'SatisfiedWantModels':copy.deepcopy(satisfied or [])}}
def inventory_reply(state):
 values=tasks.inventory(state)
 return {'result':{'Inventory':values,'inventory':values,'SatisfiedWantModels':[]},'inventory':values}

def newborn_plan(pregnancy,gender,index):
 choices=[v for v in world.rows('villager_starting_variation') if v.get('refId')==('baby female' if gender else 'baby male') and v.get('SpecialType','0')=='0']
 selector=int(hashlib.sha256((pregnancy['id']+':'+str(index)).encode()).hexdigest()[:8],16)
 seed=choices[selector%len(choices)]
 return {'rawId':uuid.uuid4().hex,'gender':gender,'seedId':seed['id']}

def choose_children(record,kind,places):
 # UI: natural1, twins2, boy7, girl8, triplets9. Costs are original globals.
 count=2 if kind==2 else 3 if kind==9 else 1
 if kind==1 and places>=2 and roll(100)<int(world.global_value('twinsChance')):count=2
 if places<count:raise ValueError('Not enough population capacity for this pregnancy')
 genders=[0 if kind==7 else 1 if kind==8 else roll(2) for _ in range(count)]
 return [newborn_plan(record,g,i) for i,g in enumerate(genders)]

def conceive(state,data,at):
 mother,father=couple(state,data.get('villagerId'),at)
 if is_pregnant(mother):return pregnancy_reply(mother,state.get('pregnancies',{}).get(mother['id'],{}).get('satisfiedWants',[])),False
 last=state.get('pregnancies',{}).get(mother['id'])
 if last and last['status']=='failed' and not last.get('retryUnlockedAt') and at-last['attemptedAt']<int(world.global_value('pregnancySkipRetryDuration')):return pregnancy_reply(mother),False
 if last and last['status']=='born' and at-last['bornAt']<int(world.global_value('childWantDelayAfterLastChild')):raise ValueError('Original post-birth interval has not elapsed')
 if free_places(state)<1:raise ValueError('Village population capacity reached')
 tries=int(mother.get('pregnancyTryCount',0))+1
 success=tries>=int(world.global_value('retriesBeforePregnancySuccess')) or roll(100)<int(world.global_value('pregnancyChancePercentage'))
 record={'id':uuid.uuid4().hex,'motherId':mother['id'],'fatherId':father['id'],'attemptedAt':at,'status':'pregnant' if success else 'failed','kind':1,'designFinalized':False,'children':[]}
 if success:
  record['children']=choose_children(record,1,free_places(state));record['readyAt']=int(struct.unpack('<f',struct.pack('<f',at))[0])+int(world.global_value('pregnancySkipDuration'))
 mother.update(pregnant='true' if success else 'false',pregnancyStartTime=at,pregnancyTryCount=tries,updatedAt=at)
 if success:
  ids={mother['id'],father['id']}
  removed=[w for w in state.get('wants',[]) if w['VillagerStringID'] in ids and w['MaterialID']==343 and w['wantableCategoryType']==5]
  record['satisfiedWants']=[{'WantId':w['WantId'],'VillagerStringID':w['VillagerStringID']} for w in removed]
  state['wants']=[w for w in state.get('wants',[]) if w not in removed]
 state.setdefault('pregnancies',{})[mother['id']]=record
 return pregnancy_reply(mother,record.get('satisfiedWants',[])),True

def timer_price(remaining,category):
 if remaining<=0:return 0
 def f(v):return struct.unpack('<f',struct.pack('<f',v))[0]
 xs=[f(float(world.global_value('gemCurveVariable'+category+'Time'+v))) for v in ['1min','1hour','1day','1week']]
 ys=[f(float(world.global_value('gemCalc'+category+'Value'+str(i)))) for i in range(1,5)]
 t=min(f(remaining),xs[-1]);index=0 if t<xs[1] else 1 if t<xs[2] else 2
 scale=f(f(xs[index+1]-xs[index])/f(ys[index+1]-ys[index]))
 return max(1,math.floor(f(ys[index]+f(f(t-xs[index])/scale))))

def retry_price(remaining):return timer_price(remaining,'PregnancySkipRetry')

def skip_reply(state,updated):return {'result':{'UpdatedTime':updated,'Gem':state['inventory'].get('323',0)}}

def skip_pregnancy(state,data,at,owner_id):
 mother=actor(state,data.get('motherVillagerId'));record=state.get('pregnancies',{}).get(mother['id'])
 if not record or data.get('fatherVillagerId')!=record['fatherId']:raise ValueError('Saved pregnancy and its father are required')
 if data.get('areaId')!=mother['position']['areaId']:raise ValueError('Pregnancy belongs to another area')
 if record['status']=='born':return birth_reply(state,record),False
 if record['status']!='pregnant' or not is_pregnant(mother):raise ValueError('Active pregnancy required')
 if free_places(state,mother['id'])<len(record['children']):raise ValueError('Village population capacity reached')
 if not str(owner_id).isdecimal() or len(str(owner_id))>18:raise ValueError('Valid owning player required')
 remaining=max(0,record['readyAt']-at);cost=0 if record.get('skipReceipt') else timer_price(remaining,'PregnancySkip')
 if state['inventory'].get('323',0)<cost:raise ValueError('Not enough gems to finish pregnancy')
 updated=at-int(world.global_value('pregnancySkipDuration'))
 state['inventory']['323']=state['inventory'].get('323',0)-cost
 record['readyAt']=min(at,record['readyAt'])
 record.setdefault('skipReceipt',{'at':at,'gemsSpent':cost,'updatedTime':updated})
 mother['pregnancyStartTime']=updated
 # Script2039 dispatches SkipPregnancy to BirthModelListener (result.villagers),
 # not the UpdatedTime/Gem listener used by advertisement time reductions.
 return birth(state,{'VillagerStringID':mother['id']},at,owner_id)

def unlock_retry(state,data,at):
 mother,_=couple(state,data.get('villagerId'),at)
 record=state.get('pregnancies',{}).get(mother['id'])
 if not record or record['status']!='failed' or is_pregnant(mother):raise ValueError('A saved failed conception attempt is required')
 if record.get('retryUnlockedAt'):return inventory_reply(state),False
 remaining=max(0,record['attemptedAt']+int(world.global_value('pregnancySkipRetryDuration'))-at)
 if not remaining:return inventory_reply(state),False
 if free_places(state)<1:raise ValueError('Village population capacity reached')
 cost=retry_price(remaining)
 if state['inventory'].get('323',0)<cost:raise ValueError('Not enough gems for the original retry price')
 state['inventory']['323']-=cost;record.update(retryUnlockedAt=at,retryGemCost=cost)
 # The original paid-retry listener reads Inventory, then returns to FillHeart.
 # CanConcievePregnancy makes the next attempt; this purchase never rerolls it.
 return inventory_reply(state),True

def design(state,data,at):
 mother=actor(state,data.get('villagerId'));record=state.get('pregnancies',{}).get(mother['id'])
 if not record or record['status']!='pregnant' or not is_pregnant(mother):raise ValueError('Active pregnancy required')
 value=data.get('pregnancyType')
 if isinstance(value,bool) or not isinstance(value,(str,int)) or str(value) not in {'1','2','7','8','9'}:raise ValueError('Unsupported pregnancy choice')
 kind=int(value)
 if record['designFinalized']:
  if record['kind']!=kind:raise ValueError('Pregnancy choice already finalized')
  return inventory_reply(state),False
 costs={1:0,2:int(world.global_value('gemsForTwins')),9:int(world.global_value('gemsForTriplet')),7:int(world.global_value('gemsForBoy')),8:int(world.global_value('gemsForGirl'))};cost=costs[kind]
 if state['inventory'].get('323',0)<cost:raise ValueError('Not enough in-game gems')
 if kind==1:
  if free_places(state,mother['id'])<len(record['children']):raise ValueError('Not enough population capacity')
  children=record['children']
 else:children=choose_children(record,kind,free_places(state,mother['id']))
 record.update(children=children,kind=kind,designFinalized=True,gemsSpent=cost)
 state['inventory']['323']=state['inventory'].get('323',0)-cost
 return inventory_reply(state),True

def add_relation(person,other,kind):
 if not any(r['villagerId']==other['id'] and int(r['type'])==kind for r in person['relations']):person['relations'].append({'villagerId':other['id'],'type':kind})

def birth_reply(state,record):
 result=[]
 for ident in record['bornChildren']:
  child=actor(state,ident)
  result.append({'ID':child['serverBirthId'],'Name':child['name'],'Equipment':child['equipment'],'villagerBaseId':child['villagerBaseId'],'StartAge':0,'BornAt':child['bornAt'],'createdAt':child['bornAt'],'Gender':child['gender'],'Rarity':child['rarity'],'Skills':[{'SkillTypeID':int(s.get('skilltypeId',s.get('skillTypeId'))),'SkillSourceType':int(s['skillOriginType'])} for s in child.get('skills',[])]})
 return {'result':{'villagers':result,'inventory':tasks.inventory(state)}}

def birth(state,data,at,owner_id):
 mother=actor(state,data.get('VillagerStringID'));record=state.get('pregnancies',{}).get(mother['id'])
 if not record:raise ValueError('No saved pregnancy for this mother')
 if record['status']=='born':return birth_reply(state,record),False
 if record['status']!='pregnant' or not is_pregnant(mother):raise ValueError('Active pregnancy required')
 if at<record['readyAt']:raise ValueError('Pregnancy is not ready')
 if not str(owner_id).isdecimal() or len(str(owner_id))>18:raise ValueError('Valid owning player required')
 father=actor(state,record['fatherId'])
 if free_places(state,mother['id'])<len(record['children']):raise ValueError('Village population capacity reached')
 existing=actors(state);born=[]
 for i,plan in enumerate(record['children']):
  seed=world.by_id('villager_starting_variation',plan['seedId']);ident='Villager_'+str(owner_id)+'_'+plan['rawId']
  if any(a['id']==ident for a in existing):raise ValueError('Duplicate newborn identity')
  child={'templateType':'villager_type','serverPersisted':True,'startingArea':mother['position']['areaId']}
  child.update(id=ident,refId='',name=seed['name'],templateId=4 if plan['gender'] else 3,villagerBaseId=int(seed['id']),birthType=0,specialType=0,energyLevel=0,energyTimeStamp=at,startAge=0,bornAt=at,updatedAt=at,pregnant='false',pregnancyTryCount=0,pregnancyStartTime=0,gender=plan['gender'],xp=0,rarity=0,shelterBedId='',position={**mother['position'],'x':mother['position']['x']+40*(i+1),'y':mother['position']['y']+40},equipment=seed['equipment'],genetics=seed['genetics'],relations=[],skills=[],wants=[],clothing=[],isCommunityVillager='false',retireAt=0,retireEventID=0,serverBirthId=plan['rawId'],familyBirthId=record['id'])
  if plan.get('gachaBaseId'):
   import collection
   chosen=collection.definition(plan['gachaBaseId'])
   child.update(name=chosen['name'],villagerBaseId=int(chosen['id']),collectionBaseId=int(chosen['id']),equipment=chosen['equipment'],rarity=int(chosen['star']),skills=collection.seed_skills(chosen),genetics='')
   state.setdefault('villagerCollection',{})[chosen['id']]=max(2,state.get('villagerCollection',{}).get(chosen['id'],0))
  for key in ['originalSeedId','lastChildBornAt','ownerUserId','datingPartnerId']:child.pop(key,None)
  add_relation(child,mother,0);add_relation(child,father,0);add_relation(mother,child,1);add_relation(father,child,1)
  for sibling in existing+born:
   if any(r['villagerId'] in {mother['id'],father['id']} and int(r['type'])==0 for r in sibling.get('relations',[])):add_relation(child,sibling,3);add_relation(sibling,child,3)
  born.append(child)
 state['world']['entities']+=born
 mother.update(pregnant='false',pregnancyStartTime=0,pregnancyTryCount=0,lastChildBornAt=at,updatedAt=at)
 father['lastChildBornAt']=at
 record.update(status='born',bornAt=at,bornChildren=[c['id'] for c in born])
 return birth_reply(state,record),True

def set_name(state,data):
 person=actor(state,data.get('villagerId'));name=data.get('name')
 if not isinstance(name,str) or not name.strip() or len(name.encode('utf-8'))>64 or any(ord(c)<32 for c in name):raise ValueError('Invalid villager name')
 name=name.strip();changed=person['name']!=name;person['name']=name
 return {},changed

def operate(state,service,data,at,owner_id,receipt_key):
 if service in WISH_SERVICES:
  response,changed=generate_child_wishes(state,at)
  if changed:state['revision']+=1;state['updatedAt']=at
  return response,changed
 if not receipt_key:raise ValueError('Family action requires a request identifier')
 signature=json.dumps({'service':service,'data':data},sort_keys=True,separators=(',',':'))
 receipt=state.get('familyReceipts',{}).get(receipt_key)
 if receipt:
  if receipt['signature']!=signature:raise ValueError('Family request identifier reused')
  if service in {'ClientVillager/Birth','ClientVillagerService/SkipPregnancy'} and receipt.get('birthId'):
   record=next(r for r in state.get('birthHistory',[]) if r['id']==receipt['birthId'])
   return birth_reply(state,record),False
  if service=='ClientVillager/CanConcievePregnancy':return pregnancy_reply(actor(state,data.get('villagerId')),state.get('pregnancies',{}).get(data.get('villagerId'),{}).get('satisfiedWants',[])),False
  if service!='ClientVillagerService/SkipPregnancy':return ({} if service.endswith('/SetName') else inventory_reply(state)),False
 if service=='ClientVillager/CanConcievePregnancy':response,changed=conceive(state,data,at)
 elif service=='ClientVillager/SkipRetryConcievePregnancy':response,changed=unlock_retry(state,data,at)
 elif service=='ClientVillagerService/SkipPregnancy':response,changed=skip_pregnancy(state,data,at,owner_id)
 elif service=='ClientVillager/DesignPregnancy':response,changed=design(state,data,at)
 elif service=='ClientVillager/Birth':response,changed=birth(state,data,at,owner_id)
 elif service=='ClientVillagerService/SetName':response,changed=set_name(state,data)
 else:raise NotImplementedError('Unrecovered family action')
 receipt={'signature':signature}
 if service in {'ClientVillager/Birth','ClientVillagerService/SkipPregnancy'}:
  mother_id=data['VillagerStringID'] if service=='ClientVillager/Birth' else data['motherVillagerId']
  record=state['pregnancies'][mother_id];receipt['birthId']=record['id']
  if not any(r['id']==record['id'] for r in state.get('birthHistory',[])):state.setdefault('birthHistory',[]).append(copy.deepcopy(record))
 state.setdefault('familyReceipts',{})[receipt_key]=receipt
 state.setdefault('rules',{})['family']={'status':'reconstructed_server_policy_using_original_wire_and_tables','evidence':'native pregnancy info, design codes, BirthModelListener fields and player-prefixed IDs; pregnancySkipDuration86400 read by native PregnancyModelUpdate','policy':'original conception/twin chances and gem design prices; original minimum adult and maternal age bounds; same-shelter married parents; population reservations; authored baby appearance/skills templates; no recovered genetic-inheritance algorithm; no cross-owner transfers implemented'}
 state['revision']+=1;state['updatedAt']=at
 return response,True
