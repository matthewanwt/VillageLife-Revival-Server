import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import session
class HostedIsolationTests(unittest.TestCase):
 def test_two_players_keep_separate_settings_and_cannot_cross_session(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(session,'STATE',Path(directory)):
   alice=session.login({'deviceId':'hosted-alice'})['data']['users'][0]
   bob=session.login({'deviceId':'hosted-bob'})['data']['users'][0]
   self.assertNotEqual(alice['pId'],bob['pId'])
   def call(profile,service,data):
    return session.process({**profile,'data':{'calls':[{'id':'1','service':service,'data':data}]}})['data']['calls'][0]
   call(alice,'ClientSettingService/SaveGameSetting',{'key':'test-setting','value':'alice'})
   self.assertEqual(call(bob,'ClientSettingService/GetUserGameSettings',{})['data']['gameSettings'],[])
   self.assertEqual(call({**bob,'sessionId':alice['sessionId']},'ClientSettingService/GetUserGameSettings',{})['code'],403)
 def test_legacy_identity_is_preserved(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(session,'STATE',Path(directory)):
   profile=session.login({'deviceId':'legacy-test'})['data']['users'][0];profile['pId']='1'
   session.atomic_json(session.profile_path('legacy-test'),profile)
   self.assertEqual(session.login({'deviceId':'legacy-test'})['data']['users'][0]['pId'],'1')
if __name__=='__main__':unittest.main()
