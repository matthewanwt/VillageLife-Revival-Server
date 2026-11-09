"""Community reports: prenatal charms, paid birth skip, tree roles and bed repair."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import charms,family,habitats,native_identity,session,world

class CommunityFamilyFixes(unittest.TestCase):
 def setUp(self):
  self.at=2000000000;self.state=world.build_bridge_world(session.fresh_tutorial(),self.at)
  self.state['user'].update(populationCap=100,userLevel=50,userLevelID=50,xp=372826)
  self.state['inventory']['323']=100000
  home={'id':'family-home','templateType':'shelter','templateId':1,'position':{'x':4000,'y':4000,'rotation':0,'areaId':1}}
  habitats.initialize(home,self.at);self.state['world']['entities'].append(home)
  for person,bed in zip(['steve','jill'],home['beds']):
   family.actor(self.state,person).update(startAge=25,bornAt=self.at)
   habitats.assign(self.state,{'villagerId':person,'shelterBedId':bed['id']},self.at)
  with patch.object(family,'roll',side_effect=[0,99,0]):family.operate(self.state,'ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},self.at,'42','conceive')
 def baby(self,sku,service='Gacha',key='charm'):
  return charms.operate(self.state,'ClientFortune/'+service,{'CharmSetID':str(sku),'VillagerStringId':'jill'},self.at+1,'42',key)
 def test_free_premium_deluxe_all_quantities_save_draw_without_early_birth(self):
  for sku,cost,count in [(1,0,1),(4,30,1),(5,60,2),(6,90,3),(7,45,1),(8,90,2),(9,135,3)]:
   with self.subTest(sku=sku):
    self.setUp();before=len(family.actors(self.state));gems=self.state['inventory']['323']
    response,changed=self.baby(sku,'ConsumeGacha' if sku==1 else 'Gacha');self.assertTrue(changed)
    record=self.state['pregnancies']['jill'];self.assertEqual(len(record['children']),count)
    self.assertEqual(record['charmChoice']['gemsSpent'],cost)
    # Bonus materials can include gems; charge evidence is the saved receipt.
    self.assertEqual(self.state['charmReceipts']['charm']['payment']['amount'],cost)
    self.assertEqual(len(family.actors(self.state)),before);self.assertTrue(family.is_pregnant(family.actor(self.state,'jill')))
    self.state=json.loads(json.dumps(self.state));snapshot=copy.deepcopy(self.state)
    with patch.object(charms,'draw',side_effect=AssertionError('reroll')):
     self.assertEqual(self.baby(sku,'ConsumeGacha' if sku==1 else 'Gacha'),(response,False))
     self.assertEqual(self.baby(sku,'ConsumeGacha' if sku==1 else 'Gacha','different-call'),(response,False))
    self.assertEqual(snapshot,self.state)
    plans=copy.deepcopy(record['children']);preview=[v for result in response['result'] for reward in result for v in reward.get('Villagers',[])]
    born,_=family.operate(self.state,'ClientVillager/Birth',{'VillagerStringID':'jill'},record['readyAt'],'42','birth')
    self.assertEqual(len(born['result']['villagers']),count)
    for plan,wire in zip(plans,preview):
     child=family.actor(self.state,'Villager_42_'+plan['rawId']);seed=world.by_id('gachaVillager',plan['gachaBaseId'])
     self.assertEqual(child['equipment'],seed['equipment']);self.assertEqual(child['name'],seed['name']);self.assertEqual(child['rarity'],int(seed['star']))
     self.assertEqual(child['startAge'],0);self.assertEqual(child['bornAt'],record['readyAt']);self.assertTrue(child['skills'])
     native_identity.reserve_ids(self.state,'42');self.assertEqual(int(self.state['nativeIdentityIds']['42'][child['id']]),wire['VillagerId'])
    world.validate_world(self.state)
 def test_baby_charm_shortage_capacity_conflict_and_wrong_actor_never_spend(self):
  for failure in ['gems','population','mother']:
   with self.subTest(failure=failure):
    self.setUp()
    if failure=='gems':self.state['inventory']['323']=0
    elif failure=='population':self.state['user']['populationCap']=family.population(self.state)+1
    else:self.state['pregnancies']={}
    snapshot=copy.deepcopy(self.state)
    with self.assertRaises(ValueError):self.baby(9)
    self.assertEqual(snapshot,self.state)
  self.setUp();self.baby(1,'ConsumeGacha');snapshot=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):self.baby(4,key='other')
  self.assertEqual(snapshot,self.state)
 def test_pregnancy_skip_original_curve_reply_birth_and_no_double_charge(self):
  record=self.state['pregnancies']['jill'];remaining=record['readyAt']-(self.at+1);cost=family.timer_price(remaining,'PregnancySkip');gems=self.state['inventory']['323']
  data={'motherVillagerId':'jill','fatherVillagerId':'steve','areaId':1}
  response,_=family.operate(self.state,'ClientVillagerService/SkipPregnancy',data,self.at+1,'42','skip')
  self.assertEqual(self.state['inventory']['323'],gems-cost);self.assertTrue(response['result']['villagers']);self.assertEqual(record['status'],'born')
  self.state=json.loads(json.dumps(self.state));snapshot=copy.deepcopy(self.state)
  family.operate(self.state,'ClientVillagerService/SkipPregnancy',data,self.at+2,'42','skip')
  family.operate(self.state,'ClientVillagerService/SkipPregnancy',data,self.at+2,'42','new-skip')
  self.assertEqual(self.state['inventory']['323'],snapshot['inventory']['323'])
  family.operate(self.state,'ClientVillager/Birth',{'VillagerStringID':'jill'},self.at+2,'42','birth')
  family.operate(self.state,'ClientVillagerService/SkipPregnancy',data,self.at+3,'42','skip')
  self.assertEqual(self.state['inventory']['323'],gems-cost)
 def test_tree_contract_finds_parents_and_children_using_native_subject_roles(self):
  history=family.history(self.state,{'userId':'42'},self.at,'42');edges=history['villagerRelations']
  # Original ProcessFamilyTree selects outgoing child-role rows2/3 as parents,
  # and incoming child-role rows2/3 as children; never use our role mapper here.
  parents={r['relativeVillagerId'] for r in edges if r['villagerId']=='baby male' and r['relationTypeId'] in [2,3]}
  children={r['villagerId'] for r in edges if r['relativeVillagerId']=='jill' and r['relationTypeId'] in [2,3]}
  self.assertEqual(parents,{'steve','jill'});self.assertIn('baby male',children);self.assertIn('baby female',children)
 def test_bed_migration_preserves_occupants_ids_and_timer_for_all_eight_shelters(self):
  for typ,capacity in habitats.SHELTER_CAPACITIES.items():
   with self.subTest(shelter=typ):
    self.setUp();home=next(e for e in self.state['world']['entities'] if e['id']=='family-home');home['templateId']=typ;home['beds']=home['beds'][:2];before=copy.deepcopy(home)
    habitats.migrate(self.state,self.at+1);self.assertEqual(len(home['beds']),capacity);self.assertEqual(home['beds'][:2],before['beds']);self.assertEqual(home['happinessCollectedAt'],before['happinessCollectedAt'])
    snapshot=copy.deepcopy(self.state);self.assertFalse(habitats.migrate(self.state,self.at+2));self.assertEqual(snapshot,self.state);world.validate_world(self.state)
 def test_age_one_year_per_real_day_offline_and_restart(self):
  person=family.actor(self.state,'baby male');person.update(startAge=0,bornAt=self.at)
  self.state=json.loads(json.dumps(self.state));person=family.actor(self.state,'baby male')
  self.assertEqual(world.current_age(person,self.at+86400),1);self.assertEqual(world.current_age(person,self.at+5*86400),5)
 def test_authenticated_native_skip_translates_both_parent_ids(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(session,'STATE',Path(tmp)),patch.object(session,'wire_time',return_value=self.at+1):
   profile=session.login({'deviceId':'family-fix-test'})['data']['users'][0];path=session.profile_path('family-fix-test').with_suffix('.tutorial.json');saved={**session.fresh_tutorial(),'version':3,'normal':self.state,'gameSettings':{'activeSequenceId':'-1','isFtueComplete':'1'}};session.atomic_json(path,saved)
   native_identity.reserve_ids(self.state,profile['pId']);out,_,_,_=native_identity.mappings(self.state,profile['pId'])
   req={**profile,'data':{'calls':[{'id':'skip','service':'ClientVillagerService/SkipPregnancy','data':{'motherVillagerId':out['jill'],'fatherVillagerId':out['steve'],'areaId':1}}]}}
   result=native_identity.process(req)['data']['calls'][0];self.assertEqual(result['code'],200,result)

if __name__=='__main__':unittest.main()
