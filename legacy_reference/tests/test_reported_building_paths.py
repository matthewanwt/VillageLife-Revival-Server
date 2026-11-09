import copy,json,unittest
import world,session,tasks,buildings
class ReportedBuildingTests(unittest.TestCase):
 def setUp(self):self.state=world.build_bridge_world(session.fresh_tutorial(),1000)
 def fund(self,task):
  for req in world.rows('requirement_set_item'):
   if req['requirementSet'] in {task['requirementSet'],task['levelRequirement']}:self.state['inventory'][req['materialType']]=10000
 def test_grass_gathering_uses_original_tools_timer_and_replay(self):
  definition=world.by_id('task',31);self.fund(definition)
  source_type=next(v for v in world.rows('material_source') if v['task']=='31')
  source=next(v for v in self.state['world']['entities'] if v['templateType']=='material_source' and v['templateId']==int(source_type['id']))
  data={'villagerId':'steve','userMaterialSourceId':source['id'],'taskTypeId':31,**source['position']}
  started,_=tasks.start(self.state,data,1000);self.assertEqual(started['completionTime'],1120)
  req={'workAreaId':started['workAreaId'],'taskTypeId':31};tasks.harvest(self.state,req,1120)
  before=copy.deepcopy(self.state);self.assertFalse(tasks.harvest(self.state,req,1121)[1]);self.assertEqual(before,self.state)
 def test_original_storage_placeholder_and_entire_upgrade_chain_keep_one_identity(self):
  storage=next(e for e in self.state['world']['entities'] if e['templateType']=='container_type' and e['templateId']==3)
  original_id=storage['id'];point=storage['position'];at=1000
  for foundation_id in [54,55,56,57]:
   foundation=world.by_id('building_task',foundation_id);task=world.by_id('task',foundation['taskId']);self.fund(task)
   building=world.by_id('building_type',foundation['buildingType'])
   self.state['inventory'].pop(building['materialType'],None)
   if task['taskType']=='2':buildings.place(self.state,{'buildingTaskTypeId':str(foundation_id),**point})
   result,_=tasks.start(self.state,{'villagerId':'steve','taskTypeId':int(task['id']),**point},at,'ClientTaskService/StartBuildingTask')
   request={'workAreaId':result['workAreaId'],'taskTypeId':int(task['id'])};tasks.harvest(self.state,request,result['completionTime'])
   self.state=json.loads(json.dumps(self.state));current=next(e for e in self.state['world']['entities'] if e['id']==original_id)
   self.assertEqual(current['templateId'],int(building['entityID']));self.assertEqual(current['position'],point)
   self.assertEqual(sum(e['templateType']=='container_type' and e['id']==original_id for e in self.state['world']['entities']),1)
   before=copy.deepcopy(self.state);self.assertFalse(tasks.harvest(self.state,request,result['completionTime']+1)[1]);self.assertEqual(before,self.state)
   world.validate_world(self.state);at=result['completionTime']+1
if __name__=='__main__':unittest.main()
