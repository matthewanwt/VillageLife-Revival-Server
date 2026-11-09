"""Validate persistence and repeat requests for post-tutorial systems."""
import unittest,copy
import world,session,progression,quests,needs,community,shop
class PostTutorialTests(unittest.TestCase):
 def setUp(self):
  self.saved={'normal':world.build_bridge_world(session.fresh_tutorial(),1000),'gameSettings':{'activeSequenceId':'1723'}}
  self.state=self.saved['normal']
 def test_scripted_xp_applied_once(self):
  self.assertTrue(progression.sync_inventory_assignments(self.saved));self.assertEqual(self.state['user']['xp'],72)
  before=copy.deepcopy(self.state);self.assertFalse(progression.sync_inventory_assignments(self.saved));self.assertEqual(before,self.state)
 def test_finished_tutorial_retains_scripted_xp_even_after_checkpoint_cleared(self):
  self.saved['gameSettings'].update(activeSequenceId='-1',isFtueComplete='1')
  self.assertTrue(progression.sync_inventory_assignments(self.saved));self.assertEqual(self.state['user']['xp'],72)
  self.assertFalse(progression.sync_inventory_assignments(self.saved))
 def test_levelup_and_repeat_do_not_duplicate_rewards(self):
  progression.sync_inventory_assignments(self.saved)
  result,changed=progression.increase_level(self.state,{'IsPaid':'false','WheelOfFortuneTypeID':3})
  self.assertTrue(changed);self.assertEqual(self.state['user']['userLevelID'],2);self.assertEqual(result['result']['PopulationCap'],21)
  before=copy.deepcopy(self.state);self.assertEqual(progression.increase_level(self.state,{}),(result,False));self.assertEqual(before,self.state)
 def test_paid_and_insufficient_levelup_rejected(self):
  self.state['user']['xp']=0
  with self.assertRaises(ValueError):progression.increase_level(self.state,{})
  with self.assertRaises(ValueError):progression.increase_level(self.state,{'IsPaid':'true'})
 def test_story_quest_requires_completed_building_and_is_idempotent(self):
  data={'objectId':'54','questTypeId':12,'amount':1}
  result,changed=quests.add(self.state,data,1000);self.assertTrue(changed)
  self.assertEqual(quests.add(self.state,data,1001),(result,False));ident=result['userQuest']['id']
  with self.assertRaises(ValueError):quests.complete(self.state,{'userQuestId':ident},1002)
  self.state['inventory']['442']=1
  receipt,changed=quests.complete(self.state,{'userQuestId':ident},1003);self.assertTrue(changed)
  before=copy.deepcopy(self.state);self.assertEqual(quests.complete(self.state,{'userQuestId':ident},1004),(receipt,False));self.assertEqual(before,self.state)
 def test_invalid_quest_does_not_mutate(self):
  before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):quests.add(self.state,{'objectId':'not-a-story','questTypeId':12,'amount':1},1000)
  self.assertEqual(before,self.state)
 def test_needs_are_stable_and_consumption_is_once_only(self):
  first,changed=needs.generate(self.state,'ClientWant/GenerateFoodWants',1000);self.assertTrue(changed)
  self.assertEqual(needs.generate(self.state,'ClientWant/GenerateFoodWants',1001),(first,False))
  want=next(v for v in first['result'] if v['VillagerStringID']=='steve');self.state['inventory']['107']=5
  data={'VillagerStringID':'steve','MaterialTypeID':107,'WantID':want['WantId']}
  response,changed=needs.consume(self.state,data,1002);self.assertTrue(changed);self.assertEqual(self.state['inventory']['107'],4)
  before=copy.deepcopy(self.state);self.assertEqual(needs.consume(self.state,data,1003),(response,False));self.assertEqual(before,self.state)
  needs.generate(self.state,'ClientWant/GenerateFoodWants',1100)
  self.assertFalse(any(v['VillagerStringID']=='steve' and v['wantableCategoryType']==2 for v in self.state['wants']))
  needs.generate(self.state,'ClientWant/GenerateFoodWants',1603)
  self.assertTrue(any(v['VillagerStringID']=='steve' and v['wantableCategoryType']==2 for v in self.state['wants']))
 def test_release_xp_only_once_and_consume_receipt_checks_actor(self):
  needs.generate(self.state,'ClientWant/GenerateFoodWants',1000);self.state['inventory']['107']=5
  want=next(v for v in self.state['wants'] if v['VillagerStringID']=='steve')
  needs.consume(self.state,{'VillagerStringID':'steve','MaterialTypeID':107,'WantID':want['WantId']},1001)
  before=self.state['user']['xp'];actor=needs.actor_by_id(self.state,'steve');amount=actor['xp']
  needs.release_xp(self.state,{'VillagerStringID':'steve'});self.assertEqual(self.state['user']['xp'],before+amount)
  self.assertFalse(needs.release_xp(self.state,{'VillagerStringID':'steve'})[1])
  with self.assertRaises(ValueError):needs.consume(self.state,{'VillagerStringID':'jill','MaterialTypeID':107,'WantID':want['WantId']},1002)
 def test_quick_drink_retry_without_want_id_does_not_spend_twice(self):
  needs.generate(self.state,'ClientWant/GenerateWaterWants',1000);self.state['inventory']['6']=5
  data={'VillagerStringID':'brother','MaterialTypeID':6}
  response,changed=needs.consume(self.state,data,1001);self.assertTrue(changed)
  self.assertIn('WantId',response['SatisfiedWantModels'][0]);self.assertNotIn('WantID',response['SatisfiedWantModels'][0])
  self.state['inventory']['6']=12
  again,changed=needs.consume(self.state,data,1002);self.assertFalse(changed);self.assertEqual(self.state['inventory']['6'],12)
  self.assertEqual(next(v['amount'] for v in again['inventory'] if v['materialTypeId']==6),12)
 def test_complex_needs_are_explicitly_deferred(self):
  self.assertTrue(needs.generate(self.state,'ClientWant/GenerateRetirementWants',1000)[1]);self.assertFalse(needs.generate(self.state,'ClientWant/GenerateRetirementWants',1001)[1])
  self.assertIn('GenerateRetirementWants',self.state['deferredNeedSystems'])
 def test_blankies_charge_original_gem_price_and_retries_are_safe(self):
  self.state['inventory']['323']=50
  data={'amount':10,'materialTypeId':444}
  self.assertTrue(shop.buy(self.state,data,'epoch:65')[1]);self.assertEqual(self.state['inventory']['323'],40);self.assertEqual(self.state['inventory']['444'],10)
  before=copy.deepcopy(self.state);self.assertFalse(shop.buy(self.state,data,'epoch:65')[1]);self.assertEqual(self.state,before)
  shop.buy(self.state,data,'new-epoch:65');self.assertEqual(self.state['inventory']['323'],30)
 def test_shop_invalid_or_unaffordable_request_does_not_spend(self):
  self.state['inventory']['323']=0;before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):shop.buy(self.state,{'amount':10,'materialTypeId':444},'epoch:65')
  self.assertEqual(before,self.state)
  with self.assertRaises(ValueError):shop.buy(self.state,{'amount':11,'materialTypeId':444},'epoch:66')
  with self.assertRaises(ValueError):shop.buy(self.state,{'amount':1,'materialTypeId':107},'epoch:67')
 def test_community_configuration_is_disabled_and_unknown_fails(self):
  result=community.process({'Calls':[{'Id:':1,'Service':'ApplicationSetting/Get'}]})
  item=result['data'][0];self.assertEqual(item['code'],200);self.assertIn({'Key':'ChatEnabled','Value':'0'},item['Data']['ApplicationSettings'])
  self.assertEqual(community.process({'Calls':[{'Id:':2,'Service':'Unknown'}]})['data'][0]['code'],501)
if __name__=='__main__':unittest.main()
