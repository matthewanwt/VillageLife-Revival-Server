import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import family,habitats,native_identity,session,world
import test_family as family_tests

class ChildWishTests(unittest.TestCase):
 setUp=family_tests.FamilyTests.setUp
 def generate(self,at=1060):return family.operate(self.state,'ClientWant/GenerateBirthWants',{},at,'42',None)
 def test_original_child_material_category_and_duplicate_free_generation(self):
  result,changed=self.generate();self.assertTrue(changed)
  wishes=[w for w in result['result'] if w['MaterialID']==343];self.assertEqual(len(wishes),1);self.assertEqual(wishes[0]['VillagerStringID'],'jill');self.assertEqual(wishes[0]['wantableCategoryType'],5)
  before=copy.deepcopy(self.state);self.assertFalse(self.generate(1061)[1]);self.assertEqual(before,self.state)
  self.assertFalse(family.operate(self.state,'ClientWant/GenerateChildWants',{},1062,'42',None)[1])
 def test_original_post_marriage_delay_and_unsupported_couples(self):
  self.assertFalse(any(w['MaterialID']==343 for w in self.generate(1059)[0]['result']))
  original=copy.deepcopy(self.state)
  for kind in ['young','old','unmarried','separate-beds','full','pregnant']:
   with self.subTest(kind=kind):
    self.state=copy.deepcopy(original);mother=family.actor(self.state,'jill')
    if kind=='young':mother['startAge']=17
    elif kind=='old':mother['startAge']=51
    elif kind=='unmarried':mother['relations']=[]
    elif kind=='separate-beds':mother['shelterBedId']=''
    elif kind=='full':self.state['user']['populationCap']=family.population(self.state)
    elif kind=='pregnant':mother['pregnant']='true'
    self.assertFalse(any(w['MaterialID']==343 for w in self.generate()[0]['result']))
 def test_stale_child_wish_removed_if_no_longer_eligible(self):
  self.generate();mother=family.actor(self.state,'jill');mother['pregnant']='true'
  result,changed=self.generate(1061);self.assertTrue(changed);self.assertFalse(any(w['MaterialID']==343 for w in result['result']))
 def test_birth_and_generation_cooldowns_use_saved_clocks(self):
  mother=family.actor(self.state,'jill');mother['lastChildBornAt']=1050
  self.assertFalse(any(w['MaterialID']==343 for w in self.generate()[0]['result']))
  mother['lastChildBornAt']=0;self.generate();self.state['wants']=[]
  self.assertFalse(any(w['MaterialID']==343 for w in self.generate(1061)[0]['result']))
  # Advance only the generation clock: real ageing is independent of this test.
  self.state['childWantGeneratedAt']['jill']=1061-int(world.global_value('waitDurationAfterLastChildWantGen'))
  self.assertTrue(any(w['MaterialID']==343 for w in self.generate(1061)[0]['result']))
 def test_riverside_authored_limits_do_not_change_woodland_behavior(self):
  self.state['areaId']=2;self.state['user']['populationCap']=50
  family.actor(self.state,'baby male').update(startAge=2,bornAt=1000)
  self.assertFalse(any(w['MaterialID']==343 for w in self.generate()[0]['result']))
  self.state['areaId']=1;self.assertTrue(any(w['MaterialID']==343 for w in self.generate()[0]['result']))
 def test_success_satisfies_saved_wish_and_retries_do_not_reroll(self):
  self.generate();wish=next(w for w in self.state['wants'] if w['MaterialID']==343)
  with patch.object(family,'roll',side_effect=[0,99,0]):
   response,changed=family.operate(self.state,'ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},1061,'42','wish:1')
  self.assertTrue(changed);expected=[{'WantId':wish['WantId'],'VillagerStringID':'jill'}]
  self.assertEqual(response['result']['SatisfiedWantModels'],expected);self.assertFalse(any(w['MaterialID']==343 for w in self.state['wants']))
  saved=json.loads(json.dumps(self.state));before=copy.deepcopy(saved)
  with patch.object(family,'roll',side_effect=AssertionError('rerolled')):
   again,changed=family.operate(saved,'ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},1062,'42','wish:1')
  self.assertFalse(changed);self.assertEqual(again['result']['SatisfiedWantModels'],expected);self.assertEqual(before,saved);world.validate_world(saved)
 def test_failed_attempt_preserves_wish_and_original_retry_cooldown(self):
  self.generate()
  with patch.object(family,'roll',return_value=99):family.operate(self.state,'ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},1061,'42','failed:1')
  self.assertTrue(any(w['MaterialID']==343 for w in self.state['wants']));before=copy.deepcopy(self.state)
  with patch.object(family,'roll',side_effect=AssertionError('rerolled early')):
   response,changed=family.conceive(self.state,{'villagerId':'jill'},1062)
  self.assertFalse(changed);self.assertEqual(response['result']['PregnancyInfo']['pregnant'],0);self.assertEqual(before,self.state)
 def failed_attempt(self):
  self.generate()
  with patch.object(family,'roll',return_value=99):family.operate(self.state,'ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},1061,'42','failed:1')
 def test_paid_retry_uses_original_pregnancy_curve_and_never_rerolls_at_purchase(self):
  self.assertEqual([family.retry_price(t) for t in [0,60,3600,28800,86400,604800]],[0,1,3,12,33,125])
  self.failed_attempt();balance=self.state['inventory']['323']
  with patch.object(family,'roll',side_effect=AssertionError('purchase rerolled conception')):
   response,_=family.operate(self.state,'ClientVillager/SkipRetryConcievePregnancy',{'villagerId':'jill'},1062,'42','pay:1')
  self.assertIn('Inventory',response['result']);self.assertEqual(self.state['inventory']['323'],balance-12)
  self.assertEqual(self.state['pregnancies']['jill']['status'],'failed');self.assertFalse(family.is_pregnant(family.actor(self.state,'jill')))
  with patch.object(family,'roll',side_effect=[0,99,0]):response,_=family.operate(self.state,'ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},1063,'42','try:2')
  self.assertEqual(response['result']['PregnancyInfo']['pregnant'],1);self.assertEqual(response['result']['PregnancyInfo']['pregnancyTryCount'],2)
 def test_paid_retry_receipts_and_attempt_identity_prevent_double_charge(self):
  self.failed_attempt();data={'villagerId':'jill'};family.operate(self.state,'ClientVillager/SkipRetryConcievePregnancy',data,1062,'42','pay:1');balance=self.state['inventory']['323']
  self.state=json.loads(json.dumps(self.state))
  family.operate(self.state,'ClientVillager/SkipRetryConcievePregnancy',data,1063,'42','pay:1')
  family.operate(self.state,'ClientVillager/SkipRetryConcievePregnancy',data,1064,'42','pay:2')
  self.assertEqual(self.state['inventory']['323'],balance)
 def test_unaffordable_or_wrong_actor_retry_cannot_change_inventory(self):
  self.failed_attempt();self.state['inventory']['323']=0
  for data in [{'villagerId':'jill'},{'villagerId':'steve'},{'villagerId':'unowned'}]:
   before=copy.deepcopy(self.state)
   with self.assertRaises(ValueError):family.unlock_retry(self.state,data,1062)
   self.assertEqual(before,self.state)
 def test_elapsed_retry_wait_has_no_gem_charge(self):
  self.failed_attempt();before=copy.deepcopy(self.state)
  _,changed=family.unlock_retry(self.state,{'villagerId':'jill'},1061+28800)
  self.assertFalse(changed);self.assertEqual(before,self.state)
 def test_authenticated_native_generation_and_conception_save_the_same_wish(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(session,'STATE',Path(folder)):
   profile=session.login({'deviceId':'child-wish-native'})['data']['users'][0]
   path=session.profile_path('child-wish-native').with_suffix('.tutorial.json');session.atomic_json(path,{**session.fresh_tutorial(),'normal':self.state})
   def call(service,data,at,ident):
    with patch.object(session,'wire_time',return_value=at):return session.process({**profile,'data':{'calls':[{'id':ident,'service':service,'data':data}]}},native_ids=True)['data']['calls'][0]
   response=call('ClientWant/GenerateBirthWants',{},1060,'1');self.assertEqual(response['code'],200)
   wire=native_identity.mappings(self.state,profile['pId'])[0]['jill'];wish=next(w for w in response['data']['result'] if w['MaterialID']==343);self.assertEqual(wish['VillagerStringID'],wire)
   with patch.object(family,'roll',side_effect=[0,99,0]):response=call('ClientVillager/CanConcievePregnancy',{'villagerId':wire},1061,'2')
   self.assertEqual(response['code'],200);self.assertEqual(response['data']['result']['SatisfiedWantModels'][0]['VillagerStringID'],wire)
   normal=json.loads(path.read_text(encoding='utf-8'))['normal'];self.assertTrue(family.is_pregnant(family.actor(normal,'jill')));self.assertFalse(any(w['MaterialID']==343 for w in normal['wants']))
if __name__=='__main__':unittest.main()
