"""Focused checks for the gathering handler draft; no guest execution."""
import unittest,copy
import session,world,tasks
class GatheringDraftTests(unittest.TestCase):
 def setUp(self):
  self.state=world.build_bridge_world(session.fresh_tutorial(),1000)
  source=next(v for v in self.state['world']['entities'] if v.get('refId')=='Strawberries')
  self.data={'villagerId':'steve','userMaterialSourceId':source['id'],'taskTypeId':14,'x':1500,'y':3550,'rotation':0,'areaId':1}
 def test_start_uses_original_duration_and_fractional_basket_wear(self):
  response,changed=tasks.start(self.state,self.data,1000)
  self.assertTrue(changed);self.assertEqual(response['completionTime'],1030);self.assertEqual(response['villager']['id'],'steve');self.assertAlmostEqual(self.state['inventory']['111'],0.9)
 def test_repeated_start_returns_same_job_and_does_not_spend_twice(self):
  first,_=tasks.start(self.state,self.data,1000);before=copy.deepcopy(self.state)
  second,changed=tasks.start(self.state,self.data,1010)
  self.assertFalse(changed);self.assertEqual(first,second);self.assertEqual(self.state,before)
 def test_busy_source_and_baby_are_rejected(self):
  tasks.start(self.state,self.data,1000)
  with self.assertRaises(ValueError):tasks.start(self.state,{**self.data,'villagerId':'jill'},1001)
  with self.assertRaises(ValueError):tasks.start(self.state,{**self.data,'villagerId':'baby male'},1001)
 def test_early_harvest_rejected_and_reward_paid_once(self):
  start,_=tasks.start(self.state,self.data,1000);request={'workAreaId':start['workAreaId'],'taskTypeId':14};before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):tasks.harvest(self.state,request,1029)
  self.assertEqual(self.state,before);balance=self.state['inventory'].get('107',0)
  response,changed=tasks.harvest(self.state,request,1030);self.assertTrue(changed);self.assertEqual(self.state['inventory']['107'],balance+25)
  after=copy.deepcopy(self.state);again,changed=tasks.harvest(self.state,request,1040)
  self.assertFalse(changed);self.assertEqual(response,again);self.assertEqual(self.state,after)
 def test_completed_uncollected_job_frees_villager_but_retains_harvest(self):
  start,_=tasks.start(self.state,self.data,1000)
  import world
  source=next(v for v in self.state['world']['entities'] if v.get('templateType')=='material_source' and v['templateId']==next(int(r['id']) for r in world.rows('material_source') if r['task']=='235'))
  data={'villagerId':'steve','userMaterialSourceId':source['id'],'taskTypeId':235,**source['position']}
  new,changed=tasks.start(self.state,data,1030);self.assertTrue(changed);self.assertEqual(self.state['workAreas'][start['workAreaId']]['status'],'ready')
  self.assertNotEqual(start['workAreaId'],new['workAreaId']);world.validate_world(self.state)
  old_overlay=next(v for v in tasks.work_overlay(self.state,1030) if v['id']==start['workAreaId']);self.assertEqual(old_overlay['villagerId'],'')
  request={'workAreaId':start['workAreaId'],'taskTypeId':14};before=self.state['inventory'].get('107',0)
  tasks.harvest(self.state,request,1030);self.assertEqual(self.state['inventory']['107'],before+25)
  tasks.harvest(self.state,request,1031);self.assertEqual(self.state['inventory']['107'],before+25)
 def test_mismatched_task_cannot_spend_materials(self):
  before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):tasks.start(self.state,{**self.data,'taskTypeId':6},1000)
  self.assertEqual(self.state,before)
if __name__=='__main__':unittest.main()
