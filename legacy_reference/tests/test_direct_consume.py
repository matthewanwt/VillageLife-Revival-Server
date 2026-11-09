import copy,unittest
import needs,world,session
class DirectConsumeTests(unittest.TestCase):
 def setUp(self):
  self.state=world.build_bridge_world(session.fresh_tutorial(),1000)
  self.state['inventory'].update({'6':10,'107':10})
 def test_native_no_want_path_spends_once_and_has_no_phantom_wish(self):
  data={'VillagerStringID':'steve','MaterialTypeID':6}
  response,changed=needs.consume(self.state,data,1001,'epoch:1')
  self.assertTrue(changed);self.assertEqual(self.state['inventory']['6'],9)
  self.assertNotIn('WantID',response['result']);self.assertEqual(response['SatisfiedWantModels'],[])
  self.assertEqual(response['result']['VillagerStringID'],'steve')
  before=copy.deepcopy(self.state)
  self.assertFalse(needs.consume(self.state,data,9999,'epoch:1')[1]);self.assertEqual(self.state,before)
 def test_different_native_call_during_need_interval_does_not_spend_again(self):
  data={'VillagerStringID':'sister','MaterialTypeID':107}
  needs.consume(self.state,data,1001,'epoch:1')
  self.assertFalse(needs.consume(self.state,data,1002,'epoch:2')[1]);self.assertEqual(self.state['inventory']['107'],9)
  self.assertTrue(needs.consume(self.state,data,20000,'epoch:3')[1]);self.assertEqual(self.state['inventory']['107'],8)
 def test_unknown_explicit_wish_and_non_food_cannot_create_a_wish(self):
  before=copy.deepcopy(self.state)
  for data in [{'VillagerStringID':'steve','MaterialTypeID':107,'WantID':9999},{'VillagerStringID':'steve','MaterialTypeID':323}]:
   with self.assertRaises(ValueError):needs.consume(self.state,data,1001,'epoch:1')
   self.assertEqual(self.state,before)
 def test_all_original_food_branches_and_observed_farmed_items(self):
  definitions=[v for v in world.rows('material_type') if v['categoryId'] in {'8','9','10','11'}]
  self.assertIn('42',{v['id'] for v in definitions});self.assertIn('1005',{v['id'] for v in definitions})
  for definition in definitions:
   state=copy.deepcopy(self.state);material=int(definition['id']);state['inventory'][str(material)]=2
   with self.subTest(material=material):
    result,changed=needs.consume(state,{'VillagerStringID':'steve','MaterialTypeID':material},1001,'food')
    self.assertTrue(changed);self.assertEqual(state['inventory'][str(material)],1)
    before=copy.deepcopy(state);self.assertFalse(needs.consume(state,{'VillagerStringID':'steve','MaterialTypeID':material},1002,'food')[1]);self.assertEqual(before,state)
 def test_empty_stock_does_not_grant_happiness(self):
  self.state['inventory']['6']=0;before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):needs.consume(self.state,{'VillagerStringID':'steve','MaterialTypeID':6},1001,'epoch:1')
  self.assertEqual(self.state,before)
if __name__=='__main__':unittest.main()
