import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import world,session,learning,tasks

class LearningTests(unittest.TestCase):
 def setUp(self):
  self.state=world.build_bridge_world(session.fresh_tutorial(),1000)
  self.state['user']['userLevelID']=100;self.state['areaId']=10;self.state['inventory']['323']=1000
 def call(self,method,ident=178,at=1000):return learning.operate(self.state,'ClientMaterialService/'+method+'LearningMaterial',{'materialTypeId':ident},at)
 def test_start_persists_locked_zero_stock_and_does_not_duplicate_timer(self):
  result,changed=self.call('Start');self.assertTrue(changed);self.assertEqual(result['result']['UpdatedTime'],1000)
  material=next(r for r in result['inventory'] if r['materialTypeId']==178);self.assertFalse(material['isUnlocked']);self.assertEqual(material['amount'],0)
  self.state=json.loads(json.dumps(self.state));before=copy.deepcopy(self.state)
  self.assertFalse(self.call('Start',at=1010)[1]);self.assertEqual(before,self.state)
 def test_natural_completion_boundary_restart_and_repeat(self):
  self.call('Start');before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):self.call('Complete',at=1059)
  self.assertEqual(before,self.state);self.state=json.loads(json.dumps(self.state))
  result,changed=self.call('Complete',at=1060);self.assertTrue(changed);self.assertTrue(learning.unlocked(self.state,178));self.assertEqual(self.state['inventory']['323'],1000)
  before=copy.deepcopy(self.state);self.assertFalse(self.call('Complete',at=2000)[1]);self.assertEqual(before,self.state)
  self.assertTrue(next(x for x in tasks.inventory(self.state) if x['materialTypeId']==178)['isUnlocked'])
 def test_skip_cost_once_and_no_stock_grant(self):
  self.call('Start');cost=learning.price(59);self.call('Skip',at=1001)
  self.assertEqual(self.state['inventory']['323'],1000-cost);self.assertNotIn('178',self.state['inventory'])
  self.state=json.loads(json.dumps(self.state));before=copy.deepcopy(self.state)
  self.assertFalse(self.call('Skip',at=1002)[1]);self.assertEqual(before,self.state)
 def test_bad_inputs_and_failed_purchases_do_not_mutate(self):
  for ident in [True,0,-1,999999,'178',107]:
   before=copy.deepcopy(self.state)
   with self.assertRaises(ValueError):self.call('Start',ident)
   self.assertEqual(before,self.state)
  self.call('Start');self.state['inventory']['323']=0;before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):self.call('Skip',at=1001)
  self.assertEqual(before,self.state)
 def test_level_parent_and_slot_limits(self):
  self.state['user']['userLevelID']=1
  with self.assertRaises(ValueError):self.call('Start')
  self.state['user']['userLevelID']=100
  with self.assertRaises(ValueError):self.call('Start',18)
  # Fund all original requirements without granting the material being learned.
  for req in world.rows('requirement_set_item'):self.state['inventory'][req['materialType']]=max(self.state['inventory'].get(req['materialType'],0),float(req['quantity'])+100)
  self.state['inventory'].pop('178',None)
  self.state['materialLearning']={str(i):{'status':'learning','seasonal':False} for i in [991,992,993]}
  with self.assertRaises(ValueError):self.call('Start')
 def test_legacy_inventory_unlocks_are_preserved(self):
  self.state['inventory']['178']=0;before=copy.deepcopy(self.state)
  self.assertTrue(learning.unlocked(self.state,178));self.assertFalse(self.call('Start')[1]);self.assertEqual(before,self.state)
 def test_all_authored_learning_materials_start_complete_and_reload(self):
  count=0
  for definition in world.rows('material_type'):
   ident=int(definition['id']);duration=int(definition['learnDurationSec'])
   if ident<=0 or duration<=0:continue
   with self.subTest(material=ident):
    state={'inventory':{'323':100000},'user':{'userLevelID':1000000000},'areaId':100,'revision':1}
    for req in learning.requirements(ident):
     if req['materialType']=='7':state['user']['xp']=float(req['quantity'])+100
     else:state['inventory'][req['materialType']]=float(req['quantity'])+100
    state['inventory'].pop(str(ident),None)
    parent=int(definition['parentID'])
    if parent>0:state.setdefault('materialLearning',{})[str(parent)]={'status':'unlocked'}
    learning.operate(state,'ClientMaterialService/StartLearningMaterial',{'materialTypeId':ident},1000)
    state=json.loads(json.dumps(state))
    learning.operate(state,'ClientMaterialService/CompleteLearningMaterial',{'materialTypeId':ident},1000+duration)
    self.assertTrue(learning.unlocked(state,ident));count+=1
  self.assertEqual(count,649)
 def test_authenticated_learning_routes_persist_and_do_not_leak_to_other_player(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(session,'STATE',Path(tmp)),patch.object(session,'wire_time',return_value=1000):
   profile=session.login({'deviceId':'learning-test'})['data']['users'][0]
   state=world.build_bridge_world(session.fresh_tutorial(),1000);state['user']['userLevelID']=3
   saved={'version':3,**session.fresh_tutorial(),'normal':state,'gameSettings':{'activeSequenceId':'-1'}}
   session.atomic_json(session.profile_path(profile['deviceId']).with_suffix('.tutorial.json'),saved)
   req={**profile,'data':{'calls':[{'id':1,'service':'ClientMaterialService/StartLearningMaterial','data':{'materialTypeId':178}}]}}
   self.assertEqual(session.process(req)['data']['calls'][0]['code'],200)
   saved=json.loads(session.profile_path(profile['deviceId']).with_suffix('.tutorial.json').read_text())
   self.assertEqual(saved['normal']['materialLearning']['178']['startedAt'],1000)
   self.assertEqual(session.process({**req,'sessionId':'wrong'})['data']['calls'][0]['code'],403)
 def test_all_authored_learning_paid_skip_is_once_after_reload(self):
  count=0
  for definition in world.rows('material_type'):
   ident=int(definition['id']);duration=int(definition['learnDurationSec'])
   if ident<=0 or duration<=0:continue
   with self.subTest(material=ident):
    state={'inventory':{'323':100000},'user':{'userLevelID':1000000000},'areaId':100,'revision':1}
    for req in learning.requirements(ident):
     if req['materialType']=='7':state['user']['xp']=float(req['quantity'])+100
     else:state['inventory'][req['materialType']]=float(req['quantity'])+100
    state['inventory'].pop(str(ident),None)
    if int(definition['parentID'])>0:state['materialLearning']={definition['parentID']:{'status':'unlocked'}}
    learning.operate(state,'ClientMaterialService/StartLearningMaterial',{'materialTypeId':ident},1000)
    before=state['inventory']['323'];cost=learning.price(duration-1)
    state=json.loads(json.dumps(state))
    learning.operate(state,'ClientMaterialService/SkipLearningMaterial',{'materialTypeId':ident},1001)
    self.assertEqual(state['inventory']['323'],before-cost);self.assertTrue(learning.unlocked(state,ident))
    state=json.loads(json.dumps(state));snapshot=copy.deepcopy(state)
    self.assertFalse(learning.operate(state,'ClientMaterialService/SkipLearningMaterial',{'materialTypeId':ident},1002)[1]);self.assertEqual(state,snapshot);count+=1
  self.assertEqual(count,649)
if __name__=='__main__':unittest.main()
