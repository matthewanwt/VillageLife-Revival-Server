import copy,json,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import family,relationships as rel,session,world

class RelationshipTests(unittest.TestCase):
 def setUp(self):
  self.state=world.build_bridge_world(session.fresh_tutorial(),1000)
  self.person=family.actor(self.state,'steve');self.person.update(startAge=25,bornAt=1000,relations=[])
 def test_native_catalogue_is_encoded_persistent_and_explicitly_npc(self):
  reply,changed=rel.operate(self.state,'ClientVillager/GetCommunityVillagers',{'Gender':'1'},1000,'424242');self.assertTrue(changed)
  self.assertEqual(len(reply['result']),int(world.global_value('communityDatesAvailable')))
  before=copy.deepcopy(self.state);again,changed=rel.operate(self.state,'ClientVillager/GetCommunityVillagers',{'Gender':'1'},1001,'424242');self.assertFalse(changed);self.assertEqual(reply,again);self.assertEqual(before,self.state)
  values=[json.loads(r['data']) for r in reply['result']];self.assertEqual(len({v['villager']['id'] for v in values}),len(values))
  for value in values:
   self.assertEqual(value['user']['name'],'Local NPC Village');self.assertEqual(value['villager']['gender'],1);self.assertIn('identifier',value['user']);self.assertIn('Rarity',value['villager']);self.assertTrue(value['villager']['equipment'])
  self.assertTrue(all(p['ownerKind']=='npc' for p in self.state['npcDatingPool']))
  self.assertNotEqual({p['id'] for p in self.state['npcDatingPool']},{p['id'] for p in family.actors(self.state)})
 def test_catalogue_candidate_skill_read_uses_private_npc_pool(self):
  response,_=rel.catalogue(self.state,{'Gender':1},1000,'42');ident=json.loads(response['result'][0]['data'])['villager']['id']
  self.assertEqual(family.skills(self.state,{'villagerIds':json.dumps({'villagerIds':[ident]})}),{'villagerSkills':[]})
  with self.assertRaises(ValueError):family.skills(self.state,{'villagerIds':'{"villagerIds":["Villager_99999999_5"]}'})
 def test_invalid_gender_does_not_create_pool(self):
  for value in [True,2,None,[],{},'female']:
   with self.subTest(value=value),self.assertRaises(ValueError):rel.operate(self.state,'ClientVillager/GetCommunityVillagers',{'Gender':value},1000,'42')
   self.assertNotIn('npcDatingPool',self.state)
 def test_npc_age_is_persistent_not_reset_on_each_query(self):
  rel.catalogue(self.state,{'Gender':1},1000,'42');at=1000+40*int(world.global_value('hours_per_year'))*3600
  old_ids={p['id'] for p in self.state['npcDatingPool']};reply,changed=rel.catalogue(self.state,{'Gender':1},at,'42');self.assertTrue(changed);self.assertEqual(len(reply['result']),4);self.assertTrue(old_ids.isdisjoint({p['id'] for p in self.state['npcDatingPool']}));self.assertTrue(all(p['bornAt']==at for p in self.state['npcDatingPool']))
 def test_wishes_use_original_category_material_and_interval(self):
  first,changed=rel.operate(self.state,'ClientWant/GenerateRelationshipWants',{},1000,'42');self.assertTrue(changed)
  mine=[w for w in first['result'] if w['VillagerStringID']=='steve'];self.assertEqual(len(mine),1);self.assertEqual((mine[0]['MaterialID'],mine[0]['wantableCategoryType']),(340,5))
  before=copy.deepcopy(self.state);self.assertFalse(rel.generate(self.state,1001)[1]);self.assertEqual(before,self.state)
  rel.operate(self.state,'ClientWant/SatisfyRelationshipWant',{'VillagerStringID':'steve'},1002,'42');self.assertFalse(rel.generate(self.state,1003)[1]);self.assertTrue(rel.generate(self.state,1002+28800)[1])
 def test_married_pregnant_and_underage_villagers_are_not_eligible(self):
  self.assertTrue(rel.dateable(self.person,1000));self.person['relations']=[{'villagerId':'jill','type':2}];self.assertFalse(rel.dateable(self.person,1000))
  self.person['relations']=[];self.person['startAge']=17;self.assertFalse(rel.dateable(self.person,1000))
  mother=family.actor(self.state,'jill');mother.update(startAge=25,pregnant='true',relations=[]);self.assertFalse(rel.dateable(mother,1000))
 def test_opt_in_only_changes_selected_owned_eligible_actor(self):
  response,changed=rel.operate(self.state,'ClientVillagerService/OptIntoCommunity',{'villagerId':'steve'},1000,'42');self.assertTrue(changed);self.assertEqual(response,{})
  self.assertFalse(rel.operate(self.state,'ClientVillagerService/OptIntoCommunity',{'villagerId':'steve'},1001,'42')[1])
  with self.assertRaises(ValueError):rel.operate(self.state,'ClientVillagerService/OptIntoCommunity',{'villagerId':'someone-elses-villager'},1001,'42')
 def test_world_wire_maps_groups_to_original_gendered_ids_without_mutation(self):
  self.person['relations']=[{'villagerId':'jill','type':2}];before=copy.deepcopy(self.state)
  for entities in [world.startup(self.state,1000)['world']['entities'],world.area_content(self.state,1,1000)['areaJson']['entities']]:
   people={p['id']:p for p in entities if p['templateType']=='villager_type'}
   self.assertIn({'villagerId':'jill','type':4},people['steve']['relations']);self.assertIn({'villagerId':'steve','type':5},people['jill']['relations']);self.assertIn({'villagerId':'steve','type':1},people['baby male']['relations'])
  self.assertEqual(before,self.state)
 def test_authenticated_catalogue_saved_restart_and_session_isolation(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(session,'STATE',Path(folder)),patch.object(session,'wire_time',return_value=1000):
   profile=session.login({'deviceId':'dating-test'})['data']['users'][0];path=session.profile_path('dating-test').with_suffix('.tutorial.json');session.atomic_json(path,{**session.fresh_tutorial(),'normal':self.state})
   def call(profile):return session.process({**profile,'data':{'calls':[{'id':'1','service':'ClientVillager/GetCommunityVillagers','data':{'Gender':'1'}}]}})['data']['calls'][0]
   first=call(profile);self.assertEqual(first['code'],200);self.assertTrue(json.loads(path.read_text(encoding='utf-8'))['normal']['npcDatingPool']);session.login({'deviceId':'dating-test'});self.assertEqual(first['data'],call(profile)['data'])
   self.assertEqual(call({**profile,'sessionId':'invalid'})['code'],403)

class NpcDateRequestTests(unittest.TestCase):
 setUp=RelationshipTests.setUp
 # A separate TestCase would duplicate fixture setup; run only the new methods below.
 def ready(self):
  import native_identity
  rel.catalogue(self.state,{'Gender':1},1000,'42');self.person['communityOptIn']=True
  self.target=next(p for p in self.state['npcDatingPool'] if p['gender']==1)
  self.raw=next(raw for raw,ident in native_identity.mappings(self.state,'42')[2].items() if ident=='steve')
  return {'ForUserIds':[int(self.target['ownerUserId'])],'CharacterIds':[int(self.target['id'].split('_')[-1])],'FriendCharacterId':int(self.raw),'FriendCharacterAppearance':'untrusted appearance deliberately ignored'}
 def test_request_has_delayed_native_incoming_reply_and_retry_does_not_duplicate(self):
  data=self.ready();self.assertTrue(rel.community(self.state,'CharacterRequest/Create',data,1000,'42')[1]);self.assertFalse(rel.community(self.state,'CharacterRequest/Create',data,1001,'42')[1]);self.assertEqual(len(self.state['npcDateRequests']),1)
  self.assertEqual(rel.community(self.state,'CharacterRequest/GetReceived',{},1019,'42')[0],{'CharacterRequests':[]})
  response,_=rel.community(self.state,'CharacterRequest/GetReceived',{},1020,'42');item=response['CharacterRequests'][0];self.assertEqual(item['CharacterID'],self.raw);self.assertEqual(item['ForUserID'],'42');self.assertEqual(item['ByUserID'],self.target['ownerUserId']);self.assertEqual(json.loads(item['FriendCharacterAppearance'])['name'],self.target['name'])
 def test_acceptance_is_saved_external_npc_not_added_to_owned_population(self):
  data=self.ready();rel.community(self.state,'CharacterRequest/Create',data,1000,'42');record=self.state['npcDateRequests'][0];count=family.population(self.state)
  reply,changed=rel.operate(self.state,'ClientRequest/AcceptDatingRequest',{'RequestID':int(record['id'])},1020,'42');self.assertTrue(changed);self.assertEqual(reply,{})
  self.assertIn({'villagerId':self.target['id'],'type':4},self.person['relations']);self.assertEqual(family.population(self.state),count);world.validate_world(self.state)
  projected=next(p for p in world.startup(self.state,1020)['world']['entities'] if p['id']=='steve');self.assertIn({'villagerId':self.target['id'],'type':8},projected['relations'])
  family.history(self.state,{'userId':'42'},1020,'42');before=copy.deepcopy(self.state);self.assertFalse(rel.operate(self.state,'ClientRequest/AcceptDatingRequest',{'RequestID':record['id']},1021,'42')[1]);self.assertEqual(before,self.state)
  reply,_=rel.operate(self.state,'ClientVillagerService/GetPartnerVillager',{'villagerId':'steve'},1021,'42');self.assertEqual(reply['villager']['id'],self.target['id']);self.assertEqual(reply['user']['id'],self.target['ownerUserId'])
 def test_refresh_replenishes_candidates_without_resetting_an_existing_partner(self):
  data=self.ready();rel.community(self.state,'CharacterRequest/Create',data,1000,'42');rel.accept_date(self.state,{'RequestID':self.state['npcDateRequests'][0]['id']},1020)
  before=copy.deepcopy(self.target);reply,changed=rel.catalogue(self.state,{'Gender':1},1000+259200,'42');self.assertTrue(changed);self.assertEqual(len(reply['result']),4)
  self.assertEqual(before,rel.npc(self.state,self.target['id']));world.validate_world(self.state)
 def test_early_expired_unknown_or_deleted_request_does_not_create_relationship(self):
  data=self.ready();rel.community(self.state,'CharacterRequest/Create',data,1000,'42');record=self.state['npcDateRequests'][0]
  for at in [1001,1000+259200]:
   before=copy.deepcopy(self.state)
   with self.assertRaises(ValueError):rel.accept_date(self.state,{'RequestID':record['id']},at)
   self.assertEqual(before,self.state)
  with self.assertRaises(PermissionError):rel.accept_date(self.state,{'RequestID':'other-player-request'},1020)
  rel.community(self.state,'CharacterRequest/Delete',{'CharacterRequestIds':[int(record['id'])]},1020,'42')
  with self.assertRaises(ValueError):rel.accept_date(self.state,{'RequestID':record['id']},1020)
 def test_forged_human_recipient_and_unowned_sender_are_not_simulated(self):
  data=self.ready();before=copy.deepcopy(self.state)
  with self.assertRaises(PermissionError):rel.community(self.state,'CharacterRequest/Create',{**data,'ForUserIds':[123456]},1000,'42')
  self.assertEqual(before,self.state)
  with self.assertRaises(ValueError):rel.community(self.state,'CharacterRequest/Create',{**data,'FriendCharacterId':12345},1000,'42')
  self.assertEqual(before,self.state)
 def test_accepting_one_date_cancels_competing_offers_and_survives_json_reload(self):
  data=self.ready();rel.community(self.state,'CharacterRequest/Create',data,1000,'42');other=next(p for p in self.state['npcDatingPool'] if p['gender']==1 and p['id']!=self.target['id'])
  rel.community(self.state,'CharacterRequest/Create',{**data,'ForUserIds':[int(other['ownerUserId'])],'CharacterIds':[int(other['id'].split('_')[-1])]},1001,'42');rel.accept_date(self.state,{'RequestID':self.state['npcDateRequests'][0]['id']},1020)
  self.assertEqual(self.state['npcDateRequests'][1]['status'],'superseded');world.validate_world(json.loads(json.dumps(self.state)))

class NpcBreakupTests(unittest.TestCase):
 setUp=RelationshipTests.setUp
 ready=NpcDateRequestTests.ready
 def accepted(self):
  data=self.ready();rel.community(self.state,'CharacterRequest/Create',data,1000,'42')
  rel.accept_date(self.state,{'RequestID':self.state['npcDateRequests'][0]['id']},1020)
 def test_breakup_is_reciprocal_persistent_replay_safe_and_allows_another_date(self):
  self.accepted();count=family.population(self.state);data={'villagerId':'steve','partnerVillagerId':self.target['id']}
  response,changed=rel.operate(self.state,'ClientVillagerService/Breakup',data,1021,'42');self.assertTrue(changed);self.assertEqual(response,{})
  self.assertEqual(self.person['relations'],[]);self.assertEqual(self.target['relations'],[]);self.assertNotIn(self.target['id'],self.state['externalVillagers']);self.assertEqual(family.population(self.state),count)
  world.validate_world(self.state);self.state=json.loads(json.dumps(self.state));before=copy.deepcopy(self.state)
  self.assertFalse(rel.operate(self.state,'ClientVillagerService/Breakup',data,1022,'42')[1]);self.assertEqual(before,self.state)
  request={'ForUserIds':[int(self.target['ownerUserId'])],'CharacterIds':[int(self.target['id'].split('_')[-1])],'FriendCharacterId':int(self.raw)}
  self.assertTrue(rel.community(self.state,'CharacterRequest/Create',request,1023,'42')[1]);self.assertEqual(len(self.state['npcDateRequests']),2)
  rel.accept_date(self.state,{'RequestID':self.state['npcDateRequests'][-1]['id']},1043);world.validate_world(self.state)
 def test_wrong_partner_human_and_unowned_sender_are_rejected_without_changes(self):
  self.accepted();other=next(p for p in self.state['npcDatingPool'] if p['gender']==1 and p['id']!=self.target['id'])
  for data in [{'villagerId':'steve','partnerVillagerId':other['id']},{'villagerId':'steve','partnerVillagerId':'Villager_99_1'},{'villagerId':'other-player','partnerVillagerId':self.target['id']}]:
   before=copy.deepcopy(self.state)
   with self.assertRaises((ValueError,PermissionError)):rel.breakup(self.state,data,1021)
   self.assertEqual(before,self.state)
 def test_marriage_is_not_silently_divorced(self):
  self.accepted();self.person['relations'].append({'villagerId':'jill','type':2});before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):rel.breakup(self.state,{'villagerId':'steve','partnerVillagerId':self.target['id']},1021)
  self.assertEqual(before,self.state)

if __name__=='__main__':unittest.main()
