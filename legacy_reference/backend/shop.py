"""In-game gem purchases using original float32 consumable pricing; no real payments."""
from decimal import Decimal
import math,struct
import world,tasks

def f32(value):return struct.unpack('<f',struct.pack('<f',value))[0]

def purchase_price(definition,amount):
 # Script2024 GetConsumableSkipCost: VMLA/floor with literal0x3f7d70a4.
 # VariantsModelParse sets ConsumableUpper/Lower multiplier to1.0 by default;
 # this restoration supplies no experimental variants.
 ratio=f32(float(definition['gemsRatio'] or '0'));epsilon=struct.unpack('<f',bytes.fromhex('a4707d3f'))[0]
 if not math.isfinite(ratio) or ratio<=0:raise NotImplementedError('Material has no recovered direct gem price')
 quantity=f32(math.floor(f32(f32(amount)+epsilon)))
 base=f32(math.floor(f32(epsilon+f32(ratio*quantity))))
 price=math.floor(f32(epsilon+f32(base*1.0)))
 if price<=0:raise NotImplementedError('Original calculation gives no positive direct gem price')
 return price

def response(state):
 items=tasks.inventory(state)
 return {'inventory':items,'userMaterialTypes':items,'result':{'inventory':items,'userMaterialTypes':items}}
def buy(state,data,receipt_key):
 ident=data.get('materialTypeId');amount=data.get('amount')
 if isinstance(ident,bool) or not isinstance(ident,int) or isinstance(amount,bool) or not isinstance(amount,int):raise ValueError('Integer material and quantity required')
 try:definition=world.by_id('material_type',ident)
 except StopIteration:raise ValueError('Unknown shop material') from None
 if not int(definition['minPurchasable'])<=amount<=int(definition['maxPurchasable']):raise ValueError('Quantity outside original purchase bounds')
 price=purchase_price(definition,amount)
 if int(definition['unlockLevel'])>state['user']['userLevelID']:raise ValueError('Material not unlocked at this level')
 if not receipt_key:raise ValueError('Purchase call identifier required')
 previous=state.get('purchaseReceipts',{}).get(receipt_key)
 if previous:
  if previous['materialTypeId']!=ident or previous['amount']!=amount:raise ValueError('Purchase call identifier reused with different content')
  return response(state),False
 # Original material table: 323 is Gems; 72 is Pine (not currency).
 gems='323'
 if world.by_id('material_type',gems)['name']!='Gems':raise ValueError('Original gem currency definition mismatch')
 if Decimal(str(state['inventory'].get(gems,0)))<price:raise ValueError('Not enough gems')
 state['inventory'][gems]=float(Decimal(str(state['inventory'][gems]))-price)
 state['inventory'][str(ident)]=state['inventory'].get(str(ident),0)+amount
 state.setdefault('purchaseReceipts',{})[receipt_key]={'materialTypeId':ident,'amount':amount,'gemsSpent':int(price),'evidence':'original Script2024 float32 floor(amount+.99), floor(ratio*quantity+.99), floor(price*default_variant1+.99)'}
 state['revision']+=1
 return response(state),True


def buy_store(state,data,receipt_key):
 ident=data.get('storeItemId');multiples=data.get('multiples')
 if isinstance(ident,bool) or not isinstance(ident,int) or isinstance(multiples,bool) or not isinstance(multiples,int) or not 1<=multiples<=100:raise ValueError('Store item and bounded positive multiples required')
 try:item=world.by_id('store_item',ident)
 except StopIteration:raise ValueError('Unknown original store item') from None
 if not receipt_key:raise ValueError('Store purchase receipt required')
 previous=state.get('storePurchaseReceipts',{}).get(receipt_key)
 if previous:
  if previous['storeItemId']!=ident or previous['multiples']!=multiples:raise ValueError('Store receipt reused for a different purchase')
  return response(state),False
 cost=int(item['price_gems'])*multiples;amount=int(item['qty'])*multiples;material=item['material_type']
 if cost<=0 or amount<=0:raise ValueError('Invalid original store definition')
 if state['inventory'].get('323',0)<cost:raise ValueError('Not enough gems for this store item')
 state['inventory']['323']-=cost;state['inventory'][material]=state['inventory'].get(material,0)+amount
 state.setdefault('storePurchaseReceipts',{})[receipt_key]={'storeItemId':ident,'multiples':multiples,'gemsSpent':cost,'materialTypeId':int(material),'amount':amount}
 state['revision']+=1
 return response(state),True


def sell(state,data,receipt_key):
 ident=data.get('materialTypeId');amount=data.get('amount')
 if isinstance(ident,bool) or not isinstance(ident,int) or isinstance(amount,bool) or not isinstance(amount,int) or amount<=0:raise ValueError('Positive integer sale quantity required')
 if not receipt_key:raise ValueError('Sale receipt required')
 previous=state.get('saleReceipts',{}).get(receipt_key)
 if previous:
  if previous['materialTypeId']!=ident or previous['amount']!=amount:raise ValueError('Sale receipt reused')
  return response(state),False
 try:definition=world.by_id('material_type',ident)
 except StopIteration:raise ValueError('Unknown original sale material') from None
 ratio=int(definition['coinsRatio'] or 0)
 if ratio<=0 or ident in {323,325}:raise ValueError('This original material cannot be sold for coins')
 if state['inventory'].get(str(ident),0)<amount:raise ValueError('Not enough material to sell')
 coins=ratio*amount;state['inventory'][str(ident)]-=amount;state['inventory']['325']=state['inventory'].get('325',0)+coins
 state.setdefault('saleReceipts',{})[receipt_key]={'materialTypeId':ident,'amount':amount,'coinsGranted':coins,'evidence':'Script2006 original integer unit coinsRatio multiplied by quantity; currency material325'}
 state['revision']+=1;return response(state),True
