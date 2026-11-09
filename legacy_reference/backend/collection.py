"""Collection-book purchases using original character definitions and gem prices."""
import copy,json,uuid
import world,tasks,family
SERVICES={'ClientVillagerService/CreateGachaVillager','ClientVillagerService/CollectVillager'}

def definition(ident):
 if isinstance(ident,bool) or not str(ident).isdecimal():raise ValueError('Original villager definition required')
 try:return world.by_id('gachaVillager',ident)
 except StopIteration:raise ValueError('Unknown original villager') from None

def shop_price(seed):
 star=int(seed['star'])
 if star not in {3,4,5,6}:raise ValueError('This villager is not offered by the original collection shop')
 group=next((r for r in world.rows('Collection_Set_Item') if seed['id'] in r['GachaVillagerArray'].split(',')),None)
 limited=group and world.by_id('Collection_Set',group['CollectionSet'])['IsLimitedEdition']=='1'
 return int(world.global_value(str(star)+'Star'+('LimitedEd' if limited else '')+'VillagerGemCost'))

def seed_skills(seed):
 # RuneReviewSkills reads repeated skill IDs as skill levels. Do not truncate
 # six-value rows or deduplicate mastered skills. Each skill has three levels.
 skills=[int(v) for v in seed['skills'].split(',') if v.strip().isdigit()]
 valid={int(r['id']) for r in world.rows('villager_skill') if r['id']!='0'};counts={};result=[]
 for ident in skills:
  if ident not in valid or counts.get(ident,0)>=3:continue
  counts[ident]=counts.get(ident,0)+1;result.append({'skilltypeId':ident,'skillOriginType':0})
 return result

def migrate_skills(state):
 changed=False
 for person in family.actors(state):
  ident=person.get('collectionBaseId')
  if not ident:continue
  seed=definition(ident);expected=seed_skills(seed);counts={}
  for row in person.get('skills',[]):
   kind=int(row.get('skilltypeId',row.get('skillTypeId')));counts[kind]=counts.get(kind,0)+1
  needed={}
  for row in expected:
   kind=row['skilltypeId'];needed[kind]=needed.get(kind,0)+1
   if counts.get(kind,0)<needed[kind]:person.setdefault('skills',[]).append(dict(row));counts[kind]=counts.get(kind,0)+1;changed=True
 if changed:state['revision']+=1
 return changed

def spawn(state,seed,at):
 ages=[int(v) for v in seed['ageRange'].split(',')];index=next((i for i,a in enumerate(ages) if a>=18),0);age=ages[index]
 typ=world.by_id('villager_type',seed['villagerType'].split(',')[index])
 born_at=at-int(age*float(world.global_value('hours_per_year'))*3600)
 origin=next(iter(family.actors(state)),None)
 point=copy.deepcopy(origin['position'] if origin else {'x':1600,'y':3500,'areaId':state['areaId'],'rotation':0})
 point['x']+=40
 seed_id='local-gacha-'+uuid.uuid4().hex
 # Preserve the authored skill levels in the native repeated-record schema.
 skills=seed_skills(seed)
 actor={'id':seed_id,'refId':'','name':seed['name'],'templateType':'villager_type','templateId':int(typ['id']),'serverPersisted':True,'villagerBaseId':int(seed['id']),'startingArea':state['areaId'],'birthType':0,'specialType':0,'energyLevel':int(typ['maxEnergy']),'energyTimeStamp':at,'startAge':0,'bornAt':born_at,'updatedAt':at,'pregnant':'false','pregnancyTryCount':0,'pregnancyStartTime':0,'gender':int(seed['genderType']),'xp':0,'rarity':int(seed['star']),'shelterBedId':'','position':point,'equipment':seed['equipment'],'genetics':'','relations':[],'skills':skills,'wants':[],'clothing':[],'isCommunityVillager':'false','retireAt':0,'retireEventID':0,'collectionBaseId':int(seed['id'])}
 state['world']['entities'].append(actor)
 return actor

def read(state):
 collection=dict(state.get('villagerCollection',{}))
 return {'VillagerCollection':json.dumps(collection,separators=(',',':')),'villagers':[int(k) for k in collection]}

def operate(state,service,data,at,owner,key):
 if service.endswith('CollectVillager'):
  seed=definition(data.get('VillagerBaseId'));ident=seed['id'];status=state.get('villagerCollection',{}).get(ident)
  if status is None:raise ValueError('Villager has not been acquired for this collection')
  if status==3:return {},False
  state['villagerCollection'][ident]=3;state['revision']+=1;return {},True
 if not key:raise ValueError('Villager purchase receipt required')
 seed=definition(data.get('GachaVillagerId'));cost=shop_price(seed)
 if isinstance(data.get('GemCost'),bool) or data.get('GemCost')!=cost:raise ValueError('Villager price differs from the original shop price')
 old=state.get('villagerPurchaseReceipts',{}).get(key)
 if old:
  if old['baseId']!=seed['id']:raise ValueError('Villager purchase receipt reused')
  return {'inventory':tasks.inventory(state),'villager':[copy.deepcopy(old['villager'])]},False
 if family.free_places(state)<1:raise ValueError('Village population capacity reached')
 if state['inventory'].get('323',0)<cost:raise ValueError('Not enough gems to purchase this villager')
 actor=spawn(state,seed,at)
 import native_identity
 native_identity.reserve_ids(state,owner);raw=state['nativeIdentityIds'][str(owner)][actor['id']]
 state['inventory']['323']-=cost
 villager={'id':int(raw),'bornAt':actor['bornAt'],'villagerBaseID':int(seed['id'])}
 state.setdefault('villagerCollection',{})[seed['id']]=max(2,state.get('villagerCollection',{}).get(seed['id'],0))
 state.setdefault('villagerPurchaseReceipts',{})[key]={'baseId':seed['id'],'actorId':actor['id'],'gemsSpent':cost,'villager':villager}
 state.setdefault('rules',{})['collection_shop']={'status':'authored_definitions_reconstructed_spawn_policy','evidence':'Script2307 and Script0228; Script3036 normal/limited star price globals; original gachaVillager and Collection_Set tables','policy':'spawn first original adult age/type when available, otherwise first original age; backdate bornAt from zero starting age to match native CreateGachaVillager; original equipment/name and skill types; skill proficiency effects and original genetics not recovered; collection acknowledgment awards no invented bonus'}
 state['revision']+=1
 return {'inventory':tasks.inventory(state),'villager':[villager]},True
