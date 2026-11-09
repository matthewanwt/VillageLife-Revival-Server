"""Shared construction, crafting, restart and scripted-rule checks."""
import unittest,copy,tempfile,json
from pathlib import Path
from unittest.mock import patch
import world,session,tasks,buildings,progression
class CoreSystemsTests(unittest.TestCase):
 def setUp(self):self.saved={'normal':world.build_bridge_world(session.fresh_tutorial(),1000),'gameSettings':{'activeSequenceId':'1613'}};self.state=self.saved['normal']
 def test_scripted_inventory_is_applied_once_from_original_table(self):
  self.assertTrue(progression.sync_inventory_assignments(self.saved));self.assertEqual(self.state['inventory']['82'],10);self.assertEqual(self.state['inventory']['87'],10)
  self.state['inventory']['82']=5;self.assertFalse(progression.sync_inventory_assignments(self.saved));self.assertEqual(self.state['inventory']['82'],5)
 def test_early_checkpoint_does_not_grant_later_tutorial_materials(self):
  self.saved['gameSettings']['activeSequenceId']='1380';before=copy.deepcopy(self.state)
  progression.sync_inventory_assignments(self.saved);self.assertEqual(before['inventory'],self.state['inventory']);self.assertNotIn('82',self.state['inventory'])
 def test_foundation_is_idempotent_and_get_list_restores_it(self):
  data={'buildingTaskTypeId':'34','x':1950,'y':3050,'rotation':0,'areaId':1}
  first,changed=buildings.place(self.state,data);self.assertTrue(changed);before=copy.deepcopy(self.state)
  again,changed=buildings.place(self.state,data);self.assertFalse(changed);self.assertEqual(first,again);self.assertEqual(self.state,before)
  self.assertTrue(any(v['userBuildingTaskId']==first['userBuildingTask']['userBuildingTaskId'] for v in buildings.list_foundations(self.state)['userBuildingTasks']))
  with self.assertRaises(ValueError):buildings.place(self.state,{**data,'x':2100})
 def test_dance_build_consumes_original_cost_and_creates_saved_building_once(self):
  progression.sync_inventory_assignments(self.saved);buildings.place(self.state,{'buildingTaskTypeId':'34','x':1950,'y':3050,'rotation':0,'areaId':1})
  data={'villagerId':'steve','taskTypeId':89,'x':1950,'y':3075,'areaId':1,'rotation':0}
  started,changed=tasks.start(self.state,data,1000,'ClientTaskService/StartBuildingTask');self.assertTrue(changed);self.assertEqual(started['completionTime'],1060)
  self.assertEqual(self.state['inventory']['82'],5);self.assertEqual(self.state['inventory']['87'],5)
  result,changed=tasks.harvest(self.state,{'workAreaId':started['workAreaId'],'taskTypeId':89},1060);self.assertTrue(changed)
  self.assertEqual(len(result['objects']),1);self.assertTrue(any(v['id']==result['objects'][0]['id'] and v['templateType']=='fun_building' and v['templateId']==0 for v in self.state['world']['entities']))
  before=copy.deepcopy(self.state);tasks.harvest(self.state,{'workAreaId':started['workAreaId'],'taskTypeId':89},1100);self.assertEqual(self.state,before)
 def test_native_foundation_delete_after_start_preserves_build_and_is_idempotent(self):
  progression.sync_inventory_assignments(self.saved);placement,_=buildings.place(self.state,{'buildingTaskTypeId':'34','x':1950,'y':3050,'areaId':1})
  started,_=tasks.start(self.state,{'villagerId':'steve','taskTypeId':89,'x':1950,'y':3050,'areaId':1},1000,'ClientTaskService/StartBuildingTask')
  ident=placement['userBuildingTask']['userBuildingTaskId'];self.assertTrue(buildings.delete(self.state,{'userBuildingTaskId':ident})[1]);world.validate_world(self.state)
  before=copy.deepcopy(self.state);self.assertFalse(buildings.delete(self.state,{'userBuildingTaskId':ident})[1]);self.assertEqual(before,self.state)
  with self.assertRaises(ValueError):buildings.place(self.state,{'buildingTaskTypeId':'34','x':2100,'y':3050,'areaId':1})
  reloaded=json.loads(json.dumps(self.state));result,_=tasks.harvest(reloaded,{'workAreaId':started['workAreaId'],'taskTypeId':89},1060)
  self.assertEqual(len(result['objects']),1);world.validate_world(reloaded)
 def test_crafting_uses_same_saved_task_engine(self):
  self.state['inventory']['77']=6
  data={'villagerId':'steve','taskTypeId':20,'x':1786,'y':3362,'areaId':1,'rotation':0}
  started,_=tasks.start(self.state,data,1000,'ClientTaskService/StartCraftingTask');self.assertEqual(started['completionTime'],1120);self.assertEqual(self.state['inventory']['77'],3)
  tasks.harvest(self.state,{'workAreaId':started['workAreaId'],'taskTypeId':20},1120);self.assertEqual(self.state['inventory']['103'],1)
 def test_unfinished_work_has_original_native_overlay_and_can_harvest_after_reload(self):
  source=next(v for v in self.state['world']['entities'] if v.get('refId')=='Strawberries');data={'villagerId':'steve','taskTypeId':14,'userMaterialSourceId':source['id'],'x':1500,'y':3550,'areaId':1}
  started,_=tasks.start(self.state,data,1000);reloaded=json.loads(json.dumps(self.state))
  overlay=world.area_content(reloaded,1,1010)['areaJson']['entities'];job=next(v for v in overlay if v['templateType']=='work_area')
  self.assertEqual(job['id'],started['workAreaId']);self.assertEqual(job['templateId'],11);self.assertEqual(job['status'],0)
  overlay=world.area_content(reloaded,1,1030)['areaJson']['entities'];self.assertEqual(next(v for v in overlay if v['templateType']=='work_area')['status'],1)
  tasks.harvest(reloaded,{'workAreaId':started['workAreaId'],'taskTypeId':14},1030);self.assertFalse(any(v['templateType']=='work_area' for v in world.area_content(reloaded,1,1040)['areaJson']['entities']))
 def test_fun_removal_is_saved_and_idempotent(self):
  progression.sync_inventory_assignments(self.saved);buildings.place(self.state,{'buildingTaskTypeId':'34','x':1950,'y':3050,'areaId':1})
  start,_=tasks.start(self.state,{'villagerId':'steve','taskTypeId':89,'x':1950,'y':3050,'areaId':1},1000,'ClientTaskService/StartBuildingTask')
  result,_=tasks.harvest(self.state,{'workAreaId':start['workAreaId'],'taskTypeId':89},1060);ident=result['objects'][0]['id']
  self.assertTrue(buildings.delete_fun(self.state,{'userFunBuildingTypeId':ident})[1]);self.assertEqual(self.state['inventory']['132'],0)
  before=copy.deepcopy(self.state);self.assertFalse(buildings.delete_fun(self.state,{'userFunBuildingTypeId':ident})[1]);self.assertEqual(before,self.state);world.validate_world(self.state)
 def test_invalid_foundation_coordinates_are_rejected(self):
  before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):buildings.place(self.state,{'buildingTaskTypeId':'34','x':float('nan'),'y':1,'areaId':1})
  self.assertEqual(self.state,before)

class SharedServiceIntegrationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patcher=patch.object(session,'STATE',Path(self.tmp.name));self.patcher.start()
  self.identity=session.login({'deviceId':'shared-core-test'})['data']['users'][0]
  self.call('ClientUserHashService/SetActiveSequence',{'activeSequence':217});self.call('ClientUserService/ProgressArea')
 def tearDown(self):self.patcher.stop();self.tmp.cleanup()
 def call(self,service,data=None,at=1000):
  request={k:self.identity[k] for k in ['deviceId','sessionId','pId']};request['data']={'calls':[{'id':'42','service':service,'data':data or {}}]}
  with patch.object(session,'wire_time',return_value=at):return session.process(request)['data']['calls'][0]
 def saved(self):return json.loads(next(Path(self.tmp.name).glob('*.tutorial.json')).read_text())
 def test_build_start_and_finish_are_committed_and_reloadable(self):
  self.call('ClientSettingService/SaveGameSetting',{'key':'activeSequenceId','value':'1613'})
  placement=self.call('ClientBuildingService/CreateUserBuildingTask',{'buildingTaskTypeId':'34','x':1950,'y':3050,'rotation':0,'areaId':1});self.assertEqual(placement['code'],200)
  response=self.call('ClientTaskService/StartBuildingTask',{'villagerId':'steve','taskTypeId':89,'x':1950,'y':3075,'areaId':1});self.assertEqual(response['code'],200)
  ident=response['data']['workAreaId'];self.assertIn(ident,self.saved()['normal']['workAreas'])
  overlay=self.call('ClientStartupService/GetAreaContent',{'areaId':1},1020)['data']['areaJson']['entities'];self.assertTrue(any(v['id']==ident for v in overlay))
  harvest=self.call('ClientTaskService/HarvestTask',{'workAreaId':ident,'taskTypeId':89},1060);self.assertEqual(harvest['code'],200)
  self.assertEqual(self.saved()['normal']['workAreas'][ident]['status'],'harvested');self.assertEqual(self.saved()['normal']['inventory']['82'],5)
 def test_purchase_receipt_survives_replay_but_new_login_has_new_call_namespace(self):
  saved=self.saved();saved['normal']['inventory']['323']=50;session.atomic_json(next(Path(self.tmp.name).glob('*.tutorial.json')),saved)
  data={'amount':10,'materialTypeId':444}
  self.assertEqual(self.call('ClientMaterialService/BuyMaterialType',data)['code'],200)
  self.call('ClientMaterialService/BuyMaterialType',data);self.assertEqual(self.saved()['normal']['inventory']['323'],40)
  self.identity=session.login({'deviceId':'shared-core-test'})['data']['users'][0]
  self.call('ClientMaterialService/BuyMaterialType',data);self.assertEqual(self.saved()['normal']['inventory']['323'],30)
 def test_commercial_offer_is_ignored_and_saved_without_rewards(self):
  before=self.saved()['normal']['inventory'];result=self.call('ClientUserBundleService/CreateUserBundle',{'bundleId':0})
  self.assertEqual(result['code'],200);self.assertEqual(result['data']['userBundles'][0]['ignore'],'true')
  self.assertEqual(self.saved()['normal']['inventory'],before)
  self.assertEqual(self.call('ClientUserBundleService/CreateUserBundle',{'bundleId':0})['data'],result['data'])
  self.assertEqual(len(self.saved()['normal']['bundles']),1)
 def test_complete_tutorial_uses_native_numeric_setting(self):
  result=self.call('ClientUser/CompleteTutorial');self.assertEqual(result['code'],200)
  self.assertEqual(self.saved()['gameSettings']['isFtueComplete'],'1')
  self.assertEqual(self.call('ClientUser/CompleteTutorial')['code'],200)
 def test_failed_start_cannot_partially_spend_saved_inventory(self):
  self.call('ClientBuildingService/CreateUserBuildingTask',{'buildingTaskTypeId':'34','x':1950,'y':3050,'areaId':1})
  before=self.saved();result=self.call('ClientTaskService/StartBuildingTask',{'villagerId':'steve','taskTypeId':89,'x':1950,'y':3075,'areaId':1})
  self.assertEqual(result['code'],400);self.assertEqual(self.saved(),before)
 def test_shared_gathering_supports_new_character_id_without_name_special_cases(self):
  saved=self.saved();actor=copy.deepcopy(next(v for v in saved['normal']['world']['entities'] if v['id']=='steve'));actor.update(id='future-villager-12345',refId='future-character',name='Future')
  saved['normal']['world']['entities'].append(actor);session.atomic_json(next(Path(self.tmp.name).glob('*.tutorial.json')),saved)
  source=next(v for v in saved['normal']['world']['entities'] if v.get('refId')=='Strawberries')
  result=self.call('ClientTaskService/StartGatheringTask',{'villagerId':actor['id'],'taskTypeId':14,'userMaterialSourceId':source['id'],'x':1500,'y':3550,'areaId':1})
  self.assertEqual(result['code'],200);self.assertEqual(result['data']['villager']['id'],actor['id'])
 def test_invalid_coordinates_return_error_without_server_exception(self):
  before=self.saved();result=self.call('ClientTaskService/StartCraftingTask',{'villagerId':'steve','taskTypeId':20,'x':'bad','y':3362,'areaId':1})
  self.assertEqual(result['code'],400);self.assertEqual(before,self.saved())
if __name__=='__main__':unittest.main()

