import unittest,copy
import world,session,tasks,fun,needs,buildings
class FunAndFinishTests(unittest.TestCase):
 def setUp(self):
  self.state=world.build_bridge_world(session.fresh_tutorial(),1000);self.state['inventory']['323']=40
  self.mat={'id':'test-mat','templateType':'fun_building','templateId':0,'position':{'x':1950,'y':3050,'areaId':1,'rotation':0},'serverPersisted':True,'localCreated':True}
  self.state['world']['entities'].append(self.mat);fun.initialize(self.mat)
 def test_missing_counter_is_initialized_once_and_broken_is_not_refilled(self):
  self.assertEqual(self.mat['amount'],50);self.mat['amount']=0;self.assertFalse(fun.migrate(self.state));self.assertEqual(self.mat['amount'],0)
 def test_original_sets_children_dance_babies_use_creche(self):
  dance=world.by_id('fun_activity',0);sleep=world.by_id('fun_activity',21)
  for ident in ['steve','sister']:self.assertTrue(fun.eligible(fun.actor(self.state,ident),dance,1000))
  for ident in ['baby male','baby female']:
   person=fun.actor(self.state,ident);self.assertFalse(fun.eligible(person,dance,1000));self.assertTrue(fun.eligible(person,sleep,1000))
 def test_owned_usable_fun_building_does_not_block_idle_fun_with_a_wish(self):
  self.state['wants']=[{'WantId':99,'VillagerStringID':'baby male','MaterialID':132,'wantableCategoryType':3}]
  result,_=needs.generate(self.state,'ClientWant/GenerateFunWants',1000)
  self.assertFalse(any(v['VillagerStringID']=='baby male' for v in result['result']))
  self.state['wants']=[{'WantId':100,'VillagerStringID':'baby male','MaterialID':442,'wantableCategoryType':3}]
  creche={**self.mat,'id':'test-creche','templateId':9};creche.pop('amount');fun.initialize(creche);self.state['world']['entities'].append(creche)
  result,_=needs.generate(self.state,'ClientWant/GenerateFunWants',1001)
  self.assertFalse(any(v['VillagerStringID']=='baby male' for v in result['result']))
  self.assertEqual(creche['amount'],50)
  before=copy.deepcopy(self.state);self.assertFalse(needs.generate(self.state,'ClientWant/GenerateFunWants',1002)[1]);self.assertEqual(before,self.state)
 def test_activity_saves_happiness_wear_and_satisfied_want_once(self):
  self.state['wants']=[{'WantId':100,'VillagerStringID':'steve','MaterialID':132,'wantableCategoryType':3}];data={'villagerId':'steve','funActivityId':0,'userFunBuildingTypeId':'test-mat'}
  response,changed=fun.perform(self.state,data,1030,'epoch:1');self.assertTrue(changed);self.assertEqual(self.mat['amount'],49);self.assertEqual(response['HappinessModel']['Xp'],12)
  self.assertTrue(response['SatisfiedWantModels']);before=copy.deepcopy(self.state)
  self.assertFalse(fun.perform(self.state,data,1031,'epoch:1')[1]);self.assertEqual(before,self.state)
  self.assertFalse(fun.perform(self.state,data,1032,'epoch:2')[1]);self.assertEqual(before,self.state)
  self.assertTrue(fun.perform(self.state,data,1060,'epoch:3')[1]);self.assertEqual(self.mat['amount'],48)
 def test_installed_fun_counter_is_persisted_at_login(self):
  import tempfile,json
  from pathlib import Path
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as directory,patch.object(session,'STATE',Path(directory)):
   identity=session.login({'deviceId':'fun-migration-test'})['data']['users'][0]
   saved={'normal':copy.deepcopy(self.state),'userHash':session.fresh_tutorial()['userHash']};next(v for v in saved['normal']['world']['entities'] if v['id']=='test-mat').pop('amount')
   path=session.profile_path('fun-migration-test').with_suffix('.tutorial.json');session.atomic_json(path,saved)
   session.login({'deviceId':'fun-migration-test'});loaded=json.loads(path.read_text());self.assertEqual(next(v for v in loaded['normal']['world']['entities'] if v['id']=='test-mat')['amount'],50)
 def test_consume_result_matches_dedicated_native_wish_listener(self):
  needs.generate(self.state,'ClientWant/GenerateWaterWants',1000);self.state['inventory']['6']=10
  want=next(v for v in self.state['wants'] if v['VillagerStringID']=='steve' and v['MaterialID']==6)
  data={'VillagerStringID':'steve','MaterialTypeID':6,'WantID':want['WantId']}
  response,_=needs.consume(self.state,data,1001)
  self.assertEqual(response['result']['VillagerStringID'],'steve');self.assertEqual(response['result']['WantID'],want['WantId']);self.assertEqual(response['result']['wantID'],want['WantId'])
  person=fun.actor(self.state,'steve');person['xp']=7
  replay,_=needs.consume(self.state,data,1002);self.assertEqual(replay['result']['Xp'],7)
 def test_old_receipt_is_upgraded_without_spending_again(self):
  needs.generate(self.state,'ClientWant/GenerateWaterWants',1000);self.state['inventory']['6']=10
  want=next(v for v in self.state['wants'] if v['VillagerStringID']=='steve' and v['MaterialID']==6)
  data={'VillagerStringID':'steve','MaterialTypeID':6,'WantID':want['WantId']};needs.consume(self.state,data,1001)
  receipt=self.state['consumptionReceipts'][str(want['WantId'])]
  for key in ['VillagerStringID','Xp','WantID','wantID']:receipt['response']['result'].pop(key,None)
  before=self.state['inventory']['6'];reply,changed=needs.consume(self.state,data,1002)
  self.assertFalse(changed);self.assertEqual(self.state['inventory']['6'],before);self.assertEqual(reply['result']['wantID'],want['WantId'])
 def test_owned_fun_building_wish_is_cleared_regardless_of_happiness(self):
  person=fun.actor(self.state,'steve');person['xp']=12
  result,_=needs.generate(self.state,'ClientWant/GenerateFunWants',1000)
  self.assertFalse(any(v['VillagerStringID']=='steve' and v['wantableCategoryType']==3 for v in result['result']))
  person['xp']=0;needs.generate(self.state,'ClientWant/GenerateFunWants',1001)
  self.assertFalse(any(v['VillagerStringID']=='steve' and v['wantableCategoryType']==3 for v in self.state['wants']))
 def test_happiness_collection_returns_original_userxp_envelope_once(self):
  person=fun.actor(self.state,'steve');person['xp']=12;before=self.state['user']['xp']
  response,changed=needs.release_xp(self.state,{'VillagerStringID':'steve'})
  self.assertTrue(changed);self.assertEqual(response['result']['UserXp'],before+12)
  self.assertFalse(needs.release_xp(self.state,{'VillagerStringID':'steve'})[1]);self.assertEqual(self.state['user']['xp'],before+12)
 def test_baby_cannot_receive_dance_reward(self):
  before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):fun.perform(self.state,{'villagerId':'baby male','funActivityId':0,'userFunBuildingTypeId':'test-mat'},1030,'epoch:1')
  self.assertEqual(before,self.state)
 def test_portable_toy_uses_original_fractional_wear_without_building(self):
  self.state['inventory']['137']=1;data={'villagerId':'steve','funActivityId':3}
  result,changed=fun.perform(self.state,data,1030,'portable')
  self.assertTrue(changed);self.assertAlmostEqual(self.state['inventory']['137'],79/80)
  self.assertEqual(result['userFunBuildingType'],{});self.assertEqual(result['HappinessModel']['Xp'],12)
  before=copy.deepcopy(self.state);self.assertFalse(fun.perform(self.state,data,1031,'portable')[1]);self.assertEqual(before,self.state)
  self.assertFalse(fun.perform(self.state,data,1032,'other')[1]);self.assertEqual(before,self.state)
 def test_portable_path_cannot_bypass_building_or_ownership(self):
  for data in [{'villagerId':'steve','funActivityId':0},{'villagerId':'steve','funActivityId':3},{'villagerId':'baby male','funActivityId':3}]:
   before=copy.deepcopy(self.state)
   with self.assertRaises(ValueError):fun.perform(self.state,data,1030,'invalid')
   self.assertEqual(before,self.state)
 def make_job(self):
  source=next(v for v in self.state['world']['entities'] if v.get('refId')=='Strawberries')
  return tasks.start(self.state,{'villagerId':'steve','userMaterialSourceId':source['id'],'taskTypeId':14,'x':1500,'y':3550,'areaId':1},1000)[0]['workAreaId']
 def test_finish_prices_match_original_knots_and_minimum(self):
  self.assertEqual([tasks.instant_price(v) for v in [1,100,900,2500,50000,604800,700000]],[1,2,3,6,33,125,125])
 def test_instant_finish_then_harvest_charges_once(self):
  ident=self.make_job();response,changed=tasks.instant_complete(self.state,{'workAreaId':ident},1001)
  self.assertTrue(changed);self.assertEqual(self.state['inventory']['323'],39);self.assertEqual(response['completionTime'],1001)
  before=copy.deepcopy(self.state);self.assertFalse(tasks.instant_complete(self.state,{'workAreaId':ident},1002)[1]);self.assertEqual(before,self.state)
  tasks.harvest(self.state,{'workAreaId':ident,'taskTypeId':14},1002);self.assertEqual(self.state['workAreas'][ident]['status'],'harvested')
 def test_naturally_complete_finish_is_free(self):
  ident=self.make_job();tasks.instant_complete(self.state,{'workAreaId':ident},1030);self.assertEqual(self.state['inventory']['323'],40)
 def test_insufficient_gems_preserves_task_and_inventory(self):
  ident=self.make_job();self.state['inventory']['323']=0;before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):tasks.instant_complete(self.state,{'workAreaId':ident},1001)
  self.assertEqual(before,self.state)
if __name__=='__main__':unittest.main()
