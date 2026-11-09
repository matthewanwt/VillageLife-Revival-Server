import unittest
import community
class CommunityEnvelopeTests(unittest.TestCase):
 def test_user_initialization_is_local_and_keeps_chat_disabled(self):
  user={'Id':123,'Name':'Test Village','XpLevel':3}
  calls=[{'Id:':1,'Service':'User/Get','Data':{}},{'Id:':2,'Service':'ApplicationSetting/Get','Data':{}}]
  values=community.process({'Calls':calls},user)['data'];self.assertEqual(values[0]['Data']['User']['Id'],123);self.assertIn({'Key':'ChatEnabled','Value':'0'},values[1]['Data']['ApplicationSettings'])
 def test_empty_local_inbox_and_rankings_have_the_original_array_names(self):
  for name,fields in [('UserMessage/GetInbox',['UserMessages','FriendshipRequests']),('CharacterRequest/GetReceived',['CharacterRequests']),('MaterialRequest/GetReceived',['MaterialRequests']),('Friendship/GetByUser',['Users','Friendships']),('Group/GetTop',['Groups']),('User/GetTop',['Users','Groups'])]:
   value=community.process({'Calls':[{'Id:':1,'Service':name}]})['data'][0];self.assertEqual(value['code'],200)
   for field in fields:self.assertEqual(value['Data'][field],[])
 def test_mutations_require_server_selected_profile_callback_and_preserve_denial(self):
  request={'Calls':[{'Id:':1,'Service':'CharacterRequest/Create','Data':{}}]}
  self.assertEqual(community.process(request)['data'][0]['code'],501)
  def deny(*args):raise PermissionError('Wrong owner')
  self.assertEqual(community.process(request,relationship_operation=deny)['data'][0]['code'],403)
  self.assertEqual(community.process(request,relationship_operation=lambda service,data:{'proof':'bound'})['data'][0]['Data'],{'proof':'bound'})
if __name__=='__main__':unittest.main()
