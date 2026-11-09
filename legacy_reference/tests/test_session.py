from contextlib import closing
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import session
class SessionTests(unittest.TestCase):
 def test_local_identity_survives_reload(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(session,'STATE',Path(tmp)):
   first=session.login({'deviceId':'test-device'})
   second=session.login({'deviceId':'test-device'})
   self.assertEqual(first,second)
   self.assertEqual(len(first['data']['users']),1)
 def test_batch_preserves_ids_and_rejects_unknown_gameplay(self):
  response=session.process({'data':{'calls':[{'id':'42','service':'ClientAnalyticsService/Install'},{'id':'43','service':'Unknown/GrantCurrency'}]}})
  self.assertEqual([(x['id'],x['code']) for x in response['data']['calls']],[('42',200),('43',501)])
 def test_original_tutorial_starter_records(self):
  value=session.fresh_tutorial()['userHash']
  self.assertEqual(value['activeSequence'],0)
  self.assertEqual(value['data']['villagers'][:2],[{'id':'steve','refId':'steve','name':'Harry','variationId':0},{'id':'jill','refId':'jill','name':'Chloe','variationId':4}])
class TutorialSaveTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.override=patch.object(session,'STATE',Path(self.temp.name));self.override.start()
  self.profile=session.login({'deviceId':'save-test'})['data']['users'][0]
 def tearDown(self):self.override.stop();self.temp.cleanup()
 def call(self,service,data=None,profile=None):
  p=profile or self.profile
  request={k:p[k] for k in ['deviceId','sessionId','pId']}
  request['data']={'calls':[{'id':'101','service':service,'data':data or {}}]}
  return session.process(request)['data']['calls'][0]
 def test_checkpoint_and_name_survive_disk_reload(self):
  self.assertEqual(self.call('ClientUserHashService/SetActiveSequence',{'activeSequence':154})['code'],200)
  self.assertEqual(self.call('ClientUserHashService/SetVillagerName',{'villagerId':'jill','name':'Test Chloe'})['code'],200)
  profile=session.login({'deviceId':'save-test'})['data']['users'][0]
  data=self.call('ClientUserHashService/GetUserHash',profile=profile)['data']['userHash']
  self.assertEqual(data['activeSequence'],154)
  self.assertEqual(next(v['name'] for v in data['data']['villagers'] if v['refId']=='jill'),'Test Chloe')
  self.assertFalse(list(Path(self.temp.name).glob('*.tmp')))
 def test_invalid_write_does_not_create_or_corrupt_save(self):
  for data in [{'activeSequence':999999},{'activeSequence':True}]:self.assertEqual(self.call('ClientUserHashService/SetActiveSequence',data)['code'],400)
  for data in [{'villagerId':'nobody','name':'Test'},{'villagerId':'jill','name':'a\nb'},{'villagerId':'jill','name':'a'*65}]:self.assertEqual(self.call('ClientUserHashService/SetVillagerName',data)['code'],400)
  self.assertEqual(self.call('ClientUserHashService/GetUserHash')['data']['userHash']['activeSequence'],0)
  self.assertFalse(list(Path(self.temp.name).glob('*.tutorial.json')))
 def test_profiles_are_isolated_and_session_mismatch_is_rejected(self):
  other=session.login({'deviceId':'second-test'})['data']['users'][0]
  self.call('ClientUserHashService/SetActiveSequence',{'activeSequence':154})
  self.assertEqual(self.call('ClientUserHashService/GetUserHash',profile=other)['data']['userHash']['activeSequence'],0)
  forged={**self.profile,'sessionId':other['sessionId']}
  self.assertEqual(self.call('ClientUserHashService/SetActiveSequence',{'activeSequence':0},profile=forged)['code'],403)

 def test_all_shipped_checkpoint_targets_are_accepted(self):
  import sqlite3,json
  with closing(sqlite3.connect('file:'+str(session.DATABASE)+'?mode=ro',uri=True)) as conn:
   values={int(json.loads(v[0])['persist']) for v in conn.execute("select fields_json from game_rows r join game_tables t on r.table_id=t.id where t.name='seq_state_tablet_ftue'")}
  for value in values-{0}:
   self.assertEqual(self.call('ClientUserHashService/SetActiveSequence',{'activeSequence':value})['code'],200,value)

 def test_reset_shelter_timer_returns_and_persists_expected_timestamp(self):
  value=self.call('ClientUserShelterService/ResetHappinessTimer',{'userShelterId':'UserShelter_1_2'})
  self.assertEqual(value['code'],200)
  stamp=value['data']['userShelter']['happinessCollectedAt']
  import json,time
  self.assertIsInstance(stamp,int)
  self.assertLess(abs(stamp-time.time()),5)
  saved=json.loads(next(Path(self.temp.name).glob('*.tutorial.json')).read_text())
  self.assertEqual(saved['shelters']['UserShelter_1_2']['happinessCollectedAt'],stamp)

 def test_wire_timestamps_are_epoch_seconds_for_native_decimal_parser(self):
  import time
  self.assertIsInstance(self.profile['createdAt'],int)
  response=session.process({'data':{'calls':[]}})
  self.assertIsInstance(response['currentTime'],int)
  self.assertLess(abs(response['currentTime']-time.time()),5)

 def test_legacy_saves_gain_unique_native_ids_without_losing_names(self):
  import json
  path=session.profile_path('save-test').with_suffix('.tutorial.json')
  old=session.fresh_tutorial()
  for villager in old['userHash']['data']['villagers']:villager.pop('id')
  old['userHash']['data']['villagers'][0]['name']='Saved Harry'
  session.atomic_json(path,{'version':1,**old})
  value=self.call('ClientUserHashService/GetUserHash')['data']['userHash']
  self.assertEqual([v['id'] for v in value['data']['villagers'][:2]],['steve','jill'])
  self.assertEqual(len({v['id'] for v in value['data']['villagers']}),6)
  self.assertEqual(value['data']['villagers'][0]['name'],'Saved Harry')
  self.assertEqual(json.loads(path.read_text())['version'],3)

 def test_all_original_tutorial_spawns_have_distinct_native_ids(self):
  value=session.fresh_tutorial()['userHash']['data']['villagers']
  self.assertEqual({v['id'] for v in value},{'steve','jill','brother','sister','baby male','baby female'})
  self.assertEqual(len(value),6)
 def test_older_parent_only_save_is_extended_without_resetting_progress(self):
  import json
  path=session.profile_path('save-test').with_suffix('.tutorial.json')
  old=session.fresh_tutorial();old['userHash']['activeSequence']=162;old['userHash']['data']['villagers']=old['userHash']['data']['villagers'][:2]
  session.atomic_json(path,{'version':2,**old})
  value=self.call('ClientUserHashService/GetUserHash')['data']['userHash']
  self.assertEqual(value['activeSequence'],162)
  self.assertEqual(len(value['data']['villagers']),6)

 def test_game_settings_round_trip_with_original_key_value_shape(self):
  self.assertEqual(self.call('ClientSettingService/GetUserGameSettings')['data'],{'gameSettings':[]})
  self.assertEqual(self.call('ClientSettingService/SaveGameSetting',{'key':'musicEnabled','value':'false'})['code'],200)
  self.assertEqual(self.call('ClientSettingService/GetUserGameSettings')['data'],{'gameSettings':[{'key':'musicEnabled','value':'false'}]})


 def test_shared_identity_guard_handles_arbitrary_future_characters(self):
  records=session.fresh_tutorial()['userHash']['data']['villagers']+[{'id':'future-villager-'+str(i)} for i in range(100)]
  session.validate_character_ids(records)
  with self.assertRaises(ValueError):session.validate_character_ids(records+[{'id':'future-villager-0'}])
  for record in [{},{'id':''},{'id':None}]:
   with self.assertRaises(ValueError):session.validate_character_ids(records+[record])

if __name__=='__main__':unittest.main()
