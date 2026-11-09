"""Persistent normal-world contract and state invariants."""
import unittest,tempfile,json,copy
from pathlib import Path
from unittest.mock import patch
import session,world
class WorldTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patcher=patch.object(session,'STATE',Path(self.tmp.name));self.patcher.start()
  self.identity=session.login({'deviceId':'normal-test'})['data']['users'][0]
 def tearDown(self):self.patcher.stop();self.tmp.cleanup()
 def call(self,name,payload=None):
  request={k:self.identity[k] for k in ['deviceId','sessionId','pId']};request['data']={'calls':[{'id':'42','service':name,'data':payload or {}}]}
  return session.process(request)['data']['calls'][0]
 def transition(self):
  self.assertEqual(self.call('ClientUserHashService/SetActiveSequence',{'activeSequence':217})['code'],200)
  self.assertEqual(self.call('ClientUserService/ProgressArea')['code'],200)
 def saved(self):return json.loads(next(Path(self.tmp.name).glob('*.tutorial.json')).read_text(encoding='utf8'))
 def test_transition_requires_bridge_and_does_not_partially_create_world(self):
  self.assertEqual(self.call('ClientUserService/ProgressArea')['code'],400)
  self.assertFalse(list(Path(self.tmp.name).glob('*.tutorial.json')))
 def test_transition_is_idempotent_and_preserves_all_six_ids(self):
  self.transition();before=self.saved()
  self.assertEqual(self.call('ClientUserService/ProgressArea')['code'],200)
  self.assertEqual(self.saved(),before)
  self.assertEqual(before['userHash']['activeSequence'],217)
  expected={v['id'] for v in before['userHash']['data']['villagers']}
  self.assertEqual({v['id'] for v in before['normal']['world']['entities'] if v['templateType']=='villager_type'},expected)
 def test_login_projects_persisted_world_without_rotating_session(self):
  self.transition();profile=session.login({'deviceId':'normal-test'})['data']['users'][0]
  self.assertEqual(profile['scenarioId'],2);self.assertFalse(profile['isNewUser']);self.assertEqual(profile['sessionId'],self.identity['sessionId'])
 def test_original_scene_and_spawn_data_are_used(self):
  self.transition();value=self.saved()['normal'];self.assertEqual(value['areaName'],'Woodland');self.assertEqual(len(value['world']['entities']),264)
  actor=next(v for v in value['world']['entities'] if v['id']=='steve')
  self.assertEqual(actor['position'],{'x':1539,'y':3127,'areaId':1,'rotation':0})
  self.assertEqual(value['rules']['initial_inventory']['status'],'inferred')
 def test_startup_projection_is_read_only_and_preserves_world_first(self):
  self.transition();before=self.saved();data=self.call('ClientStartupService/GetStartupInfo')['data']
  self.assertEqual(next(iter(data)),'world');self.assertEqual(data['user']['populationCap'],20)
  self.assertEqual(self.saved(),before)
 def test_name_change_reaches_saved_normal_actor(self):
  self.transition();self.assertEqual(self.call('ClientUserHashService/SetVillagerName',{'villagerId':'brother','name':'Saved Name'})['code'],200)
  data=self.call('ClientStartupService/GetStartupInfo')['data'];self.assertEqual(next(x['name'] for x in data['world']['entities'] if x['id']=='brother'),'Saved Name')
 def test_duplicate_ids_and_dangling_family_links_are_rejected(self):
  self.transition();value=self.saved()['normal'];bad=copy.deepcopy(value);bad['world']['entities'].append(copy.deepcopy(bad['world']['entities'][0]))
  with self.assertRaises(ValueError):world.validate_world(bad)
  bad=copy.deepcopy(value);actor=next(x for x in bad['world']['entities'] if x['templateType']=='villager_type');actor['relations'].append({'villagerId':'missing','type':0})
  with self.assertRaises(ValueError):world.validate_world(bad)
 def test_epoch_age_uses_original_twenty_four_hour_year(self):
  self.transition();actor=next(x for x in self.saved()['normal']['world']['entities'] if x['id']=='brother')
  self.assertAlmostEqual(world.current_age(actor,actor['bornAt']+86400),actor['startAge']+1)
 def test_local_inbox_and_wants_are_empty_until_events_exist(self):
  self.transition();before=self.saved()
  for service,key in [('ClientUserService/GetUserNotifications','userNotifications'),('ClientRequestService/GetPaginatedSentRequests','userRequests'),('ClientRequestService/GetPaginatedReceivedRequests','userRequests'),('ClientWant/AllWants','result')]:
   value=self.call(service,{'count':500});self.assertEqual(value['code'],200);self.assertEqual(value['data'],{key:[]})
  self.assertEqual(self.saved(),before)
 def test_request_page_size_is_bounded(self):
  self.transition();self.assertEqual(self.call('ClientRequestService/GetPaginatedSentRequests',{'count':-1})['code'],400)
 def test_area_overlay_contains_saved_characters_without_static_duplicates(self):
  self.transition();before=self.saved();value=self.call('ClientStartupService/GetAreaContent',{'areaId':1})
  self.assertEqual(value['code'],200);actors=value['data']['areaJson']['entities'];self.assertEqual(len(actors),68)
  self.assertEqual(sum(v['templateType']=='villager_type' for v in actors),6);self.assertEqual(self.saved(),before)
  for invalid in [True,2,'1',None]:self.assertEqual(self.call('ClientStartupService/GetAreaContent',{'areaId':invalid})['code'],400)
 def test_later_progression_does_not_reuse_first_bridge_success(self):
  self.transition();self.call('ClientSettingService/SaveGameSetting',{'key':'activeSequenceId','value':'500'})
  before=self.saved();self.assertEqual(self.call('ClientUserService/ProgressArea')['code'],400);self.assertEqual(self.saved(),before)
 def test_native_wire_level_uses_level_number_not_row_zero(self):
  self.transition();value=self.call('ClientStartupService/GetStartupInfo')['data']['user']
  self.assertEqual(value['userLevel'],1);self.assertEqual(value['userLevelID'],1)
  self.assertEqual(session.login({'deviceId':'normal-test'})['data']['users'][0]['userLevelId'],1)
 def test_legacy_level_migration_preserves_checkpoint_names_and_inventory(self):
  self.transition();before=self.saved();legacy=copy.deepcopy(before);legacy['normal']['schemaVersion']=1
  legacy['normal']['user'].update(userLevel=0,userLevelID=0)
  path=next(Path(self.tmp.name).glob('*.tutorial.json'));session.atomic_json(path,legacy)
  self.call('ClientStartupService/GetStartupInfo');after=self.saved()
  self.assertEqual(after['normal']['user']['userLevelID'],1);self.assertEqual(after['userHash'],before['userHash'])
  self.assertEqual(after['normal']['inventory'],before['normal']['inventory']);self.assertEqual(after['normal']['world'],before['normal']['world'])
  again=self.saved();self.call('ClientStartupService/GetStartupInfo');self.assertEqual(self.saved(),again)
 def test_authored_resources_and_required_child_survive_reload_without_duplicates(self):
  self.transition();state=self.saved()['normal'];overlay=world.area_content(state,1)['areaJson']['entities']
  self.assertEqual(sum(x['templateType']=='material_source' for x in overlay),28)
  self.assertEqual(sum(x['templateType']=='shelter' for x in overlay),8)
  self.assertEqual(len({v['id'] for v in overlay}),len(overlay))
  self.assertTrue(any(x.get('refId')=='Strawberries' for x in overlay))
  sister=next(x for x in overlay if x.get('refId')=='sister');self.assertEqual(sister['templateId'],11);self.assertEqual(sister['startAge'],12);self.assertEqual(sister['name'],'Mia')
  members={int(v['villagerType']) for v in world.rows('villager_set_item') if v['villagerSet']=='21'}
  self.assertTrue(any(x['templateType']=='villager_type' and x['templateId'] in members for x in overlay))
  state['schemaVersion']=2;state['world']['entities']=[v for v in state['world']['entities'] if v['templateType']=='villager_type' or not v.get('serverPersisted')]
  self.assertTrue(world.migrate_authored_area(state));self.assertEqual(len(state['world']['entities']),264);self.assertFalse(world.migrate_authored_area(state))
 def test_authored_overlay_uses_native_mode_two_creation_path_without_mutating_save(self):
  self.transition();before=self.saved();overlay=world.area_content(before['normal'],1)['areaJson']['entities']
  self.assertTrue(all(not e['serverPersisted'] for e in overlay if e['templateType']!='villager_type'))
  self.assertTrue(all(e['serverPersisted'] for e in overlay if e['templateType']=='villager_type'))
  self.assertTrue(all(e['serverPersisted'] for e in before['normal']['world']['entities'] if e['templateType']=='material_source'))
  self.assertEqual(self.saved(),before)
 def test_native_checkpoint_aliases_cannot_restore_stale_bridge_value(self):
  self.transition();self.call('ClientSettingService/SaveGameSetting',{'key':'activeSequenceId','value':'1380'})
  saved=self.saved();saved['gameSettings']['activeSequence']='410';path=next(Path(self.tmp.name).glob('*.tutorial.json'));session.atomic_json(path,saved)
  settings={v['key']:v['value'] for v in self.call('ClientSettingService/GetUserGameSettings')['data']['gameSettings']}
  self.assertEqual(settings['activeSequenceId'],'1380');self.assertEqual(settings['activeSequence'],'1380')
 def test_unknown_mutation_cannot_grant_inventory(self):
  self.transition();before=self.saved();self.assertEqual(self.call('Unknown/GiveGold',{'amount':1000000})['code'],501);self.assertEqual(self.saved(),before)
if __name__=='__main__':unittest.main()
