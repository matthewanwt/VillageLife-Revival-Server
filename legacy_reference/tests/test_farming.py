"""Recovered Script2434 farming RPC and original farm/plot definitions."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import buildings,session,tasks,world

class FarmingTests(unittest.TestCase):
 def setUp(self):
  self.state=world.build_bridge_world(session.fresh_tutorial(),1000)
  self.state['user'].update(userLevel=50,userLevelID=50,xp=372826)
  self.state['inventory']['323']=1000000
  self.point={'x':4000,'y':4000,'rotation':0,'areaId':1}
 def farm(self,tier=0):
  self.state['world']['entities'].append({'id':'farm','templateType':'farm_building','templateId':tier,'position':dict(self.point),'localCreated':True})
 def fund(self,ident):
  task=world.by_id('task',ident)
  for r in world.rows('requirement_set_item'):
   if r['requirementSet']==task['requirementSet'] and float(r['quantityUsed'])>0:self.state['inventory'][r['materialType']]=float(r['quantity'])+float(r['quantityUsed'])+1
  return task
 def plot(self):
  result,_=buildings.place(self.state,{'buildingTaskTypeId':9,**self.point})
  self.fund(144)
  start,_=tasks.start(self.state,{'villagerId':'steve','taskTypeId':144,**self.point},1000,'ClientTaskService/StartBuildingTask','plot')
  reply,_=tasks.harvest(self.state,{'workAreaId':start['workAreaId'],'taskTypeId':144},1060)
  return reply['objects'][0]['id']
 def test_build_plot_uses_real_xp_and_farm_milestone_without_stock_grant(self):
  self.farm();ident=self.plot();self.assertNotIn('7',self.state['inventory']);self.assertNotIn('231',self.state['inventory'])
  self.assertEqual(self.state['user']['xp'],372826)
  self.assertTrue(any(e['id']==ident and e['templateType']=='farming_plot' for e in world.area_content(self.state,1,1061)['areaJson']['entities']))
 def test_farm_capacity_reserves_foundations_and_retries_do_not_take_extra_slot(self):
  before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):buildings.place(self.state,{'buildingTaskTypeId':9,**self.point})
  self.assertEqual(self.state,before);self.farm()
  first,_=buildings.place(self.state,{'buildingTaskTypeId':9,**self.point})
  self.assertFalse(buildings.place(self.state,{'buildingTaskTypeId':9,**self.point})[1])
  with self.assertRaises(ValueError):buildings.place(self.state,{'buildingTaskTypeId':20,**{**self.point,'x':4200}})
  buildings.delete(self.state,{'userBuildingTaskId':first['userBuildingTask']['userBuildingTaskId']})
  self.assertTrue(buildings.place(self.state,{'buildingTaskTypeId':9,**self.point})[1])
 def test_all_five_original_farm_plot_limits(self):
  for tier in range(5):
   with self.subTest(tier=tier):
    self.setUp();self.farm(tier);capacity=int(world.by_id('farm_building',tier)['numPlots'])
    for i in range(capacity):buildings.place(self.state,{'buildingTaskTypeId':9,**{**self.point,'x':4000+i*100}})
    with self.assertRaises(ValueError):buildings.place(self.state,{'buildingTaskTypeId':9,**{**self.point,'x':6000}})
 def test_removed_visual_foundation_keeps_paid_plot_reservation_until_claim(self):
  self.farm();placed,_=buildings.place(self.state,{'buildingTaskTypeId':9,**self.point});self.fund(144)
  started,_=tasks.start(self.state,{'villagerId':'steve','taskTypeId':144,**self.point},1000,'ClientTaskService/StartBuildingTask','plot')
  buildings.delete(self.state,{'userBuildingTaskId':placed['userBuildingTask']['userBuildingTaskId']})
  snapshot=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):buildings.place(self.state,{'buildingTaskTypeId':20,**self.point})
  self.assertEqual(snapshot,self.state)
  tasks.harvest(self.state,{'workAreaId':started['workAreaId'],'taskTypeId':144},1060)
  self.assertEqual(sum(e['templateType']=='farming_plot' for e in self.state['world']['entities']),1)
 def test_all_284_original_crops_complete_reload_and_pay_once(self):
  base=copy.deepcopy(self.state);count=0
  for recipe in world.rows('farming_task'):
   with self.subTest(crop=recipe['materialType'],recipe=recipe['id']):
    self.state=copy.deepcopy(base);self.farm();plot=self.plot();task=self.fund(recipe['taskId'])
    data={'villagerId':'steve','taskTypeId':int(task['id']),'userFarmPlotId':plot,**self.point}
    start,_=tasks.start(self.state,data,1100,'ClientTaskService/StartFarmingTask','crop')
    with self.assertRaises(ValueError):tasks.harvest(self.state,{'workAreaId':start['workAreaId'],'taskTypeId':int(task['id'])},start['completionTime']-1)
    self.state=json.loads(json.dumps(self.state));before=copy.deepcopy(self.state['inventory'])
    req={'workAreaId':start['workAreaId'],'taskTypeId':int(task['id'])};tasks.harvest(self.state,req,start['completionTime'])
    for reward in world.rows('reward_set_item'):
     if reward['setId']==task['rewardSet']:self.assertAlmostEqual(self.state['inventory'][reward['materialType']]-before.get(reward['materialType'],0),float(reward['quantity']))
    snapshot=copy.deepcopy(self.state);self.assertFalse(tasks.harvest(self.state,req,start['completionTime']+1)[1]);self.assertFalse(tasks.start(self.state,data,start['completionTime']+2,'ClientTaskService/StartFarmingTask','crop')[1]);self.assertEqual(snapshot,self.state)
    count+=1
  self.assertEqual(count,284)
 def test_paid_crop_skip_replant_and_busy_plot_validation(self):
  self.farm();plot=self.plot();self.fund(29)
  data={'villagerId':'steve','taskTypeId':29,'userFarmPlotId':plot,**self.point}
  start,_=tasks.start(self.state,data,1100,'ClientTaskService/StartFarmingTask','crop1')
  snapshot=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):tasks.start(self.state,{**data,'villagerId':'jill'},1101,'ClientTaskService/StartFarmingTask','crop2')
  self.assertEqual(snapshot,self.state)
  req={'workAreaId':start['workAreaId'],'taskTypeId':29};balance=self.state['inventory']['323'];cost=tasks.instant_price(7199)
  tasks.instant_complete(self.state,req,1101);tasks.harvest(self.state,req,1101)
  self.assertEqual(self.state['inventory']['323'],balance-cost)
  self.fund(29);self.assertTrue(tasks.start(self.state,data,1102,'ClientTaskService/StartFarmingTask','crop3')[1])
 def test_authenticated_farming_route_commits_and_rejects_wrong_plot(self):
  self.farm();plot=self.plot();self.fund(29)
  with tempfile.TemporaryDirectory() as tmp,patch.object(session,'STATE',Path(tmp)),patch.object(session,'wire_time',return_value=1100):
   profile=session.login({'deviceId':'farm-route'})['data']['users'][0];path=session.profile_path('farm-route').with_suffix('.tutorial.json')
   session.atomic_json(path,{**session.fresh_tutorial(),'version':3,'normal':self.state,'gameSettings':{'activeSequenceId':'-1','isFtueComplete':'1'}})
   session.process({**profile,'data':{'calls':[{'id':'load','service':'ClientStartupService/GetAreaContent','data':{'areaId':1}}]}})
   def call(plot_id):return session.process({**profile,'data':{'calls':[{'id':plot_id,'service':'ClientTaskService/StartFarmingTask','data':{'villagerId':'steve','taskTypeId':29,'userFarmPlotId':plot_id,**self.point}}]}})['data']['calls'][0]
   before=path.read_bytes();self.assertEqual(call('unknown')['code'],400);self.assertEqual(path.read_bytes(),before)
   self.assertEqual(call(plot)['code'],200);self.assertTrue(json.loads(path.read_text())['normal']['workAreas'])

if __name__=='__main__':unittest.main()
