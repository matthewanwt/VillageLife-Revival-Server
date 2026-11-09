import copy,json,unittest
from decimal import Decimal,ROUND_CEILING
import shop,world
class ResourcePurchaseTests(unittest.TestCase):
 def test_observed_three_vines_cost_two_gems(self):
  self.assertEqual(shop.purchase_price(world.by_id('material_type',77),3),2)
  self.assertEqual(shop.purchase_price(world.by_id('material_type',77),1),1)
  self.assertEqual(shop.purchase_price(world.by_id('material_type',77),50),26)
 def test_all_original_positive_prices_and_quantity_boundaries(self):
  for definition in world.rows('material_type'):
   if Decimal(definition['gemsRatio'] or '0')<=0:continue
   low=max(1,int(definition['minPurchasable']));high=int(definition['maxPurchasable'])
   if high<low:continue
   for amount in sorted({low,high}):
    with self.subTest(material=definition['id'],amount=amount):
     cost=shop.purchase_price(definition,amount);self.assertGreater(cost,0)
     # Sanity against decimal ceiling; float32 can differ at large integer bounds.
     expected=int((Decimal(definition['gemsRatio'])*amount).to_integral_value(rounding=ROUND_CEILING));self.assertLessEqual(abs(cost-expected),max(2,expected*1e-6))
 def test_fractional_purchase_reload_and_replay_cannot_charge_twice(self):
  state={'inventory':{'323':10},'user':{'userLevelID':10},'revision':1};data={'materialTypeId':77,'amount':3}
  shop.buy(state,data,'purchase');self.assertEqual(state['inventory'],{'323':8,'77':3})
  state=json.loads(json.dumps(state));before=copy.deepcopy(state);self.assertFalse(shop.buy(state,data,'purchase')[1]);self.assertEqual(state,before)
 def test_insufficient_gems_bad_quantity_and_reused_id_never_spend(self):
  data={'materialTypeId':77,'amount':3};state={'inventory':{'323':1},'user':{'userLevelID':10},'revision':1};before=copy.deepcopy(state)
  with self.assertRaises(ValueError):shop.buy(state,data,'p')
  self.assertEqual(state,before);state['inventory']['323']=10;shop.buy(state,data,'p');before=copy.deepcopy(state)
  for invalid in [{**data,'amount':0},{**data,'amount':51},{**data,'amount':True},{**data,'amount':4}]:
   with self.assertRaises(ValueError):shop.buy(state,invalid,'p')
   self.assertEqual(state,before)
if __name__=='__main__':unittest.main()
