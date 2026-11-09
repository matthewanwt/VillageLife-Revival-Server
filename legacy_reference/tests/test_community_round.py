import copy,json,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import world,session,progression,needs,shop,interactive

class CommunityRoundTests(unittest.TestCase):
 def setUp(self):self.state=world.build_bridge_world(session.fresh_tutorial(),1000)
 def test_cached_authored_definitions_cannot_be_changed_through_a_returned_record(self):
  first=world.by_id('material_type',137);name=first['name'];first['name']='changed'
  table=world.rows('material_type');next(v for v in table if v['id']=='137')['name']='also changed'
  self.assertEqual(world.by_id('material_type',137)['name'],name)
  self.assertEqual(next(v['name'] for v in world.rows('material_type') if v['id']=='137'),name)
 def test_paid_price_original_level_three_boundaries(self):
  self.state['user'].update(userLevelID=3,xp=106)
  self.assertEqual(progression.paid_level_price(self.state),11)
  self.state['user']['xp']=231;self.assertEqual(progression.paid_level_price(self.state),10)
  self.state['user']['xp']=355;self.assertEqual(progression.paid_level_price(self.state),9)
  self.state['user']['xp']=356;self.assertEqual(progression.paid_level_price(self.state),0)
 def test_all_playable_level_prices_within_authored_bounds(self):
  levels=sorted(world.rows('user_level'),key=lambda r:int(r['levelNumber']))
  for index,row in enumerate(levels[:-1]):
   level=int(row['levelNumber']);previous=int(levels[index-1]['experienceRequired']) if index else 0
   for xp in [previous,(previous+int(row['experienceRequired']))//2,int(row['experienceRequired'])-1]:
    self.state['user'].update(userLevelID=level,xp=xp)
    price=progression.paid_level_price(self.state)
    self.assertGreaterEqual(price,0);self.assertLessEqual(price,int(row['fillCost'])+1)
    if price==0:
     import struct
     f=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]
     self.assertGreaterEqual(f(xp),f(int(row['experienceRequired'])))
 def test_paid_level_is_atomic_persists_and_replay_never_spends_twice(self):
  self.state['inventory']['323']=100;self.state['user']['xp']=0
  result,changed=progression.increase_level(self.state,{'IsPaid':'true'},'level:1')
  self.assertTrue(changed);self.assertEqual(self.state['inventory']['323'],115);self.assertEqual(self.state['user']['userLevelID'],2);self.assertEqual(self.state['user']['xp'],36)
  self.state=json.loads(json.dumps(self.state));before=copy.deepcopy(self.state)
  self.assertEqual(progression.increase_level(self.state,{'IsPaid':'true'},'level:1'),(result,False));self.assertEqual(before,self.state)
  with self.assertRaises(ValueError):progression.increase_level(self.state,{'IsPaid':'false'},'level:1')
 def test_unaffordable_or_invalid_paid_level_never_changes_state(self):
  self.state['inventory']['323']=0;before=copy.deepcopy(self.state)
  for data,key in [({'IsPaid':'true'},'x'),({'IsPaid':'yes'},'y'),({'IsPaid':'true'},None)]:
   with self.assertRaises(ValueError):progression.increase_level(self.state,data,key)
   self.assertEqual(before,self.state)
 def test_all_original_store_bundles_charge_and_grant_exact_quantities_once(self):
  for item in world.rows('store_item'):
   state={'inventory':{'323':1000000},'revision':1}
   data={'storeItemId':int(item['id']),'multiples':2}
   shop.buy_store(state,data,'bundle')
   self.assertEqual(state['inventory']['323'],1000000-int(item['price_gems'])*2)
   self.assertEqual(state['inventory'][item['material_type']],int(item['qty'])*2)
   state=json.loads(json.dumps(state));before=copy.deepcopy(state)
   self.assertFalse(shop.buy_store(state,data,'bundle')[1]);self.assertEqual(before,state)
   with self.assertRaises(ValueError):shop.buy_store(state,{**data,'multiples':3},'bundle')
 def infant(self,gender=0):
  person=next(p for p in self.state['world']['entities'] if p['id']=='brother');person.update(templateId=3 if not gender else 4,startAge=0,bornAt=1000,gender=gender,xp=0);return person
 def test_both_infant_genders_get_interactive_bottle_not_ordinary_food_or_water(self):
  for gender in [0,1]:
   self.state=world.build_bridge_world(session.fresh_tutorial(),1000);person=self.infant(gender)
   needs.generate(self.state,'ClientWant/GenerateFoodWants',1000);needs.generate(self.state,'ClientWant/GenerateWaterWants',1000);interactive.generate(self.state,1000)
   wants=[w for w in self.state['wants'] if w['VillagerStringID']==person['id']]
   self.assertEqual([(w['wantableCategoryType'],w['MaterialID']) for w in wants],[(8,494)])
 def test_feeding_cost_xp_cooldown_and_reload(self):
  person=self.infant();self.state['inventory'].update({'487':10,'72':10})
  interactive.generate(self.state,1000)
  data={'requesterVillagerId':person['id'],'supplierVillagerId':'steve','activityId':'1'}
  response,_=interactive.perform(self.state,data,1001,'feeding')
  self.assertEqual(self.state['inventory']['487'],6);self.assertEqual(self.state['inventory']['72'],8);self.assertEqual(person['xp'],12)
  self.state=json.loads(json.dumps(self.state));before=copy.deepcopy(self.state)
  self.assertFalse(interactive.perform(self.state,data,1002,'feeding')[1]);self.assertEqual(before,self.state)
  interactive.generate(self.state,1002);self.assertFalse(any(w['VillagerStringID']==person['id'] for w in self.state['wants']))
  interactive.generate(self.state,21001);self.assertTrue(any(w['VillagerStringID']==person['id'] for w in self.state['wants']))
 def test_bottle_want_removed_when_child_ages_out_of_feeding_group(self):
  person=self.infant();interactive.generate(self.state,1000)
  at=1000+int(float(world.global_value('hours_per_year'))*3600*5)
  interactive.generate(self.state,at);needs.generate(self.state,'ClientWant/GenerateFoodWants',at)
  wants=[w for w in self.state['wants'] if w['VillagerStringID']==person['id']]
  self.assertTrue(any(w['MaterialID']==107 and w['wantableCategoryType']==2 for w in wants));self.assertFalse(any(w['MaterialID']==494 for w in wants))
 def test_child_intro_matches_authored_world_without_age_regression(self):
  seed=session.fresh_tutorial();ident=next(v for v in seed['userHash']['data']['villagers'] if v['refId']=='sister')
  source=world.by_id('villager_starting_variation',ident['variationId'])
  person=next(p for p in self.state['world']['entities'] if p['id']=='sister')
  self.assertEqual(int(source['startAge']),person['startAge']);self.assertEqual(person['startAge'],12)
  self.assertEqual(person['name'],source['name']);self.assertEqual(person['templateId'],11);self.assertEqual(source['villagerType'],'11')
 def test_custom_tutorial_twin_names_survive_bridge_and_restart(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(session,'STATE',Path(tmp)),patch.object(session,'wire_time',return_value=1000):
   profile=session.login({'deviceId':'named-twins'})['data']['users'][0]
   def call(service,data):
    result=session.process({**profile,'data':{'calls':[{'id':1,'service':service,'data':data}]}})['data']['calls'][0]
    self.assertEqual(result['code'],200);return result['data']
   call('ClientUserHashService/SetVillagerName',{'villagerId':'baby male','name':'Custom Boy'})
   call('ClientUserHashService/SetVillagerName',{'villagerId':'baby female','name':'Custom Girl'})
   call('ClientUserHashService/SetActiveSequence',{'activeSequence':217});call('ClientUserService/ProgressArea',{})
   session.login({'deviceId':'named-twins'})
   saved=json.loads(session.profile_path('named-twins').with_suffix('.tutorial.json').read_text())
   for key,name in [('baby male','Custom Boy'),('baby female','Custom Girl')]:
    self.assertEqual(next(v['name'] for v in saved['normal']['world']['entities'] if v['id']==key),name)
    self.assertEqual(next(v['name'] for v in saved['userHash']['data']['villagers'] if v['id']==key),name)
if __name__=='__main__':unittest.main()
