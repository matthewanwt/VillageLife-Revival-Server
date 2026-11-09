import copy,json,unittest
from unittest.mock import patch
import fortune,world,session,progression

class FortuneTests(unittest.TestCase):
 def state(self):return world.build_bridge_world(session.fresh_tutorial(),1000)
 def test_ftue_level_spin_is_authored_guaranteed_slot_and_amount(self):
  for _ in range(3):self.assertEqual(fortune.draw(6),{'ResultIndex':9,'MaterialTypes':[{'MaterialTypeId':323,'Amount':25}]})
 def test_every_authored_spin_slot_and_nested_pool_delivers_valid_reward(self):
  count=0
  for row in world.rows('WofSetItem'):
   if float(row['Chance'])<=0:continue
   def select(rows,field='Chance'):
    if field=='Chance':return row
    return rows[0]
   with patch.object(fortune,'choose',side_effect=select):
    model=fortune.draw(row['WofSet'],1.5)
   self.assertEqual(model['ResultIndex'],int(row['SlotIndex']));self.assertTrue(model['MaterialTypes'])
   for prize in model['MaterialTypes']:
    world.by_id('material_type',prize['MaterialTypeId']);self.assertGreater(prize['Amount'],0)
   count+=1
  self.assertGreater(count,75)
 def test_daily_spin_cooldown_reload_and_replay_never_duplicate(self):
  state=self.state();response,changed=fortune.operate(state,'ClientFortune/GetWOFSpinResult',{'WheelOfFortuneTypeID':1},1000,'spin1')
  self.assertTrue(changed);state=json.loads(json.dumps(state));before=copy.deepcopy(state)
  self.assertEqual(fortune.operate(state,'ClientFortune/GetWOFSpinResult',{'WheelOfFortuneTypeID':1},1001,'spin1'),(response,False));self.assertEqual(state,before)
  with self.assertRaises(ValueError):fortune.operate(state,'ClientFortune/GetWOFSpinResult',{'WheelOfFortuneTypeID':1},1001,'spin2')
  self.assertEqual(state,before)
  fortune.operate(state,'ClientFortune/GetWOFSpinResult',{'WheelOfFortuneTypeID':1,'Multiplier':999999,'WofSet':'1'},87400,'spin2')
  self.assertEqual(state['dailySpin']['increment'],2)
 def test_weekly_streak_and_missed_day_reset(self):
  state=self.state()
  for day in range(7):fortune.operate(state,'ClientFortune/GetWOFSpinResult',{'WheelOfFortuneTypeID':1},1000+day*86400,'day'+str(day))
  self.assertEqual(state['dailySpin']['increment'],7)
  fortune.operate(state,'ClientFortune/GetWOFSpinResult',{'WheelOfFortuneTypeID':1},1000+10*86400,'later');self.assertEqual(state['dailySpin']['increment'],1)
 def test_level_eight_charm_granted_at_eight_not_nine_and_replay_safe(self):
  state=self.state();state['user'].update(userLevelID=7,userLevel=7,xp=int(next(r['experienceRequired'] for r in world.rows('user_level') if r['levelNumber']=='7')))
  result,changed=progression.increase_level(state,{'IsPaid':'false'},'level8');self.assertTrue(changed)
  self.assertEqual(result['result']['Rewards'],[{'MaterialTypeId':2837,'Amount':1.0}]);self.assertEqual(state['user']['userLevelID'],8)
  self.assertIn('WheelOfFortuneModel',result['result']);before=copy.deepcopy(state)
  self.assertEqual(progression.increase_level(state,{'IsPaid':'false'},'level8'),(result,False));self.assertEqual(before,state)
 def test_old_deferred_spins_and_missing_milestone_repaired_once(self):
  state=self.state();state['user']['userLevelID']=8
  state['levelReceipts']={'2':{'result':{'Rewards':[]}},'8':{'result':{'Rewards':[]}}}
  state['pendingLevelBonuses']=[{'level':2,'status':'deferred_unrecovered_wheel_payout'}]
  gems=state['inventory']['323'];self.assertTrue(progression.reconcile_level_rewards(state))
  self.assertEqual(state['inventory']['323'],gems+25);self.assertEqual(state['inventory']['2837'],1)
  state=json.loads(json.dumps(state));before=copy.deepcopy(state);self.assertFalse(progression.reconcile_level_rewards(state));self.assertEqual(before,state)
 def test_old_late_milestone_is_not_given_twice(self):
  state=self.state();state['user']['userLevelID']=9
  state['levelReceipts']={'8':{'result':{'Rewards':[]}},'9':{'result':{'Rewards':[{'MaterialTypeId':2837,'Amount':1}]}}}
  before=copy.deepcopy(state);self.assertFalse(progression.reconcile_level_rewards(state));self.assertEqual(before,state)
 def test_level_two_spin_credited_and_saved_once(self):
  state=self.state();state['user']['xp']=36;before=state['inventory']['323']
  result,_=progression.increase_level(state,{},'level2');self.assertEqual(state['inventory']['323'],before+25)
  state=json.loads(json.dumps(state));progression.increase_level(state,{},'level2');self.assertEqual(state['inventory']['323'],before+25)
if __name__=='__main__':unittest.main()
