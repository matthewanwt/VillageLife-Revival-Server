import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import habitats,world,session,tasks
class HabitatRulesTests(unittest.TestCase):
 def setUp(self):self.state=world.build_bridge_world(session.fresh_tutorial(),1000);self.fire=next(e for e in self.state['world']['entities'] if e['templateType']=='fire_type');self.shelter=next(e for e in self.state['world']['entities'] if e['templateType']=='shelter')
 def fund(self,state):
  for req in world.rows('requirement_set_item'):
   state['inventory'][req['materialType']]=max(state['inventory'].get(req['materialType'],0),float(req['quantity'])+float(req['quantityUsed'])+100)
   if req['materialType']=='7':state['user']['xp']=max(state['user']['xp'],float(req['quantity'])+100)
 def test_all_six_fires_use_original_costs_burn_time_and_expire_once(self):
  for definition in world.rows('fire_task'):
   with self.subTest(fire=definition['fireType']):
    state=copy.deepcopy(self.state);fire=next(e for e in state['world']['entities'] if e['id']==self.fire['id']);fire['templateId']=int(definition['fireType']);self.fund(state)
    task=world.by_id('task',definition['taskId']);before=copy.deepcopy(state['inventory']);response,_=habitats.operate(state,'ClientUserFireService/StartFire',{'userFireId':fire['id'],'villagerId':'steve'},1000,'a')
    self.assertEqual(response['userFire']['endsAt'],1000+int(definition['burnDuration']))
    for req in world.rows('requirement_set_item'):
     if req['requirementSet']==task['requirementSet']:self.assertAlmostEqual(state['inventory'][req['materialType']],before[req['materialType']]-float(req['quantityUsed']))
    snapshot=copy.deepcopy(state);habitats.operate(state,'ClientUserFireService/StartFire',{'userFireId':fire['id'],'villagerId':'steve'},1001,'a');self.assertEqual(state,snapshot)
    state=json.loads(json.dumps(state));self.assertTrue(habitats.sync(state,response['userFire']['endsAt']));self.assertFalse(habitats.sync(state,response['userFire']['endsAt']+1));world.validate_world(state)
 def test_oil_uses_original_quantity_and_extension_and_receipt_survives_reload(self):
  self.fund(self.state);habitats.start_fire(self.state,{'userFireId':self.fire['id'],'villagerId':'steve'},1000);self.state['inventory']['8']=1000;before=self.fire['endsAt']
  data={'userFireId':self.fire['id']};result,_=habitats.operate(self.state,'ClientUserFireService/OilFire',data,1010,'oil')
  self.assertEqual(self.state['inventory']['8'],990);self.assertEqual(result['userFire']['endsAt'],before+43200)
  self.state=json.loads(json.dumps(self.state));snapshot=copy.deepcopy(self.state);habitats.operate(self.state,'ClientUserFireService/OilFire',data,1020,'oil');self.assertEqual(snapshot,self.state)
 def test_all_fire_types_charge_their_own_oil_quantity(self):
  for definition in world.rows('fire_type'):
   with self.subTest(fire=definition['id']):
    state=copy.deepcopy(self.state);fire=next(e for e in state['world']['entities'] if e['id']==self.fire['id']);fire['templateId']=int(definition['id']);self.fund(state);habitats.start_fire(state,{'userFireId':fire['id'],'villagerId':'steve'},1000);state['inventory']['8']=1000;before=fire['endsAt'];habitats.oil_fire(state,{'userFireId':fire['id']},1010)
    self.assertEqual(state['inventory']['8'],1000-int(definition['oilQuantity']));self.assertEqual(fire['endsAt'],before+int(world.global_value('oilBurnDuration')))
 def test_oil_unlit_or_unfunded_fire_is_rejected_without_charge(self):
  before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):habitats.oil_fire(self.state,{'userFireId':self.fire['id']},1000)
  self.assertEqual(self.state,before);self.fund(self.state);habitats.start_fire(self.state,{'userFireId':self.fire['id'],'villagerId':'steve'},1000);self.state['inventory']['8']=0;before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):habitats.oil_fire(self.state,{'userFireId':self.fire['id']},1001)
  self.assertEqual(self.state,before)
 def test_busy_villager_and_baby_cannot_light_fire(self):
  self.fund(self.state);data={'userFireId':self.fire['id'],'villagerId':'baby male'}
  with self.assertRaises(ValueError):habitats.start_fire(self.state,data,1000)
  source=next(e for e in self.state['world']['entities'] if e.get('refId')=='Strawberries');tasks.start(self.state,{'villagerId':'steve','taskTypeId':14,'userMaterialSourceId':source['id'],**source['position']},1000)
  with self.assertRaises(ValueError):habitats.start_fire(self.state,{**data,'villagerId':'steve'},1001)
 def test_lighting_blocks_other_work_until_original_animation_duration(self):
  self.fund(self.state);habitats.start_fire(self.state,{'userFireId':self.fire['id'],'villagerId':'steve'},1000)
  source=next(e for e in self.state['world']['entities'] if e.get('refId')=='Strawberries');data={'villagerId':'steve','taskTypeId':14,'userMaterialSourceId':source['id'],**source['position']}
  with self.assertRaises(ValueError):tasks.start(self.state,data,1001)
  self.assertTrue(tasks.start(self.state,data,1006)[1])
 def test_all_49_shelters_assign_clear_persist_and_reward_original_happiness(self):
  for definition in world.rows('shelter'):
   with self.subTest(shelter=definition['id']):
    state=copy.deepcopy(self.state);shelter=next(e for e in state['world']['entities'] if e['id']==self.shelter['id']);shelter['templateId']=int(definition['id']);ident=shelter['beds'][0]['id']
    habitats.operate(state,'ClientUserShelterService/AssignBedToVillager',{'villagerId':'steve','shelterBedId':ident},1000,'assign');state=json.loads(json.dumps(state));world.validate_world(state)
    with self.assertRaises(ValueError):habitats.happiness(state,{'userShelterId':shelter['id']},1001)
    before=state['user']['xp'];response,_=habitats.operate(state,'ClientUserShelterService/CollectShelterHappiness',{'userShelterId':shelter['id']},87400,'collect');self.assertEqual(state['user']['xp'],before+int(definition['happinessReward']));self.assertEqual(response['xp'],int(definition['happinessReward']))
    state=json.loads(json.dumps(state));snapshot=copy.deepcopy(state);habitats.operate(state,'ClientUserShelterService/CollectShelterHappiness',{'userShelterId':shelter['id']},87401,'collect');self.assertEqual(state,snapshot)
    habitats.operate(state,'ClientUserShelterService/EmptyBed',{'shelterBedId':ident},87402,'empty');world.validate_world(state);self.assertEqual(next(e for e in state['world']['entities'] if e['id']=='steve')['shelterBedId'],'')
 def test_occupied_bed_cannot_evict_and_moving_clears_old_reference(self):
  a,b=self.shelter['beds'];habitats.assign(self.state,{'villagerId':'steve','shelterBedId':a['id']},1000);before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):habitats.assign(self.state,{'villagerId':'jill','shelterBedId':a['id']},1001)
  self.assertEqual(self.state,before);habitats.assign(self.state,{'villagerId':'steve','shelterBedId':b['id']},1002);self.assertEqual(a['villagerId'],'');world.validate_world(self.state)
 def test_shelter_reward_is_per_occupant_and_waits_the_native_full_day(self):
  for person,target in zip(['steve','jill'],self.shelter['beds']):habitats.assign(self.state,{'villagerId':person,'shelterBedId':target['id']},1000)
  with self.assertRaises(ValueError):habitats.happiness(self.state,{'userShelterId':self.shelter['id']},87399)
  response,_=habitats.happiness(self.state,{'userShelterId':self.shelter['id']},87400);self.assertEqual(response['xp'],1400)
 def test_unknown_bed_foreign_objects_and_reused_receipt_are_rejected(self):
  with self.assertRaises(ValueError):habitats.assign(self.state,{'villagerId':'steve','shelterBedId':'foreign'},1000)
  data={'villagerId':'steve','shelterBedId':self.shelter['beds'][0]['id']};habitats.operate(self.state,'ClientUserShelterService/AssignBedToVillager',data,1000,'same')
  with self.assertRaises(ValueError):habitats.operate(self.state,'ClientUserShelterService/AssignBedToVillager',{**data,'villagerId':'jill'},1001,'same')
 def test_all_shelter_construction_results_include_native_bed_records(self):
  count=0
  for foundation in world.rows('building_task'):
   building=world.by_id('building_type',foundation['buildingType'])
   if building['entityRef']!='shelter':continue
   definition=world.by_id('task',foundation['taskId'])
   if definition['taskType']!='2':continue
   with self.subTest(foundation=foundation['id']):
    state=copy.deepcopy(self.state);self.fund(state);point={'x':4000,'y':4000,'rotation':0,'areaId':1};source={'id':'fixture-foundation','templateType':'building_task','templateId':int(foundation['id']),'position':point,'serverPersisted':True};state['world']['entities'].append(source)
    response,_=tasks.start(state,{'villagerId':'steve','taskTypeId':int(definition['id']),**point},1000,'ClientTaskService/StartBuildingTask')
    completed,_=tasks.harvest(state,{'workAreaId':response['workAreaId'],'taskTypeId':int(definition['id'])},response['completionTime']);record=completed['objects'][0];self.assertEqual(len(record['beds']),2);self.assertTrue(all(b.get('id') and 'shelterSlotID' in b for b in record['beds']));self.assertIn('id',record['position']);world.validate_world(json.loads(json.dumps(state)));count+=1
  self.assertEqual(count,38)
 def test_overlay_beds_match_extra_native_json_descent_without_changing_save(self):
  before=copy.deepcopy(self.state);projection=world.area_content(self.state,1)['areaJson']['entities'];shelter=next(e for e in projection if e['id']==self.shelter['id'])
  self.assertEqual([next(iter(entry.values()))['id'] for entry in shelter['beds']],[b['id'] for b in self.shelter['beds']]);self.assertEqual(self.state,before)
 def test_migration_is_idempotent_and_reset_does_not_erase_timer(self):
  before=copy.deepcopy(self.state);self.assertFalse(habitats.migrate(self.state,1001));self.assertEqual(self.state,before)
  habitats.assign(self.state,{'villagerId':'steve','shelterBedId':self.shelter['beds'][0]['id']},1000);result,changed=habitats.happiness(self.state,{'userShelterId':self.shelter['id']},1100,True);self.assertFalse(changed);self.assertEqual(result['userShelter']['happinessCollectedAt'],1000)

class HabitatTransactionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);scope=patch.object(session,'STATE',Path(self.tmp.name));scope.start();self.addCleanup(scope.stop)
  self.profile=session.login({'deviceId':'habitat-test'})['data']['users'][0];self.path=session.profile_path('habitat-test').with_suffix('.tutorial.json');self.saved={'userHash':session.fresh_tutorial()['userHash'],'normal':world.build_bridge_world(session.fresh_tutorial(),1000)};session.atomic_json(self.path,self.saved)
 def call(self,service,data,at=1000,ident='1'):
  with patch.object(session,'wire_time',return_value=at):return session.process({**self.profile,'data':{'calls':[{'id':ident,'service':service,'data':data}]}})['data']['calls'][0]
 def test_failed_fire_start_never_spends_saved_materials(self):
  fire=next(e for e in self.saved['normal']['world']['entities'] if e['templateType']=='fire_type');before=self.path.read_bytes();response=self.call('ClientUserFireService/StartFire',{'userFireId':fire['id'],'villagerId':'steve'});self.assertEqual(response['code'],400);self.assertEqual(self.path.read_bytes(),before)
 def test_fire_and_oil_commit_and_expire_through_authenticated_calls(self):
  fire=next(e for e in self.saved['normal']['world']['entities'] if e['templateType']=='fire_type');self.saved['normal']['inventory'].update({'72':100,'87':100,'8':1000});session.atomic_json(self.path,self.saved)
  data={'userFireId':fire['id'],'villagerId':'steve'};response=self.call('ClientUserFireService/StartFire',data);self.assertEqual(response['code'],200);self.assertEqual(response['data']['userFire']['endsAt'],2800)
  oil=self.call('ClientUserFireService/OilFire',{'userFireId':fire['id']},1010,'2');self.assertEqual(oil['code'],200);self.assertEqual(oil['data']['userFire']['endsAt'],46000)
  before=self.path.read_bytes();self.call('ClientUserFireService/OilFire',{'userFireId':fire['id']},1011,'2');self.assertEqual(self.path.read_bytes(),before)
  self.call('ClientUser/KeepActive',{},46000,'3');saved=json.loads(self.path.read_text());self.assertEqual(saved['normal']['inventory']['72'],90);self.assertEqual(saved['normal']['inventory']['8'],990);self.assertEqual(saved['normal']['inventory']['201'],self.saved['normal']['inventory'].get('201',0))
 def test_assignment_and_happiness_commit_through_authentication(self):
  shelter=next(e for e in self.saved['normal']['world']['entities'] if e['templateType']=='shelter');data={'villagerId':'steve','shelterBedId':shelter['beds'][0]['id']}
  self.assertEqual(self.call('ClientUserShelterService/AssignBedToVillager',data)['code'],200)
  self.assertEqual(self.call('ClientUserShelterService/CollectShelterHappiness',{'userShelterId':shelter['id']},87400,'2')['data']['xp'],700)
  self.assertEqual(json.loads(self.path.read_text())['normal']['user']['xp'],700)
  before=self.path.read_bytes();self.profile['sessionId']='wrong';self.assertEqual(self.call('ClientUserShelterService/EmptyBed',{'shelterBedId':data['shelterBedId']})['code'],403);self.assertEqual(self.path.read_bytes(),before)
if __name__=='__main__':unittest.main()
