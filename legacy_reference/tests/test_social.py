import unittest,tempfile,json,copy
from pathlib import Path
from unittest.mock import patch
import session,social,world
class SocialTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name);self.scope=patch.object(session,'STATE',self.directory);self.scope.start()
  self.players=[]
  for name in ['Alice','Bob','Carol']:
   profile=session.login({'deviceId':'social-'+name})['data']['users'][0];saved=session.fresh_tutorial();saved['normal']=world.build_bridge_world(saved,1000);saved['normal']['user']['name']=name
   session.atomic_json(session.profile_path(profile['deviceId']).with_suffix('.tutorial.json'),saved);self.players.append(profile)
 def tearDown(self):self.scope.stop();self.tmp.cleanup()
 def call(self,who,service,data=None):return session.process({**self.players[who],'data':{'calls':[{'id':'1','service':service,'data':data or {}}]}})['data']['calls'][0]
 def test_native_friend_projection_and_bilateral_link_survive_reopen(self):
  a,b=map(social.public_id,self.players[:2]);social.link(self.directory,a,b);social.link(self.directory,a,b)
  for who,target in [(0,b),(1,a)]:
   response=self.call(who,'ClientFriendService/GetApplicationFriends');self.assertEqual(response['code'],200);self.assertEqual([r['identifier']['pId'] for r in response['data']['friends']],[target])
  self.assertEqual(social.friend_ids(self.directory,a),[b])
 def test_unlinked_players_cannot_read_villages(self):
  self.assertEqual(self.call(0,'ClientFriendService/GetFriendStartupInfo',{'friendUserId':social.public_id(self.players[1])})['code'],403)
 def test_visit_is_read_only_and_never_exposes_credentials_inventory_or_receipts(self):
  a,b=map(social.public_id,self.players[:2]);social.link(self.directory,a,b)
  target=session.profile_path(self.players[1]['deviceId']).with_suffix('.tutorial.json');before=target.read_bytes()
  response=self.call(0,'ClientFriendService/GetFriendStartupInfo',{'friendUserId':b});self.assertEqual(response['code'],200)
  text=json.dumps(response['data']);self.assertNotIn('sessionId',text);self.assertNotIn('deviceId',text);self.assertNotIn('inventory',response['data']);self.assertIn('areaJson',response['data']);self.assertEqual(target.read_bytes(),before)
 def test_removing_link_revokes_visits_and_invalid_session_is_rejected(self):
  a,b=map(social.public_id,self.players[:2]);social.link(self.directory,a,b);social.link(self.directory,a,b,remove=True)
  self.assertEqual(self.call(0,'ClientFriendService/GetFriendStartupInfo',{'friendUserId':b})['code'],403)
  self.players[0]['sessionId']='wrong';self.assertEqual(self.call(0,'ClientFriendService/GetFriends')['code'],403)
 def test_legacy_single_digit_id_has_stable_native_compatible_public_id(self):
  profile={**self.players[0],'pId':'1'};first=social.public_id(profile);self.assertGreater(len(first),1);self.assertEqual(first,social.public_id(profile))
if __name__=='__main__':unittest.main()
