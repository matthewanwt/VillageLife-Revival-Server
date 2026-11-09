import copy,json,unittest
from unittest.mock import patch
import world,session,charms,collection,family
class CharmTests(unittest.TestCase):
 def setUp(self):
  self.state=world.build_bridge_world(session.fresh_tutorial(),2000000);self.state['user']['populationCap']=1000;self.state['inventory'].update({'323':100000,'2937':3,'2837':1})
 def test_bought_pack_original_cost_persisted_draw_and_no_reroll(self):
  before=len(family.actors(self.state));response,changed=charms.operate(self.state,'ClientFortune/Gacha',{'CharmSetID':'13'},2000000,'1','buy')
  self.assertTrue(changed);self.assertEqual(self.state['inventory']['323'],99970);self.assertEqual(len(response['result']),1);self.assertGreaterEqual(len(family.actors(self.state)),before+1)
  self.state=json.loads(json.dumps(self.state));snapshot=copy.deepcopy(self.state)
  with patch.object(charms,'pick_reward',side_effect=AssertionError('rerolled')):
   self.assertEqual(charms.operate(self.state,'ClientFortune/Gacha',{'CharmSetID':'13'},2000001,'1','buy'),(response,False))
  self.assertEqual(snapshot,self.state);world.validate_world(self.state)
 def test_owned_hero_consumes_one_token_and_awards_original_villager(self):
  gems=self.state['inventory']['323'];response,_=charms.operate(self.state,'ClientFortune/ConsumeGacha',{'CharmSetID':'98'},2000000,'1','earned')
  self.assertEqual(self.state['inventory']['2837'],0);self.assertEqual(self.state['inventory']['323'],gems)
  people=[v for g in response['result'] for r in g for v in r.get('Villagers',[])]
  self.assertEqual(len(people),1);self.assertEqual(collection.definition(people[0]['villagerBaseId'])['pool'] in {'24','25'},True)
  self.assertGreater(people[0]['VillagerId'],0);self.assertLess(people[0]['BornAt'],2000000)
 def test_invalid_free_baby_shortage_or_capacity_does_not_change_save(self):
  for service,data in [('Gacha',{'CharmSetID':'98'}),('Gacha',{'CharmSetID':'1'}),('ConsumeGacha',{'CharmSetID':'16'}),('Gacha',{'CharmSetID':'13','VillagerStringId':'steve'})]:
   before=copy.deepcopy(self.state)
   with self.assertRaises(ValueError):charms.operate(self.state,'ClientFortune/'+service,data,2000000,'1','invalid')
   self.assertEqual(before,self.state)
  self.state['user']['populationCap']=len(family.actors(self.state));before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):charms.operate(self.state,'ClientFortune/Gacha',{'CharmSetID':'13'},2000000,'1','full')
  self.assertEqual(before,self.state)
 def test_real_original_pool_types_material_single_and_couple(self):
  for kind in ['0','1','2']:
   pool=next(r for r in world.rows('runeRewardPoolProb') if r['poolType']==kind and float(r['probability'])>0)
   original=charms.fortune.choose
   def choose(rows,field='Chance'):
    rows=list(rows)
    if rows and 'poolType' in rows[0]:return pool
    return original(rows,field)
   with patch.object(charms.fortune,'choose',choose):result=charms.pick_reward(pool['runeRewardSet'])
   if kind=='1':self.assertTrue(all('Material' in r for r in result))
   else:self.assertEqual(len(result[0]['Villagers']),1 if kind=='0' else 2)
 def test_all_original_hud_pack_definitions_produce_valid_worlds(self):
  count=0
  for item in world.rows('runeSetItem'):
   try:_,group=charms.sku(item['id'])
   except ValueError:continue
   if int(item['gemCost'])<=0:continue
   state=copy.deepcopy(self.state)
   with self.subTest(pack=item['id']):
    charms.operate(state,'ClientFortune/Gacha',{'CharmSetID':item['id']},2000000000,'1','matrix')
    world.validate_world(state);count+=1
  self.assertGreater(count,40)
 def test_collection_spawn_age_matches_native_zero_starting_age(self):
  seed=collection.definition(200);person=collection.spawn(self.state,seed,2000000)
  self.assertEqual(person['startAge'],0);self.assertEqual(world.current_age(person,2000000),18)
if __name__=='__main__':unittest.main()
