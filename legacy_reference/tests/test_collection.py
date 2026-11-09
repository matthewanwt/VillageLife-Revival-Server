import copy,json,struct,unittest
import world,session,collection,native_identity,family
class CollectionTests(unittest.TestCase):
 def setUp(self):
  self.state=world.build_bridge_world(session.fresh_tutorial(),1000);self.state['inventory']['323']=10000;self.owner='1'
 def purchase(self,base=52,key='purchase'):
  seed=collection.definition(base)
  return collection.operate(self.state,'ClientVillagerService/CreateGachaVillager',{'GachaVillagerId':str(base),'GemCost':collection.shop_price(seed)},1000,self.owner,key)
 def test_purchase_original_equipment_price_identity_and_reload(self):
  cost=collection.shop_price(collection.definition(52));before=len(family.actors(self.state));response,changed=self.purchase();self.assertTrue(changed)
  self.assertEqual(self.state['inventory']['323'],10000-cost);self.assertEqual(len(family.actors(self.state)),before+1)
  raw=response['villager'][0]['id'];self.assertEqual(raw,int(struct.unpack('<f',struct.pack('<f',raw))[0]))
  person=next(v for v in family.actors(self.state) if v.get('collectionBaseId')==52)
  self.assertEqual(person['equipment'],collection.definition(52)['equipment']);self.assertEqual(native_identity.mappings(self.state,self.owner)[0][person['id']],'Villager_1_'+str(raw))
  self.state=json.loads(json.dumps(self.state));before=copy.deepcopy(self.state);self.assertFalse(self.purchase()[1]);self.assertEqual(before,self.state);world.validate_world(self.state)
 def test_each_purchased_clone_has_distinct_identity(self):
  first,_=self.purchase(key='first');second,_=self.purchase(key='second')
  self.assertNotEqual(first['villager'][0]['id'],second['villager'][0]['id'])
 def test_bad_price_capacity_or_missing_funds_never_spends(self):
  self.state['inventory']['323']=0;before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):self.purchase()
  self.assertEqual(before,self.state);self.state['inventory']['323']=10000;self.state['user']['populationCap']=len(family.actors(self.state));before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):self.purchase()
  self.assertEqual(before,self.state)
 def test_collection_acknowledgment_is_saved_and_does_not_give_an_invented_reward(self):
  self.purchase();before=copy.deepcopy(self.state['inventory'])
  self.assertTrue(collection.operate(self.state,'ClientVillagerService/CollectVillager',{'VillagerBaseId':52},1001,self.owner,None)[1])
  self.assertFalse(collection.operate(self.state,'ClientVillagerService/CollectVillager',{'VillagerBaseId':52},1002,self.owner,None)[1]);self.assertEqual(before,self.state['inventory'])
  self.assertEqual(json.loads(collection.read(self.state)['VillagerCollection']),{'52':3})
 def test_every_original_priced_definition_can_spawn_a_valid_saved_actor(self):
  tested=0
  for seed in world.rows('gachaVillager'):
   if int(seed['star']) not in {3,4,5,6}:continue
   state=world.build_bridge_world(session.fresh_tutorial(),1000);state['inventory']['323']=10000
   with self.subTest(base=seed['id']):
    collection.operate(state,'ClientVillagerService/CreateGachaVillager',{'GachaVillagerId':seed['id'],'GemCost':collection.shop_price(seed)},1000,self.owner,'p')
    world.validate_world(state);tested+=1
  self.assertGreater(tested,100)
if __name__=='__main__':unittest.main()
