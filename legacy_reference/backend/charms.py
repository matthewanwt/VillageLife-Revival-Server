"""Original HUD charm packs and pools; reconstructed weighted server draws."""
import copy,math
from decimal import Decimal
import world,fortune,collection,family,native_identity
SERVICES={'ClientFortune/Gacha','ClientFortune/ConsumeGacha'}

def sku(value,conception=False):
 if isinstance(value,bool) or not str(value).isdigit():raise ValueError('Original charm pack identifier required')
 try:item=world.by_id('runeSetItem',value);group=world.by_id('runeSet',item['runeSet'])
 except StopIteration:raise ValueError('Unknown original charm pack') from None
 if conception:
  if item['isHUD']!='0' or int(group['conceptionOrder'])<0:raise ValueError('Conception requires an original baby charm')
 elif item['isHUD']!='1' or int(group['HudOrder'])<0:raise ValueError('Baby charm requires a pregnant mother')
 if not 1<=int(item['runeAmount'])<=3:raise ValueError('Invalid original charm quantity')
 return item,group

def price(item,group,at):
 value=Decimal(item['gemCost'])
 if int(group['SaleStartEpoch'])<=at<int(group['SaleEndEpoch']):value*=1-Decimal(group['discount'])
 return math.floor(value)

def pick_reward(pool_set):
 row=fortune.choose([r for r in world.rows('runeRewardPoolProb') if r['runeRewardSet']==str(pool_set)],'probability')
 if row['poolType']=='1':
  reward=fortune.choose([r for r in world.rows('gachaRewardSet') if r['pool']==row['pool']],'probability')
  items=[r for r in world.rows('gachaRewardSetItem') if r['setId']==reward['id']]
  if not items:raise ValueError('Original charm material pool is empty')
  return [{'Material':{'MaterialId':int(r['materialType']),'Quantity':float(r['quantity'])}} for r in items]
 seed=fortune.choose([r for r in world.rows('gachaVillager') if r['pool']==row['pool'] and (row['poolType']!='2' or r['partnerID']!='0')],'probability')
 seeds=[seed]
 if row['poolType']=='2':seeds.append(collection.definition(seed['partnerID']))
 elif row['poolType']!='0':raise ValueError('Unknown original charm pool type')
 return [{'Villagers':[{'villagerBaseId':int(s['id'])} for s in seeds]}]

def draw(item,group):
 results=[]
 for _ in range(int(item['runeAmount'])):
  rewards=pick_reward(group['mainRuneRewardSetId'])
  choices=[{'n':n,'weight':group[field]} for n,field in enumerate(['noBonusProb','X1BonusProb','X2BonusProb','X3BonusProb'])]
  for _ in range(fortune.choose(choices,'weight')['n']):rewards+=pick_reward(group['bonusRuneRewardSet'])
  results.append(rewards)
 return results

def baby(state,service,data,at,owner,key,item,group,signature):
 mother=family.actor(state,data['VillagerStringId']);record=state.get('pregnancies',{}).get(mother['id'])
 if not record or record['status']!='pregnant' or not family.is_pregnant(mother):raise ValueError('Active saved pregnancy required for a baby charm')
 old=record.get('charmChoice')
 if old:
  if old['sku']!=item['id']:raise ValueError('This pregnancy already has a saved baby charm choice')
  return copy.deepcopy(old['response']),False
 if record.get('designFinalized') and record.get('kind',1)!=1:raise ValueError('Pregnancy already has a paid design choice')
 candidate=copy.deepcopy(state);record=candidate['pregnancies'][mother['id']]
 cost=price(item,group,at)
 # Free conception packs use the same native consume wrapper but have no
 # inventory token. Paid packs retain their original SKU price/discount.
 if service.endswith('/ConsumeGacha') and cost:raise ValueError('This baby charm requires its gem purchase')
 if candidate['inventory'].get('323',0)<cost:raise ValueError('Not enough gems for this baby charm')
 results=draw(item,group)
 rows=[r for rewards in results for r in rewards if 'Villagers' in r]
 count=sum(len(r['Villagers']) for r in rows)
 if not count:raise ValueError('Original baby charm pool has no child')
 if family.free_places(candidate,mother['id'])<count:raise ValueError('Not enough population capacity for these babies')
 plans=[]
 for row in rows:
  for value in row['Villagers']:
   seed=collection.definition(value['villagerBaseId']);plan=family.newborn_plan(record,int(seed['genderType']),len(plans));plan['gachaBaseId']=seed['id']
   canonical='Villager_'+str(owner)+'_'+plan['rawId']
   native_identity.reserve_ids(candidate,owner,[canonical])
   value.update(VillagerId=int(candidate['nativeIdentityIds'][str(owner)][canonical]),BornAt=at)
   plans.append(plan)
 for rewards in results:
  for reward in rewards:
   if 'Material' in reward:
    material=reward['Material'];ident=str(material['MaterialId']);candidate['inventory'][ident]=candidate['inventory'].get(ident,0)+material['Quantity']
 candidate['inventory']['323']=candidate['inventory'].get('323',0)-cost
 response={'result':results}
 record.update(children=plans,designFinalized=True,charmChoice={'sku':item['id'],'gemsSpent':cost,'response':copy.deepcopy(response),'at':at})
 candidate.setdefault('charmReceipts',{})[key]={'signature':signature,'response':copy.deepcopy(response),'at':at,'pregnancyId':record['id'],'payment':{'material':'323','amount':cost}}
 candidate.setdefault('rules',{})['baby_charms']={'evidence':'Script2313/2305 targeted Gacha/ConsumeGacha; Script2074 nested result; original conception SKUs/pools; RuneOpen creates world actors only for HUD context','policy':'saved prenatal draw, original cost and bonus weights; reserves final child identities and population; births use selected appearances/skills; free draw once per pregnancy; replay cannot reroll or charge twice'}
 candidate['revision']+=1;world.validate_world(candidate);state.clear();state.update(candidate)
 return response,True

