import copy,json,unittest
import family,marriage,relationships as rel,session,world

class MarriageTests(unittest.TestCase):
 def setUp(self):
  self.state=world.build_bridge_world(session.fresh_tutorial(),1000);self.owner='42'
  self.person=family.actor(self.state,'steve');self.person.update(startAge=25,bornAt=1000,relations=[],communityOptIn=True)
  family.actor(self.state,'jill')['relations']=[r for r in family.actor(self.state,'jill')['relations'] if r['villagerId']!='steve' or int(r['type'])!=2]
  rel.catalogue(self.state,{'Gender':1},1000,self.owner);self.target=next(p for p in self.state['npcDatingPool'] if p['gender']==1)
  import native_identity
  raw=next(k for k,v in native_identity.mappings(self.state,self.owner)[2].items() if v=='steve')
  rel.community(self.state,'CharacterRequest/Create',{'ForUserIds':[int(self.target['ownerUserId'])],'CharacterIds':[int(self.target['id'].split('_')[-1])],'FriendCharacterId':int(raw)},1000,self.owner)
  rel.accept_date(self.state,{'RequestID':self.state['npcDateRequests'][0]['id']},1020)
  self.data={'senderVillagerId':'steve','recipientUserId':self.target['ownerUserId'],'recipientVillagerId':self.target['id'],'stars':'0'}
 def test_marriage_wish_uses_original_material_category_and_delay(self):
  self.assertFalse(any(w['VillagerStringID']=='steve' for w in rel.generate(self.state,1021)[0]['result']));delay=int(world.global_value('marriage_want_delay'))
  self.state['npcDateRequests'][0]['acceptedAt']=1020-delay
  self.state['relationshipWantSatisfiedAt']['steve']=1020-int(world.global_value('marriageWantRefreshDelay'))
  result,changed=rel.generate(self.state,1021);self.assertTrue(changed)
  wish=next(w for w in result['result'] if w['VillagerStringID']=='steve');self.assertEqual((wish['MaterialID'],wish['wantableCategoryType']),(342,5))
 def proposal(self):
  response,changed=marriage.operate(self.state,'ClientRequestService/SendMarriageRequest',self.data,1021,self.owner);self.assertTrue(changed)
  self.request={'RequestID':int(response['userRequest']['userRequestId']),'RequestStringID':response['userRequest']['userRequestId']};return response
 def test_proposal_delayed_acceptance_and_retry_do_not_add_a_villager(self):
  count=family.population(self.state);response=self.proposal();self.assertEqual(response['userRequest']['requestStatusTypeId'],0)
  before=copy.deepcopy(self.state);again,changed=marriage.operate(self.state,'ClientRequestService/SendMarriageRequest',self.data,1041,self.owner);self.assertFalse(changed);self.assertEqual(before,self.state);self.assertEqual(again['userRequest']['requestStatusTypeId'],1)
  self.assertEqual(family.population(self.state),count);world.validate_world(self.state)
 def test_prepare_has_original_case_sensitive_actor_and_host_fields(self):
  self.proposal();count=family.population(self.state)
  response,changed=marriage.operate(self.state,'ClientRelationship/PrepareWedding',self.request,1041,self.owner);self.assertTrue(changed)
  self.assertEqual(set(response['result']['Bride']),{'Name','VillagerType','IsPregnant','Xp','Equipment'})
  self.assertEqual(response['result']['IsUserHost'],'true');self.assertEqual(response['result']['Bride']['Name'],self.target['name']);self.assertEqual(response['data']['users']['host']['id'],self.owner)
  before=copy.deepcopy(self.state);self.assertFalse(marriage.prepare(self.state,self.request,1042,self.owner)[1]);self.assertEqual(before,self.state);self.assertEqual(family.population(self.state),count)
 def test_completion_moves_one_partner_and_survives_retry_reload_and_family_reads(self):
  self.person['familyBirthId']='must-not-transfer';self.person['communityOptIn']=True
  self.proposal();marriage.prepare(self.state,self.request,1041,self.owner);count=family.population(self.state);target=copy.deepcopy(self.target)
  marriage.operate(self.state,'ClientNotification/ProcessAcceptedProposal',self.request,1042,self.owner)
  self.assertEqual(family.population(self.state),count+1);moved=family.actor(self.state,target['id']);self.assertEqual(moved['equipment'],target['equipment']);self.assertEqual(moved['genetics'],target['genetics']);self.assertEqual(moved['bornAt'],target['bornAt']);self.assertEqual(moved['ownerUserId'],self.owner);self.assertNotIn('familyBirthId',moved);self.assertNotIn('communityOptIn',moved)
  self.assertEqual(family.spouse(self.state,self.person)['id'],moved['id']);self.assertNotIn(moved['id'],self.state['externalVillagers']);self.assertNotIn(moved['id'],[p['id'] for p in self.state['npcDatingPool']]);world.validate_world(self.state)
  saved=json.loads(json.dumps(self.state));before=copy.deepcopy(saved);self.assertFalse(marriage.operate(saved,'ClientNotification/ProcessAcceptedProposal',self.request,1043,self.owner)[1]);self.assertEqual(before,saved)
  family.history(saved,{'userId':self.owner},1043,self.owner);world.startup(saved,1043)
 def test_higher_star_local_villager_can_invite_lower_star_npc(self):
  self.person['rarity']=3;self.data['stars']='3'
  response,changed=marriage.propose(self.state,self.data,1021,self.owner);self.assertTrue(changed)
  request={'userRequestId':str(response['userRequest']['id'])}
  marriage.prepare(self.state,request,1042,self.owner);marriage.complete(self.state,request,1042,self.owner)
  moved=family.actor(self.state,self.target['id']);self.assertEqual(moved['rarity'],0)
  self.assertIn({'villagerId':moved['id'],'type':2},self.person['relations']);world.validate_world(self.state)
 def test_forged_human_owner_wrong_partner_and_unsupported_stars_do_not_mutate(self):
  for changes in [{'recipientUserId':'99'},{'recipientVillagerId':'Villager_99_1'},{'stars':5},{'senderVillagerId':'not-owned'}]:
   before=copy.deepcopy(self.state)
   with self.assertRaises((ValueError,PermissionError)):marriage.propose(self.state,{**self.data,**changes},1021,self.owner)
   self.assertEqual(before,self.state)
 def test_early_prepare_unknown_mismatched_id_and_unprepared_commit_are_rejected(self):
  self.proposal()
  for data,at in [(self.request,1022),({'RequestID':123},1041),({**self.request,'RequestStringID':'wrong'},1041)]:
   before=copy.deepcopy(self.state)
   with self.assertRaises((ValueError,PermissionError)):marriage.prepare(self.state,data,at,self.owner)
   self.assertEqual(before,self.state)
  with self.assertRaises(ValueError):marriage.complete(self.state,self.request,1041,self.owner)
 def test_population_is_checked_again_at_commit(self):
  self.proposal();marriage.prepare(self.state,self.request,1041,self.owner);self.state['user']['populationCap']=family.population(self.state);before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):marriage.complete(self.state,self.request,1042,self.owner)
  self.assertEqual(before,self.state)
 def test_stale_relationship_blocks_wedding(self):
  self.proposal();rel.breakup(self.state,{'villagerId':'steve','partnerVillagerId':self.target['id']},1022);before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):marriage.prepare(self.state,self.request,1041,self.owner)
  self.assertEqual(before,self.state);self.assertEqual(self.state['npcMarriageRequests'][0]['status'],'cancelled')
 def test_age_bounds_and_female_owned_pair_are_supported_without_rejuvenating_partner(self):
  original=copy.deepcopy(self.state)
  for age in [17,56]:
   self.state=copy.deepcopy(original);family.actor(self.state,'steve')['startAge']=age;before=copy.deepcopy(self.state)
   with self.assertRaises(ValueError):marriage.propose(self.state,self.data,1021,self.owner)
   self.assertEqual(before,self.state)
  self.state=copy.deepcopy(original);person=family.actor(self.state,'steve');person.update(gender=1,templateId=5)
  target=rel.npc(self.state,self.target['id']);target.update(gender=0,templateId=1,startAge=40)
  self.state['externalVillagers'][target['id']]=copy.deepcopy(target)
  proposal,_=marriage.propose(self.state,self.data,1021,self.owner);request={'RequestID':proposal['userRequest']['id']}
  response,_=marriage.prepare(self.state,request,1041,self.owner);self.assertEqual(response['result']['IsUserBride'],'true')
  marriage.complete(self.state,request,1042,self.owner);moved=family.actor(self.state,target['id']);self.assertEqual(moved['startAge'],40);self.assertEqual(moved['templateId'],int(world.current_villager_type(target,1042)['id']));world.validate_world(self.state)
 def test_accepted_notification_is_original_type12_and_acknowledgement_is_owned_and_repeatable(self):
  self.proposal();self.assertEqual(marriage.notifications(self.state,1040,self.owner),[])
  item=marriage.notifications(self.state,1041,self.owner)[0];self.assertEqual(item['notificationTypeId'],12);self.assertEqual(item['data']['requestStatusTypeId'],1);self.assertEqual(item['data']['userRequestId'],self.request['RequestStringID'])
  before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):marriage.operate(self.state,'ClientUserService/HandleUserNotification',{'userNotificationId':'999'},1042,self.owner)
  self.assertEqual(before,self.state)
  self.assertTrue(marriage.operate(self.state,'ClientUserService/HandleUserNotification',{'userNotificationId':item['id']},1042,self.owner)[1]);self.assertFalse(marriage.operate(self.state,'ClientUserService/HandleUserNotification',{'userNotificationId':item['id']},1043,self.owner)[1]);self.assertEqual(marriage.notifications(self.state,1043,self.owner),[])
 def test_async_message_has_native_envelope_and_ack_does_not_consume_wedding_notification(self):
  self.proposal();self.assertEqual(marriage.messages(self.state,1040,self.owner),[])
  item=marriage.messages(self.state,1041,self.owner)[0];self.assertEqual(item['messageTypeId'],7);self.assertEqual(item['data']['notificationTypeId'],12);self.assertEqual(item['data']['data']['userRequestId'],self.request['RequestStringID'])
  before=copy.deepcopy(self.state)
  with self.assertRaises(PermissionError):marriage.operate(self.state,'ClientUserService/HandleUserMessages',{'userMessageIds':item['id']+',wrong'},1042,self.owner)
  self.assertEqual(before,self.state)
  self.assertTrue(marriage.operate(self.state,'ClientUserService/HandleUserMessages',{'userMessageIds':item['id']},1042,self.owner)[1]);self.assertFalse(marriage.operate(self.state,'ClientUserService/HandleUserMessages',{'userMessageIds':item['id']},1043,self.owner)[1])
  self.assertEqual(marriage.messages(self.state,1043,self.owner),[]);self.assertEqual(len(marriage.notifications(self.state,1043,self.owner)),1)
 def test_pagination_and_hiding_preserve_replay_history(self):
  self.proposal();response,_=marriage.operate(self.state,'ClientRequestService/GetPaginatedSentRequests',{'count':500},1041,self.owner);self.assertEqual(response['userRequests'][0]['requestTypeId'],1);self.assertEqual(response['userRequests'][0]['requestStatusTypeId'],1)
  marriage.operate(self.state,'ClientRequestService/DeleteUserRequests',{'userRequestIds':self.request['RequestStringID']},1042,self.owner)
  self.assertEqual(marriage.operate(self.state,'ClientRequestService/GetPaginatedSentRequests',{},1043,self.owner)[0],{'userRequests':[]});self.assertEqual(len(self.state['npcMarriageRequests']),1)
