import copy,unittest
from unittest.mock import patch
import feature_audit as audit
class AuditChecks(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.base=audit.world.build_bridge_world(audit.session.fresh_tutorial(),1000);cls.task=audit.world.by_id('task',14)
 def test_gather_fixture_checks_restart_and_duplicate_collection(self):
  before=copy.deepcopy(self.base);result=audit.exercise_task(self.task,None,self.base)
  self.assertEqual(result['status'],'passed_server_fixture');self.assertIn('reload_then_original_rewards',result['checks']);self.assertEqual(self.base,before)
 def test_unimplemented_family_is_never_a_pass(self):
  result=audit.exercise_task({**self.task,'taskType':'9'},None,self.base);self.assertEqual(result['status'],'not_implemented')
 def test_zero_duration_mountain_workshop_is_replay_safe(self):
  task=audit.world.by_id('task',831);variant=audit.world.by_id('building_task',243)
  result=audit.exercise_task(task,variant,self.base)
  self.assertEqual(result['status'],'passed_server_fixture',result)
 def test_empty_policy_is_never_implemented_gameplay(self):
  self.assertEqual(audit.classify({'policy_disabled_or_empty':True,'handler_declared':True,'regression_tests':['a']}),'disabled_or_empty_policy')
 def test_failed_duplicate_protection_is_detected(self):
  original=audit.tasks.harvest
  def broken(state,data,at):
   result,changed=original(state,data,at)
   if not changed:state['inventory']['107']+=1
   return result,changed
  with patch.object(audit.tasks,'harvest',broken):result=audit.exercise_task(self.task,None,self.base)
  self.assertEqual(result['status'],'failed');self.assertIn('Repeated harvest',result['reason'])
if __name__=='__main__':unittest.main()