def operate(state,service,data,at,owner,key):
 if not key:raise ValueError('Charm receipt required')
 target=data.get('VillagerStringId','');item,group=sku(data.get('CharmSetID'),bool(target));signature=[service,item['id'],str(target)]
 old=state.get('charmReceipts',{}).get(key)
 if old:
  if old['signature']!=signature:raise ValueError('Charm receipt reused for a different pack')
  return copy.deepcopy(old['response']),False
 if target:return baby(state,service,data,at,owner,key,item,group,signature)
 candidate=copy.deepcopy(state);count=int(item['runeAmount']);cost=price(item,group,at)
 if service.endswith('/ConsumeGacha'):
  material=group['materialType']
  if material=='0' or candidate['inventory'].get(material,0)<count:raise ValueError('Not enough owned charms')
  candidate['inventory'][material]-=count;payment={'material':material,'amount':count}
 else:
  if cost<=0:raise ValueError('Free pack requires an earned charm; use the consume path')
  if candidate['inventory'].get('323',0)<cost:raise ValueError('Not enough gems for this charm pack')
  candidate['inventory']['323']-=cost;payment={'material':'323','amount':cost}
 results=draw(item,group)
 population=sum(len(r.get('Villagers',[])) for group_result in results for r in group_result)
 if family.free_places(candidate)<population:raise ValueError('Village population capacity reached')
 for group_result in results:
  for reward in group_result:
   if 'Material' in reward:
    m=reward['Material'];k=str(m['MaterialId']);candidate['inventory'][k]=candidate['inventory'].get(k,0)+m['Quantity'];continue
   spawned=[]
   for row in reward['Villagers']:
    seed=collection.definition(row['villagerBaseId']);person=collection.spawn(candidate,seed,at);spawned.append(person)
    native_identity.reserve_ids(candidate,owner);raw=candidate['nativeIdentityIds'][str(owner)][person['id']]
    row.update(VillagerId=int(raw),BornAt=person['bornAt'])
    candidate.setdefault('villagerCollection',{})[seed['id']]=max(2,candidate.get('villagerCollection',{}).get(seed['id'],0))
   if len(spawned)==2:
    family.add_relation(spawned[0],spawned[1],2);family.add_relation(spawned[1],spawned[0],2)
 response={'result':results}
 candidate.setdefault('charmReceipts',{})[key]={'signature':signature,'payment':payment,'response':copy.deepcopy(response),'at':at}
 candidate.setdefault('rules',{})['hud_charms']={'status':'original_pools_reconstructed_server_policy','evidence':'Script2313/2305 SKU requests; Script2074 nested response parser; runeSet, runeSetItem, runeRewardPoolProb, gachaVillager and gachaRewardSetItem','policy':'normalize original positive weights at each pool; original bonus-count weights; pool type2 uses original partner pair as spouses; original gem price and dated discount; earned tokens consumed once; saved draws cannot reroll on receipt retry; baby/conception packs remain separate; skill proficiency/genetics use collection spawn policy'}
 candidate['revision']+=1;world.validate_world(candidate);state.clear();state.update(candidate)
 return response,True
