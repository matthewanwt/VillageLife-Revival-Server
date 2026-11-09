import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import make_test_village as fixtures
import family,session,world

class TestVillageFactoryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.base=Path(self.tmp.name);self.source=self.base/'source';self.source.mkdir()
  with patch.object(session,'STATE',self.source):
   session.login({'deviceId':'fixture-source'});path=session.profile_path('fixture-source').with_suffix('.tutorial.json');session.atomic_json(path,{'normal':world.build_bridge_world(session.fresh_tutorial(),1000),**session.fresh_tutorial()})
  self.before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()}
 def generate(self,scenario):
  with patch.object(fixtures,'ROOT',self.base/'workspace'):meta=fixtures.create(self.source,scenario,100000)
  self.assertFalse(meta['source_save_modified']);self.assertEqual(self.before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in self.source.iterdir()})
  return meta,json.loads(next(Path(meta['state']).glob('*.tutorial.json')).read_text(encoding='utf-8'))['normal']
 def test_family_ready_has_two_adults_valid_beds_and_separate_test_funds(self):
  meta,state=self.generate('family-ready');self.assertEqual(len(family.actors(state)),2);family.couple(state,'jill',100000);self.assertEqual(state['inventory']['323'],500);world.validate_world(state);self.assertIn('--smoke-test 600',meta['run'])
 def test_birth_ready_uses_a_real_saved_pregnancy_past_original_due_time(self):
  _,state=self.generate('birth-ready');self.assertTrue(family.is_pregnant(family.actor(state,'jill')));self.assertLess(state['pregnancies']['jill']['readyAt'],100000);world.validate_world(state)
 def test_dating_ready_is_an_unrelated_single_adult(self):
  _,state=self.generate('dating-ready');people=family.actors(state);self.assertEqual(len(people),1);self.assertEqual(people[0]['relations'],[]);self.assertEqual(world.current_age(people[0],100000),25)
 def test_marriage_fixture_has_a_real_accepted_date_and_no_invented_owned_partner(self):
  _,state=self.generate('marriage-ready');people=family.actors(state);self.assertEqual(len(people),1)
  self.assertEqual(state['npcDateRequests'][0]['status'],'accepted');self.assertEqual(len(state['externalVillagers']),1)
  self.assertEqual(people[0]['relations'][0]['type'],4);world.validate_world(state)
  self.assertFalse(state.get('pregnancies'))
 def test_wedding_ready_has_an_accepted_inbox_proposal_but_no_completed_marriage(self):
  _,state=self.generate('wedding-ready');self.assertEqual(len(family.actors(state)),1)
  self.assertEqual(len(state['npcMarriageRequests']),1);request=state['npcMarriageRequests'][0]
  self.assertEqual(request['status'],'accepted');self.assertLessEqual(request['readyAt'],100000)
  self.assertEqual(family.actors(state)[0]['relations'][0]['type'],4)
  self.assertEqual(len(state['externalVillagers']),1);world.validate_world(state)
 def test_combined_family_flow_keeps_pregnancy_and_separate_dating_pair(self):
  _,state=self.generate('family-flow-ready');self.assertEqual(len(family.actors(state)),3)
  mother=family.actor(state,'jill');self.assertTrue(family.is_pregnant(mother));self.assertLess(state['pregnancies']['jill']['readyAt'],100000)
  self.assertEqual(family.spouse(state,mother)['id'],'steve');family.couple(state,'jill',100000)
  single=family.actor(state,'fixture-single-adult');self.assertEqual(single['name'],'Oliver');self.assertEqual(single['relations'][0]['type'],4)
  self.assertTrue(any(w['VillagerStringID']==single['id'] and w['MaterialID']==342 for w in state['wants']))
  self.assertFalse(state.get('npcMarriageRequests'));self.assertEqual(len(state['externalVillagers']),1)
  self.assertTrue(all(not b['villagerId'] for e in state['world']['entities'] if e['id']=='fixture-second-home' for b in e['beds']));world.validate_world(state)
 def test_resource_rich_preserves_actors_and_is_never_normal_save(self):
  _,state=self.generate('resource-rich');self.assertEqual(len(family.actors(state)),6);self.assertEqual(state['inventory']['323'],500)

if __name__=='__main__':unittest.main()
