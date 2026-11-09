import copy,json,unittest
from unittest.mock import patch
import family,habitats,session,world

class FamilyTests(unittest.TestCase):
 def setUp(self):
  self.state=world.build_bridge_world(session.fresh_tutorial(),1000);self.state['inventory']['323']=500
  for ident in ['steve','jill']:
   a=family.actor(self.state,ident);a.update(startAge=25,bornAt=1000)
  home={'id':'test-family-home','templateType':'shelter','templateId':0,'position':{'x':2200,'y':3400,'areaId':1,'rotation':0},'serverPersisted':True};habitats.initialize(home,1000);self.state['world']['entities'].append(home)
  for ident,bed in zip(['steve','jill'],home['beds']):habitats.assign(self.state,{'villagerId':ident,'shelterBedId':bed['id']},1000)
 def call(self,service,data,at=1000,key='test:1'):
  return family.operate(self.state,service,data,at,'424242',key)
 def conceive(self):
  with patch.object(family,'roll',side_effect=[0,99,0]):return self.call('ClientVillager/CanConcievePregnancy',{'villagerId':'jill'})
 def test_success_uses_native_pregnancy_info_and_24_hour_native_timer(self):
  response,changed=self.conceive();self.assertTrue(changed);self.assertEqual(response['result']['PregnancyInfo'],{'pregnant':1,'pregnancyStartTime':1000,'pregnancyTryCount':1});self.assertEqual(self.state['pregnancies']['jill']['readyAt'],87400)
  self.assertEqual(world.current_villager_type(family.actor(self.state,'jill'),1000)['id'],'2');world.validate_world(self.state)
 def test_failure_cooldown_then_original_guaranteed_attempt_threshold(self):
  with patch.object(family,'roll',return_value=99):
   self.call('ClientVillager/CanConcievePregnancy',{'villagerId':'jill'})
   response,_=self.call('ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},1001,'test:2');self.assertEqual(response['result']['PregnancyInfo']['pregnancyTryCount'],1)
   self.call('ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},29800,'test:3')
   response,_=self.call('ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},58600,'test:4')
  self.assertEqual(response['result']['PregnancyInfo']['pregnant'],1);self.assertEqual(response['result']['PregnancyInfo']['pregnancyTryCount'],3)
 def test_request_retry_does_not_reroll_or_overwrite_current_state(self):
  self.conceive();before=copy.deepcopy(self.state)
  with patch.object(family,'roll',side_effect=AssertionError('rerolled')):self.assertFalse(self.call('ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},1001)[1])
  self.assertEqual(before,self.state)
  with self.assertRaisesRegex(ValueError,'reused'):self.call('ClientVillager/CanConcievePregnancy',{'villagerId':'steve'})
 def test_same_shelter_and_adult_married_parents_required(self):
  for change in ['bed','age','marriage']:
   with self.subTest(change=change):
    state=copy.deepcopy(self.state);mother=family.actor(state,'jill')
    if change=='bed':mother['shelterBedId']=''
    elif change=='age':mother['startAge']=12
    else:mother['relations']=[]
    before=copy.deepcopy(state)
    with self.assertRaises(ValueError):family.operate(state,'ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},1000,'424242','test:1')
    self.assertEqual(before,state)
 def test_population_limit_rejects_before_mutation(self):
  self.state['user']['populationCap']=family.population(self.state);before=copy.deepcopy(self.state)
  with self.assertRaisesRegex(ValueError,'capacity'):self.conceive()
  self.assertEqual(before,self.state)
 def test_natural_twins_follow_original_chance_and_reserve_population(self):
  with patch.object(family,'roll',side_effect=[0,0,0,1]):self.call('ClientVillager/CanConcievePregnancy',{'villagerId':'jill'})
  self.assertEqual(len(self.state['pregnancies']['jill']['children']),2);self.assertEqual(family.free_places(self.state),self.state['user']['populationCap']-family.population(self.state)-2)
 def test_last_free_population_slot_limits_natural_pregnancy_to_one(self):
  self.state['user']['populationCap']=family.population(self.state)+1
  with patch.object(family,'roll',return_value=0):self.call('ClientVillager/CanConcievePregnancy',{'villagerId':'jill'})
  self.assertEqual(len(self.state['pregnancies']['jill']['children']),1)
 def test_original_twins_triplets_and_gender_prices_and_no_double_charge(self):
  for kind,cost,count,gender in [(1,0,1,None),(2,100,2,None),(9,199,3,None),(7,5,1,0),(8,5,1,1)]:
   with self.subTest(kind=kind):
    self.setUp();self.conceive()
    with patch.object(family,'roll',return_value=0):reply,_=self.call('ClientVillager/DesignPregnancy',{'villagerId':'jill','pregnancyType':str(kind)},1001,'test:2')
    record=self.state['pregnancies']['jill'];self.assertEqual(self.state['inventory']['323'],500-cost);self.assertEqual(len(record['children']),count)
    if gender is not None:self.assertTrue(all(c['gender']==gender for c in record['children']))
    before=copy.deepcopy(self.state);self.assertFalse(self.call('ClientVillager/DesignPregnancy',{'villagerId':'jill','pregnancyType':str(kind)},1002,'test:2')[1]);self.assertEqual(self.state,before)
    self.call('ClientVillager/DesignPregnancy',{'villagerId':'jill','pregnancyType':kind},1003,'test:3');self.assertEqual(self.state['inventory']['323'],500-cost)
 def test_insufficient_gems_or_population_cannot_partially_spend(self):
  self.conceive()
  for shortage in ['gems','population']:
   with self.subTest(shortage=shortage):
    state=copy.deepcopy(self.state)
    if shortage=='gems':state['inventory']['323']=0
    else:state['user']['populationCap']=family.population(state)+1
    before=copy.deepcopy(state)
    with self.assertRaises(ValueError):family.operate(state,'ClientVillager/DesignPregnancy',{'villagerId':'jill','pregnancyType':'2'},1001,'424242','test:2')
    self.assertEqual(before,state)
 def test_birth_is_not_early_and_retries_do_not_duplicate_newborn(self):
  self.conceive();before=copy.deepcopy(self.state)
  with self.assertRaisesRegex(ValueError,'not ready'):self.call('ClientVillager/Birth',{'VillagerStringID':'jill'},87399,'test:2')
  self.assertEqual(before,self.state)
  response,_=self.call('ClientVillager/Birth',{'VillagerStringID':'jill'},87400,'test:2');baby=response['result']['villagers'][0];ident='Villager_424242_'+baby['ID'];child=family.actor(self.state,ident)
  self.assertEqual(child['bornAt'],87400);self.assertEqual(child['startAge'],0);self.assertEqual(child['gender'],baby['Gender']);self.assertEqual(child['equipment'],baby['Equipment']);self.assertFalse(family.is_pregnant(family.actor(self.state,'jill')))
  before=copy.deepcopy(self.state);self.assertFalse(self.call('ClientVillager/Birth',{'VillagerStringID':'jill'},87401,'test:2')[1]);self.assertEqual(before,self.state)
  self.call('ClientVillager/Birth',{'VillagerStringID':'jill'},87402,'test:3');self.assertEqual(family.population(self.state),7);world.validate_world(self.state)
 def test_newborn_family_references_and_siblings_are_bidirectional(self):
  self.conceive();self.call('ClientVillager/Birth',{'VillagerStringID':'jill'},87400,'test:2');record=self.state['pregnancies']['jill'];child=family.actor(self.state,record['bornChildren'][0])
  for parent in ['steve','jill']:
   self.assertIn({'villagerId':parent,'type':0},child['relations']);self.assertIn({'villagerId':child['id'],'type':1},family.actor(self.state,parent)['relations'])
  self.assertIn({'villagerId':'baby male','type':3},child['relations']);self.assertIn({'villagerId':child['id'],'type':3},family.actor(self.state,'baby male')['relations'])
 def test_newborn_naming_reload_and_later_age_resolver(self):
  self.conceive();self.call('ClientVillager/Birth',{'VillagerStringID':'jill'},87400,'test:2');ident=self.state['pregnancies']['jill']['bornChildren'][0]
  self.call('ClientVillagerService/SetName',{'villagerId':ident,'name':'Test Baby'},87401,'test:3');self.state=json.loads(json.dumps(self.state));child=family.actor(self.state,ident)
  self.assertEqual(child['name'],'Test Baby');self.assertEqual(world.current_villager_type(child,87400+18*86400)['id'],'1')
  before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):self.call('ClientVillagerService/SetName',{'villagerId':ident,'name':'bad\nname'},87402,'test:4')
  self.assertEqual(before,self.state)
 def test_second_pregnancy_uses_new_child_ids_and_old_birth_receipt_is_stable(self):
  self.conceive();first,_=self.call('ClientVillager/Birth',{'VillagerStringID':'jill'},87400,'test:2');first_ids=[v['ID'] for v in first['result']['villagers']]
  at=87400+int(world.global_value('childWantDelayAfterLastChild'))
  with patch.object(family,'roll',side_effect=[0,99,1]):self.call('ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},at,'test:3')
  second,_=self.call('ClientVillager/Birth',{'VillagerStringID':'jill'},at+86400,'test:4');self.assertNotEqual(first_ids,[v['ID'] for v in second['result']['villagers']])
  replay,_=self.call('ClientVillager/Birth',{'VillagerStringID':'jill'},at+86401,'test:2');self.assertEqual(first_ids,[v['ID'] for v in replay['result']['villagers']]);world.validate_world(self.state)

 def test_pregnant_reload_projects_numeric_flag_without_mutating_saved_string(self):
  self.conceive();mother=family.actor(self.state,'jill');self.assertEqual(mother['pregnant'],'true')
  for entities in [world.startup(self.state,1001)['world']['entities'],world.area_content(self.state,1,1001)['areaJson']['entities']]:
   value=next(a for a in entities if a['id']=='jill');self.assertEqual(value['pregnant'],1);self.assertIsInstance(value['pregnant'],int);self.assertEqual(value['templateId'],2)
  self.assertEqual(mother['pregnant'],'true')
 def test_due_time_matches_native_float32_epoch_parsing(self):
  import struct
  at=1793860002
  for person in family.actors(self.state):person['bornAt']=at
  with patch.object(family,'roll',side_effect=[0,99,0]):self.call('ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},at)
  self.assertEqual(self.state['pregnancies']['jill']['readyAt'],int(struct.unpack('<f',struct.pack('<f',at))[0])+86400)

 def test_history_uses_original_gendered_relationship_rows_and_root_arrays(self):
  self.conceive();self.call('ClientVillager/Birth',{'VillagerStringID':'jill'},87400,'test:2')
  before=copy.deepcopy(self.state);reply=family.history(self.state,{'userId':'424242'},87401,'424242')
  self.assertEqual(before,self.state);self.assertEqual(set(reply),{'villagers','villagerRelations'})
  people={p['id']:p for p in reply['villagers']};self.assertEqual(len(people),7)
  child=self.state['pregnancies']['jill']['bornChildren'][0]
  edges={(r['villagerId'],r['relativeVillagerId']):r['relationTypeId'] for r in reply['villagerRelations']}
  self.assertEqual(edges[child,'jill'],3);self.assertEqual(edges[child,'steve'],3)
  self.assertEqual(edges['steve','jill'],5);self.assertEqual(edges['jill','steve'],4)
  self.assertEqual(edges['jill',child],0);self.assertEqual(edges[child,'baby female'],7)
  self.assertTrue(all(p['userId']=='424242' for p in people.values()))
  self.assertEqual(reply,family.history(self.state,{'userId':'424242'},87401,'424242'))
  with self.assertRaises(PermissionError):family.history(self.state,{'userId':'other-player'},87401,'424242')

 def test_profile_skill_read_is_real_saved_data_and_accepts_native_nested_json(self):
  kind=int(world.rows('villager_skill')[0]['id']);person=family.actor(self.state,'steve');person['skills']=[{'skillTypeId':kind,'skillOriginType':0}]
  before=copy.deepcopy(self.state)
  data={'villagerIds':json.dumps({'villagerIds':['steve','jill','steve']})}
  self.assertEqual(family.skills(self.state,data),{'villagerSkills':[{'villagerId':'steve','skilltypeId':kind,'skillOriginType':0}]})
  self.assertEqual(self.state,before)
  self.assertEqual(family.skills(self.state,{'villagerIds':'{"villagerIds":["jill"]}'}),{'villagerSkills':[]})
  for bad in ['not json','[]','{}','{"villagerIds":["other-player-villager"]}','{"villagerIds":[42]}']:
   with self.subTest(bad=bad),self.assertRaises(ValueError):family.skills(self.state,{'villagerIds':bad})

class FamilyServiceIntegrationTests(unittest.TestCase):
 setUp=FamilyTests.setUp
 def test_authenticated_conception_birth_naming_and_restart_use_native_ids(self):
  import tempfile
  from pathlib import Path
  with tempfile.TemporaryDirectory() as directory,patch.object(session,'STATE',Path(directory)),patch.object(session,'wire_time',return_value=1000) as clock:
   profile=session.login({'deviceId':'family-integration-test'})['data']['users'][0];path=session.profile_path('family-integration-test').with_suffix('.tutorial.json');session.atomic_json(path,{'normal':self.state,**session.fresh_tutorial()})
   def request(service,data,ident):
    response=session.process({**profile,'data':{'calls':[{'id':str(ident),'service':service,'data':data}]}})['data']['calls'][0]
    self.assertEqual(response['code'],200,response.get('message'));return response['data']
   with patch.object(family,'roll',side_effect=[0,99,0]):request('ClientVillager/CanConcievePregnancy',{'villagerId':'jill'},1)
   request('ClientVillager/DesignPregnancy',{'villagerId':'jill','pregnancyType':'1'},2);clock.return_value=87400
   response=request('ClientVillager/Birth',{'VillagerStringID':'jill'},3);ident='Villager_'+str(profile['pId'])+'_'+response['result']['villagers'][0]['ID']
   request('ClientVillagerService/SetName',{'villagerId':ident,'name':'Saved Newborn'},4)
   self.assertEqual(request('ClientVillagerService/GetVillagerSkills',{'villagerIds':json.dumps({'villagerIds':[ident]})},7),{'villagerSkills':[]})
   history=request('ClientVillagerService/GetVillagerRelations',{'userId':profile['pId']},6);self.assertEqual(next(v for v in history['villagers'] if v['id']==ident)['name'],'Saved Newborn')
   session.login({'deviceId':'family-integration-test'})
   loaded=json.loads(path.read_text(encoding='utf-8'))['normal'];self.assertEqual(family.actor(loaded,ident)['name'],'Saved Newborn');self.assertEqual(family.population(loaded),7)
   request('ClientVillager/Birth',{'VillagerStringID':'jill'},5);loaded=json.loads(path.read_text(encoding='utf-8'))['normal'];self.assertEqual(family.population(loaded),7);world.validate_world(loaded)

if __name__=='__main__':unittest.main()
