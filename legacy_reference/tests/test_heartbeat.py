import tempfile,unittest,json,copy
from pathlib import Path
from unittest.mock import patch
import session
class HeartbeatTests(unittest.TestCase):
 def test_periodic_heartbeat_keeps_session_and_progress_without_rewards(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(session,'STATE',Path(folder)):
   identity=session.login({'deviceId':'heartbeat-test'})['data']['users'][0]
   request={**identity,'data':{'calls':[{'id':'98','service':'ClientUser/KeepActive','data':{}}]}}
   with patch.object(session,'wire_time',return_value=1000):first=session.process(request)
   path=session.profile_path('heartbeat-test').with_suffix('.tutorial.json');before=json.loads(path.read_text())
   for at in [1300,1600,1900]:
    with patch.object(session,'wire_time',return_value=at):result=session.process(request)
    self.assertEqual(result['data']['calls'][0]['code'],200)
   after=json.loads(path.read_text());self.assertEqual(after.pop('lastActiveAt'),1900);before.pop('lastActiveAt');self.assertEqual(before,after)
   self.assertEqual(session.login({'deviceId':'heartbeat-test'})['data']['users'][0]['sessionId'],identity['sessionId'])
 def test_invalid_session_cannot_heartbeat(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(session,'STATE',Path(folder)):
   identity=session.login({'deviceId':'heartbeat-test'})['data']['users'][0]
   request={**identity,'sessionId':'wrong','data':{'calls':[{'id':'1','service':'ClientUser/KeepActive','data':{}}]}}
   self.assertEqual(session.process(request)['data']['calls'][0]['code'],403)
if __name__=='__main__':unittest.main()
