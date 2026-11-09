import copy,json,unittest
import world,session,interactive,quests
class InteractiveTests(unittest.TestCase):
 def setUp(self):
  self.state=world.build_bridge_world(session.fresh_tutorial(),1000);self.state['inventory'].update({'72':100,'487':100})
  self.baby=next(p for p in self.state['world']['entities'] if p['id']=='brother');self.baby.update(startAge=0,templateId=3,bornAt=1000)
  self.data={'requesterVillagerId':'brother','supplierVillagerId':'steve','activityId':'1'}
 def test_original_baby_and_toddler_role_boundaries_both_genders(self):
  for gender in [0,1]:
   for age in [0,1,2,4,5,12,18]:
    self.baby.update(gender=gender,startAge=age)
    self.assertEqual(interactive.requester_eligible(self.baby,world.by_id('interactive_activity',1),1000),age<5)
 def test_correct_roles_costs_repeat_and_alternate_caregiver(self):
  interactive.generate(self.state,1000);response,_=interactive.perform(self.state,self.data,1001,'feed1')
  self.assertEqual(self.state['inventory']['487'],96);self.assertEqual(self.state['inventory']['72'],98);self.assertTrue(response['result']['SatisfiedWantModels'])
  before=copy.deepcopy(self.state);self.assertFalse(interactive.perform(self.state,self.data,1002,'another-id')[1]);self.assertEqual(before,self.state)
  with self.assertRaises(ValueError):interactive.perform(self.state,{**self.data,'supplierVillagerId':'jill'},1002,'feed2')
  self.assertEqual(before,self.state)
 def test_invalid_roles_and_shortages_do_not_mutate(self):
  for data in [{**self.data,'supplierVillagerId':'sister'},{**self.data,'supplierVillagerId':'brother'},{**self.data,'requesterVillagerId':'steve'},{**self.data,'activityId':'2'}]:
   before=copy.deepcopy(self.state)
   with self.assertRaises(ValueError):interactive.perform(self.state,data,1000,'x')
   self.assertEqual(before,self.state)
  self.state['inventory']['487']=3;before=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):interactive.perform(self.state,self.data,1000,'poor')
  self.assertEqual(before,self.state)
 def test_native_receipt_replay_returns_current_balances_after_reload(self):
  interactive.generate(self.state,1000);interactive.perform(self.state,self.data,1001,'feed')
  self.state=json.loads(json.dumps(self.state));self.state['inventory']['487']=1000;before=copy.deepcopy(self.state)
  result,changed=interactive.perform(self.state,self.data,1002,'feed');self.assertFalse(changed);self.assertEqual(before,self.state)
  self.assertEqual(next(v['amount'] for v in result['inventory'] if v['materialTypeId']==487),1000)
 def test_interactive_quest_requires_actual_completed_animation_and_replay_safe(self):
  kind=next(r for r in world.rows('quest_type') if r['targetObjectType']=='interactive_activity')
  result,_=quests.add(self.state,{'questTypeId':int(kind['id']),'objectId':'1','villagerId':'brother'},1000)
  request={'userQuestId':result['userQuest']['id']}
  interactive.perform(self.state,self.data,1001,'feed')
  with self.assertRaises(ValueError):quests.complete(self.state,request,1030)
  quests.complete(self.state,request,1031);before=copy.deepcopy(self.state);self.assertFalse(quests.complete(self.state,request,1032)[1]);self.assertEqual(before,self.state)
if __name__=='__main__':unittest.main()
