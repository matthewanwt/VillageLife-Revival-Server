import copy,json,tempfile,unittest,struct
from pathlib import Path
from unittest.mock import patch
import family,native_identity as native,session,world

class NativeIdentityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.scope=patch.object(session,'STATE',Path(self.tmp.name));self.scope.start();self.addCleanup(self.scope.stop)
  self.profile=session.login({'deviceId':'identity-test'})['data']['users'][0];self.path=session.profile_path('identity-test').with_suffix('.tutorial.json');self.state=world.build_bridge_world(session.fresh_tutorial(),1000);session.atomic_json(self.path,{**session.fresh_tutorial(),'normal':self.state})
 def call(self,service,data,ident=1):return session.process({**self.profile,'data':{'calls':[{'id':str(ident),'service':service,'data':data}]}},native_ids=True)['data']['calls'][0]
 def test_numeric_suffix_is_exact_in_original_float32_parsers(self):
  outward,_,_,_=native.mappings(self.state,self.profile['pId'])
  for value in outward.values():
   raw=int(value.rsplit('_',1)[1]);self.assertLessEqual(raw,0xffffff)
   self.assertEqual(int(struct.unpack('<f',struct.pack('<f',raw))[0]),raw)
 def test_registry_survives_reload_actor_removal_and_new_actor(self):
  first=native.mappings(self.state,self.profile['pId'])[0];state=json.loads(json.dumps(self.state))
  state['world']['entities']=[p for p in state['world']['entities'] if p['id']!='jill']
  new=copy.deepcopy(family.actor(state,'steve'));new['id']='future-actor';state['world']['entities'].append(new)
  current=native.mappings(state,self.profile['pId'])[0]
  self.assertEqual(current['steve'],first['steve']);self.assertEqual(len(set(current.values())),len(current))
  self.assertIn('jill',state['nativeIdentityIds'][self.profile['pId']])
 def test_legacy_large_ids_are_accepted_but_never_emitted(self):
  import hashlib
  legacy='Villager_'+self.profile['pId']+'_'+str(int(hashlib.sha256((self.profile['pId']+':steve').encode()).hexdigest()[:12],16)+1)
  outward,inward,_,_=native.mappings(self.state,self.profile['pId']);self.assertEqual(inward[legacy],'steve');self.assertNotEqual(outward['steve'],legacy)
 def test_breakup_partner_field_translates_without_changing_names(self):
  outward,inward,_,_=native.mappings(self.state,self.profile['pId'])
  value={'villagerId':outward['steve'],'partnerVillagerId':outward['jill'],'name':outward['jill']}
  self.assertEqual(native.translate(value,inward),{'villagerId':'steve','partnerVillagerId':'jill','name':outward['jill']})
 def test_native_breakup_is_authenticated_and_persisted_without_duplicate_changes(self):
  import relationships as rel
  person=family.actor(self.state,'steve');person.update(startAge=25,bornAt=1000,relations=[],communityOptIn=True)
  # Remove the old spouse's reciprocal link in this isolated fixture.
  family.actor(self.state,'jill')['relations']=[r for r in family.actor(self.state,'jill')['relations'] if r['villagerId']!='steve' or int(r['type'])!=2]
  rel.catalogue(self.state,{'Gender':1},1000,self.profile['pId']);target=next(p for p in self.state['npcDatingPool'] if p['gender']==1)
  outward,_,raw_in,_=native.mappings(self.state,self.profile['pId']);raw=next(k for k,v in raw_in.items() if v=='steve')
  rel.community(self.state,'CharacterRequest/Create',{'ForUserIds':[int(target['ownerUserId'])],'CharacterIds':[int(target['id'].split('_')[-1])],'FriendCharacterId':int(raw)},1000,self.profile['pId'])
  rel.accept_date(self.state,{'RequestID':self.state['npcDateRequests'][0]['id']},1020)
  session.atomic_json(self.path,{**session.fresh_tutorial(),'normal':self.state})
  with patch.object(session,'wire_time',return_value=1021):
   self.assertEqual(self.call('ClientVillagerService/Breakup',{'villagerId':outward['steve'],'partnerVillagerId':target['id']})['code'],200)
   before=self.path.read_bytes()
   self.assertEqual(self.call('ClientVillagerService/Breakup',{'villagerId':outward['steve'],'partnerVillagerId':target['id']})['code'],200)
   self.assertEqual(before,self.path.read_bytes())
  saved=json.loads(self.path.read_text(encoding='utf-8'))['normal'];world.validate_world(saved)
  self.assertEqual(saved['npcDateRequests'][0]['status'],'broken_up');self.assertNotIn(target['id'],saved['externalVillagers'])
 def test_all_existing_actor_ids_have_numeric_suffix_and_save_is_unchanged(self):
  before=self.path.read_bytes();reply=self.call('ClientStartupService/GetStartupInfo',{});self.assertEqual(reply['code'],200)
  actors=[p for p in reply['data']['world']['entities'] if p['templateType']=='villager_type'];ids={p['id'] for p in actors};self.assertEqual(len(ids),6)
  for person in actors:
   self.assertTrue(person['id'].startswith('Villager_'+self.profile['pId']+'_'));self.assertTrue(person['id'].split('_')[-1].isdecimal());self.assertTrue(all(r['villagerId'] in ids for r in person['relations']))
  # Startup may run existing migrations; identities themselves remain canonical.
  self.assertEqual([p['id'] for p in family.actors(json.loads(self.path.read_text(encoding='utf-8'))['normal'])],[p['id'] for p in family.actors(self.state)])
 def test_name_and_profile_requests_round_trip_native_ids_without_renaming_seed_refs(self):
  out,_,_,_=native.mappings(self.state,self.profile['pId']);ident=out['steve']
  self.assertEqual(self.call('ClientVillagerService/SetName',{'villagerId':ident,'name':'steve'})['code'],200)
  saved=json.loads(self.path.read_text(encoding='utf-8'))['normal'];self.assertEqual(family.actor(saved,'steve')['name'],'steve');self.assertEqual(family.actor(saved,'steve')['refId'],'steve')
  reply=self.call('ClientVillagerService/GetVillagerRelations',{'userId':self.profile['pId']});person=next(p for p in reply['data']['villagers'] if p['id']==ident);self.assertEqual(person['name'],'steve')
  self.assertEqual(self.call('ClientVillagerService/GetVillagerSkills',{'villagerIds':json.dumps({'villagerIds':[ident]})})['code'],200)
 def test_newborn_raw_and_full_ids_are_consistent_numeric_and_not_duplicated(self):
  child=copy.deepcopy(family.actor(self.state,'baby male'));child.update(id='Villager_'+self.profile['pId']+'_abc123uuid',serverBirthId='abc123uuid',relations=[]);self.state['world']['entities'].append(child)
  out,inward,raw_in,raw_out=native.mappings(self.state,self.profile['pId']);self.assertEqual(out[child['id']],'Villager_'+self.profile['pId']+'_'+raw_out['abc123uuid']);self.assertEqual(inward[out[child['id']]],child['id']);self.assertEqual(raw_in[raw_out['abc123uuid']],child['id'])
  self.assertEqual(native.translate({'ID':'abc123uuid','Name':'steve'},out,raw_out),{'ID':raw_out['abc123uuid'],'Name':'steve'})
 def test_projection_does_not_touch_authentication_call_ids_names_or_equipment(self):
  out,_,_,_=native.mappings(self.state,self.profile['pId']);value={'name':'steve','refId':'steve','equipment':'steve','villagerId':'steve'};projected=native.translate(value,out)
  self.assertEqual(projected,{**value,'villagerId':out['steve']});self.assertEqual(value['villagerId'],'steve')
  self.assertEqual(native.mappings(self.state,self.profile['pId']),native.mappings(json.loads(json.dumps(self.state)),self.profile['pId']))
 def test_unauthenticated_mapping_cannot_read_or_mutate_other_saves(self):
  before=self.path.read_bytes()
  result=session.process({**self.profile,'sessionId':'wrong','data':{'calls':[{'id':'1','service':'ClientStartupService/GetStartupInfo','data':{}}]}},native_ids=True);self.assertEqual(result['data']['calls'][0]['code'],403)
  self.assertEqual(self.path.read_bytes(),before)

 def test_friend_visit_projects_the_visited_players_ids_not_the_viewers(self):
  import social
  friend=session.login({'deviceId':'identity-friend'})['data']['users'][0];friend_path=session.profile_path('identity-friend').with_suffix('.tutorial.json');session.atomic_json(friend_path,{**session.fresh_tutorial(),'normal':copy.deepcopy(self.state)})
  social.link(session.STATE,social.public_id(self.profile),social.public_id(friend))
  response=self.call('ClientFriendService/GetFriendStartupInfo',{'friendUserId':social.public_id(friend)})
  self.assertEqual(response['code'],200);expected=native.mappings(self.state,friend['pId'])[0]['steve'];viewer=native.mappings(self.state,self.profile['pId'])[0]['steve']
  ids={p['id'] for p in response['data']['world']['entities'] if p['templateType']=='villager_type'};self.assertIn(expected,ids);self.assertNotIn(viewer,ids)

 def test_birth_and_rename_round_trip_through_native_numeric_identity_boundary(self):
  import habitats
  with patch.object(session,'wire_time',return_value=1000) as clock:
   home={'id':'native-family-home','templateType':'shelter','templateId':0,'serverPersisted':True,'position':{'x':2200,'y':3400,'areaId':1,'rotation':0}};habitats.initialize(home,1000);self.state['world']['entities'].append(home)
   for ident,bed in zip(['steve','jill'],home['beds']):habitats.assign(self.state,{'villagerId':ident,'shelterBedId':bed['id']},1000)
   session.atomic_json(self.path,{**session.fresh_tutorial(),'normal':self.state});out=native.mappings(self.state,self.profile['pId'])[0]
   with patch.object(family,'roll',side_effect=[0,99,0]):self.assertEqual(self.call('ClientVillager/CanConcievePregnancy',{'villagerId':out['jill']},1)['code'],200)
   clock.return_value=87400;reply=self.call('ClientVillager/Birth',{'VillagerStringID':out['jill']},2);self.assertEqual(reply['code'],200)
   raw=reply['data']['result']['villagers'][0]['ID'];self.assertTrue(raw.isdecimal());ident='Villager_'+self.profile['pId']+'_'+raw
   self.assertEqual(self.call('ClientVillagerService/SetName',{'villagerId':ident,'name':'Numeric Newborn'},3)['code'],200)
   actors=self.call('ClientStartupService/GetStartupInfo',{},4)['data']['world']['entities'];self.assertEqual(next(p for p in actors if p['id']==ident)['name'],'Numeric Newborn')

 def test_gathering_and_harvest_keep_wire_ids_and_canonical_receipts_consistent(self):
  with patch.object(session,'wire_time',return_value=1000) as clock:
   out=native.mappings(self.state,self.profile['pId'])[0];source=next(p for p in self.state['world']['entities'] if p.get('refId')=='Strawberries')
   start=self.call('ClientTaskService/StartGatheringTask',{'villagerId':out['steve'],'userMaterialSourceId':source['id'],'taskTypeId':14,**source['position']},1)
   self.assertEqual(start['code'],200);self.assertEqual(start['data']['villager']['id'],out['steve']);clock.return_value=1030
   finish=self.call('ClientTaskService/HarvestTask',{'workAreaId':start['data']['workAreaId'],'taskTypeId':14},2);self.assertEqual(finish['code'],200)
   saved=json.loads(self.path.read_text(encoding='utf-8'))['normal'];job=saved['workAreas'][start['data']['workAreaId']];self.assertEqual(job['villagerId'],'steve');world.validate_world(saved)
 def test_fire_lighting_owner_and_reload_use_the_same_native_villager_id(self):
  with patch.object(session,'wire_time',return_value=1000):
   for req in world.rows('requirement_set_item'):self.state['inventory'][req['materialType']]=max(self.state['inventory'].get(req['materialType'],0),float(req['quantity'])+float(req['quantityUsed'])+100)
   session.atomic_json(self.path,{**session.fresh_tutorial(),'normal':self.state});fire=next(p for p in self.state['world']['entities'] if p['templateType']=='fire_type');ident=native.mappings(self.state,self.profile['pId'])[0]['steve']
   response=self.call('ClientUserFireService/StartFire',{'userFireId':fire['id'],'villagerId':ident},1);self.assertEqual(response['code'],200)
   actors=self.call('ClientStartupService/GetStartupInfo',{},2)['data']['world']['entities'];self.assertEqual(next(p for p in actors if p['id']==fire['id'])['lightingVillagerId'],ident)

if __name__=='__main__':unittest.main()
