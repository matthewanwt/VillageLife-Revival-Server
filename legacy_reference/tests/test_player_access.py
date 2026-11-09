import tempfile,unittest,json,threading,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
import player_access,server,session
from codec import encode,decode
class HostedAccessTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.scope=patch.object(session,'STATE',self.root/'state');self.scope.start()
  self.access=self.root/'player-access.json';self.a,self.account_a=player_access.provision(self.access,'Alice');self.b,self.account_b=player_access.provision(self.access,'Bob')
  self.srv=server.Server(('127.0.0.1',0),server.Handler);self.srv.log=self.root/'traffic.jsonl';self.srv.log_lock=threading.Lock();self.srv.summary_logs=True;self.srv.access_file=self.access
  self.worker=threading.Thread(target=self.srv.serve_forever,daemon=True);self.worker.start()
 def tearDown(self):self.srv.shutdown();self.srv.server_close();self.worker.join(5);self.scope.stop();self.tmp.cleanup()
 def request(self,path,document=None,key=None):
  headers={'Authorization':'Bearer '+key} if key else {}
  request=urllib.request.Request('http://127.0.0.1:'+str(self.srv.server_port)+path,data=encode(document) if document is not None else None,headers=headers)
  try:
   with urllib.request.urlopen(request,timeout=5) as response:
    raw=response.read();return decode(raw)[0] if document is not None else raw
  except urllib.error.HTTPError as error:error.close();raise
 def test_missing_and_revoked_invites_fail_closed_even_for_health(self):
  with self.assertRaises(urllib.error.HTTPError) as missing:self.request('/health')
  self.assertEqual(missing.exception.code,403);self.assertIn(b'local-village',self.request('/health',key=self.a))
  self.access.write_text(json.dumps({'version':1,'accounts':{}}))
  with self.assertRaises(urllib.error.HTTPError):self.request('/health',key=self.a)
 def test_account_binding_ignores_forged_device_and_rejects_other_session(self):
  alice=self.request('/web/ClientService/Login',{'deviceId':'forged-device'},self.a)['data']['users'][0]
  bob=self.request('/web/ClientService/Login',{'deviceId':'forged-device'},self.b)['data']['users'][0]
  self.assertNotEqual(alice['pId'],bob['pId']);self.assertEqual(alice['deviceId'],self.account_a['deviceId'])
  data={**bob,'data':{'calls':[{'id':'1','service':'ClientUser/KeepActive','data':{}}]}}
  response=self.request('/web/ClientService/Process',data,self.a);self.assertEqual(response['data']['calls'][0]['code'],403)
  self.assertNotIn(self.a,self.srv.log.read_text());self.assertNotIn(self.b,self.srv.log.read_text())
 def test_community_uses_bound_identity_without_rotating_request_epoch(self):
  profile=self.request('/web/ClientService/Login',{'deviceId':'native-device'},self.a)['data']['users'][0]
  path=session.profile_path(self.account_a['deviceId']).with_suffix('.tutorial.json');session.atomic_json(path,{'requestEpoch':'keep-this'})
  result=self.request('/Playdemic.Community.Web/Client/Home',{'UserId':0,'Calls':[{'Id:':1,'Service':'ApplicationSetting/Get','Data':{}}]},self.a)
  self.assertEqual(result['data'][0]['Data']['User']['Name'],'Alice');self.assertEqual(json.loads(path.read_text())['requestEpoch'],'keep-this')
  with self.assertRaises(urllib.error.HTTPError):self.request('/Playdemic.Community.Web/Client/Home',{'UserId':999999,'Calls':[{'Id:':1,'Service':'ApplicationSetting/Get','Data':{}}]},self.a)
 def test_new_hosted_login_revokes_the_previous_session(self):
  first=self.request('/web/ClientService/Login',{'deviceId':'native-device'},self.a)['data']['users'][0]
  second=self.request('/web/ClientService/Login',{'deviceId':'native-device'},self.a)['data']['users'][0]
  self.assertNotEqual(first['sessionId'],second['sessionId'])
  request={**first,'data':{'calls':[{'id':'1','service':'ClientUser/KeepActive','data':{}}]}}
  self.assertEqual(self.request('/web/ClientService/Process',request,self.a)['data']['calls'][0]['code'],403)
if __name__=='__main__':unittest.main()
