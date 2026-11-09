import unittest,copy
from unittest.mock import patch
import session,world
class StaticCacheTests(unittest.TestCase):
 def test_new_player_seed_is_not_shared_between_calls(self):
  first=session.fresh_tutorial();first['userHash']['data']['villagers'][0]['name']='changed'
  second=session.fresh_tutorial()
  self.assertNotEqual(second['userHash']['data']['villagers'][0]['name'],'changed')
 def test_indexed_table_record_is_a_fresh_copy_and_matches_original(self):
  original=next(r for r in world.rows('material_type') if r['id']=='107')
  first=world.by_id('material_type',107);self.assertEqual(first,original);first['name']='changed'
  self.assertEqual(world.by_id('material_type',107),original)
  with self.assertRaises(StopIteration):world.by_id('material_type',-999999)
 def test_large_projection_relations_match_independent_calls_without_changing_save(self):
  state=world.build_bridge_world(session.fresh_tutorial(),1000)
  actors=[p for p in state['world']['entities'] if p['templateType']=='villager_type']
  for index in range(100):
   actor=copy.deepcopy(actors[0]);actor.update(id='projection-'+str(index),refId='',relations=[],shelterBedId='');state['world']['entities'].append(actor)
  expected={p['id']:world.native_relations(state,p) for p in state['world']['entities'] if p['templateType']=='villager_type'}
  before=copy.deepcopy(state)
  with patch.object(world,'relation_context',wraps=world.relation_context) as context:
   projected=world.startup(state,1000)['world']['entities'];self.assertEqual(context.call_count,1)
  self.assertEqual({p['id']:p['relations'] for p in projected if p['templateType']=='villager_type'},expected)
  self.assertEqual(state,before)
  person=actors[0];first=world.current_villager_type(person,1000);first['name']='changed'
  self.assertNotEqual(world.current_villager_type(person,1000)['name'],'changed')
if __name__=='__main__':unittest.main()
