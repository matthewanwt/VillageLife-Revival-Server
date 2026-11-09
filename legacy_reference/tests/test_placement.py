import copy,json,unittest
import world,session,placement,shop,buildings,tasks
class PlacementTests(unittest.TestCase):
 def setUp(self):
  self.state=world.build_bridge_world(session.fresh_tutorial(),1000);self.state['inventory'].update({'323':100000,'325':100000})
  for r in world.rows('requirement_set_item'):self.state['inventory'][r['materialType']]=max(self.state['inventory'].get(r['materialType'],0),float(r['quantity'])+100)
 def place(self,ident,key='place',x=4000):return placement.operate(self.state,'ClientUserDecorItemService/CreateUserDecorItem',{'decorItemId':ident,'areaId':1,'x':x,'y':4000,'rotation':0},key)
 def test_path_place_move_reload_and_duplicate_are_persistent(self):
  definition=next(r for r in world.rows('decor_item') if 'path' in world.by_id('material_type',r['material_type'])['name'].lower() and r['hidden']=='0')
  material=definition['material_type'];self.state['inventory'][material]=0;before=copy.deepcopy(self.state['inventory'])
  result,_=self.place(int(definition['id']));record=result['userDecorItem'];self.assertEqual(self.state['inventory']['325'],before['325']-int(definition['price_coins']));self.assertEqual(self.state['inventory']['323'],before['323']-int(definition['price_gems']))
  self.state=json.loads(json.dumps(self.state));snapshot=copy.deepcopy(self.state);self.assertFalse(self.place(int(definition['id']))[1]);self.assertEqual(snapshot,self.state)
  point={'positionId':record['position']['id'],'x':4050,'y':4100,'rotation':90,'areaId':1}
  placement.operate(self.state,'ClientUtilityService/UpdatePosition',point,'move');self.state=json.loads(json.dumps(self.state));entity=next(e for e in self.state['world']['entities'] if e['id']==record['userDecorItemId']);self.assertEqual(entity['position']['x'],4050)
  self.assertFalse(placement.operate(self.state,'ClientUtilityService/UpdatePosition',point,'move')[1]);world.validate_world(self.state)
 def test_owned_decoration_spent_once_no_extra_currency_charge(self):
  definition=world.by_id('decor_item',0);self.state['inventory'][definition['material_type']]=1;coins=self.state['inventory']['325'];self.place(0)
  self.assertEqual(self.state['inventory'][definition['material_type']],0);self.assertEqual(self.state['inventory']['325'],coins)
 def test_invalid_position_cannot_create_or_move_unknown_object(self):
  before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):self.place(0,x=float('nan'))
  with self.assertRaises(ValueError):placement.operate(self.state,'ClientUtilityService/UpdatePosition',{'positionId':'missing','x':4000,'y':4000,'areaId':1},'move')
  self.assertEqual(before,self.state)
 def test_silver_sale_reloads_and_never_grants_twice(self):
  self.state['inventory']['107']=10;before=self.state['inventory']['325'];definition=world.by_id('material_type',107)
  request={'materialTypeId':107,'amount':3};shop.sell(self.state,request,'sale');self.assertEqual(self.state['inventory']['325'],before+int(definition['coinsRatio'])*3)
  self.state=json.loads(json.dumps(self.state));snapshot=copy.deepcopy(self.state);self.assertFalse(shop.sell(self.state,request,'sale')[1]);self.assertEqual(snapshot,self.state)
 def test_editable_position_projection_is_stable_and_does_not_change_save(self):
  before=copy.deepcopy(self.state);first=world.area_content(self.state,1,1000);second=world.area_content(self.state,1,1000)
  entities=[e for e in first['areaJson']['entities'] if e['templateType'] in placement.EDITABLE]
  self.assertTrue(all(e['position']['id'] for e in entities));self.assertEqual(first,second);self.assertEqual(before,self.state)
 def test_authored_workshop_can_be_rebuilt_without_duplicate_world_identity(self):
  old=next(e for e in self.state['world']['entities'] if e['templateType']=='workshop' and e['templateId']==0);ident=old['id'];point=copy.deepcopy(old['position']);self.state['inventory']['225']=0
  buildings.place(self.state,{'buildingTaskTypeId':81,**point});start,_=tasks.start(self.state,{'villagerId':'steve','taskTypeId':227,**point},1000,'ClientTaskService/StartBuildingTask');tasks.harvest(self.state,{'workAreaId':start['workAreaId'],'taskTypeId':227},start['completionTime'])
  current=[e for e in self.state['world']['entities'] if e['templateType']=='workshop' and e['templateId']==0];self.assertEqual(len(current),1);self.assertEqual(current[0]['id'],ident);self.assertEqual(current[0]['position'],point)
 def test_original_zero_second_workshop_can_complete_at_start_time(self):
  foundation=world.by_id('building_task',243);point={'x':4000,'y':4000,'rotation':0,'areaId':1};self.state['world']['entities'].append({'id':'zero-workshop','templateType':'building_task','templateId':243,'serverPersisted':True,'position':point})
  start,_=tasks.start(self.state,{'villagerId':'steve','taskTypeId':831,**point},1000,'ClientTaskService/StartBuildingTask');self.assertEqual(start['completionTime'],1000)
  tasks.harvest(self.state,{'workAreaId':start['workAreaId'],'taskTypeId':831},1000);world.validate_world(self.state)
if __name__=='__main__':unittest.main()