class NativeMarriageIntegrationTests(unittest.TestCase):
 setUp=MarriageTests.setUp
 def test_authenticated_background_message_translates_owned_ids_and_is_not_leaked(self):
  import tempfile,native_identity
  from pathlib import Path
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as folder,patch.object(session,'STATE',Path(folder)):
   profile=session.login({'deviceId':'marriage-message'})['data']['users'][0];self.owner=profile['pId']
   marriage.propose(self.state,self.data,1021,self.owner)
   path=session.profile_path('marriage-message').with_suffix('.tutorial.json');session.atomic_json(path,{**session.fresh_tutorial(),'normal':self.state})
   request={**profile,'data':{'calls':[{'id':'1','service':'ClientUser/KeepActive','data':{}}]}}
   with patch.object(session,'wire_time',return_value=1041):
    result=session.process(request,native_ids=True);self.assertEqual(len(result['messages']),1)
    message=result['messages'][0];self.assertEqual(message['data']['data']['sender']['villager']['id'],native_identity.mappings(self.state,self.owner)[0]['steve'])
    denied=session.process({**request,'sessionId':'wrong'},native_ids=True);self.assertEqual(denied['messages'],[]);self.assertEqual(denied['data']['calls'][0]['code'],403)
    ack={**profile,'data':{'calls':[{'id':'2','service':'ClientUserService/HandleUserMessages','data':{'userMessageIds':message['id']}}]}}
    response=session.process(ack,native_ids=True);self.assertEqual(response['data']['calls'][0]['code'],200);self.assertEqual(response['messages'],[])
 def test_native_proposal_wedding_move_in_reload_name_and_shelter(self):
  import tempfile,native_identity,habitats
  from pathlib import Path
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as folder,patch.object(session,'STATE',Path(folder)):
   profile=session.login({'deviceId':'marriage-integration'})['data']['users'][0];self.owner=profile['pId']
   path=session.profile_path('marriage-integration').with_suffix('.tutorial.json');session.atomic_json(path,{**session.fresh_tutorial(),'normal':self.state})
   def call(service,data,at):
    with patch.object(session,'wire_time',return_value=at):
     result=session.process({**profile,'data':{'calls':[{'id':str(at)+service,'service':service,'data':data}]}},native_ids=True)['data']['calls'][0]
    self.assertEqual(result['code'],200,result);return result['data']
   outward=native_identity.mappings(self.state,self.owner)[0]
   proposal=call('ClientRequestService/SendMarriageRequest',{**self.data,'senderVillagerId':outward['steve']},1021)
   request={'RequestID':proposal['userRequest']['id'],'RequestStringID':proposal['userRequest']['userRequestId']}
   call('ClientRelationship/PrepareWedding',request,1041)
   call('ClientNotification/ProcessAcceptedProposal',request,1042)
   saved=json.loads(path.read_text(encoding='utf-8'))['normal'];count=family.population(saved)
   call('ClientNotification/ProcessAcceptedProposal',request,1043)
   session.login({'deviceId':'marriage-integration'})
   saved=json.loads(path.read_text(encoding='utf-8'))['normal'];self.assertEqual(family.population(saved),count)
   ids=native_identity.mappings(saved,self.owner)[0];moved_id=ids[self.target['id']]
   startup=call('ClientStartupService/GetStartupInfo',{},1044);people={p['id']:p for p in startup['world']['entities'] if p['templateType']=='villager_type'}
   self.assertIn({'villagerId':moved_id,'type':4},people[ids['steve']]['relations']);self.assertIn({'villagerId':ids['steve'],'type':5},people[moved_id]['relations'])
   call('ClientVillagerService/SetName',{'villagerId':moved_id,'name':'Marriage Test Partner'},1045)
   saved=json.loads(path.read_text(encoding='utf-8'))['normal'];self.assertEqual(family.actor(saved,self.target['id'])['name'],'Marriage Test Partner')
   # The moved adult is accepted by the existing ordinary housing/family rules.
   home={'id':'test-marriage-home','templateType':'shelter','templateId':0,'position':copy.deepcopy(self.person['position'])};habitats.initialize(home,1046);saved['world']['entities'].append(home)
   for bed,person in zip(home['beds'],[family.actor(saved,'steve'),family.actor(saved,self.target['id'])]):
    habitats.assign(saved,{'villagerId':person['id'],'shelterBedId':bed['id']},1046)
   mother=family.actor(saved,self.target['id']);mother.update(startAge=25,bornAt=1046)
   family.couple(saved,mother['id'],1046);world.validate_world(saved)

if __name__=='__main__':unittest.main()
