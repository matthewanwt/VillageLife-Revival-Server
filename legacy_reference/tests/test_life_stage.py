import copy,unittest
import world,session,tasks,habitats
class LifeStageTests(unittest.TestCase):
 def setUp(self):self.state=world.build_bridge_world(session.fresh_tutorial(),1000);self.actor=next(e for e in self.state['world']['entities'] if e['id']=='sister')
 def test_all_normal_age_boundaries_for_both_genders(self):
  stages=[(0,3,4,False),(1,3,4,False),(2,16,17,False),(4,16,17,False),(5,10,11,False),(12,10,11,False),(13,12,13,True),(17,12,13,True),(18,1,5,True),(39,1,5,True),(40,6,8,True),(54,6,8,True),(55,7,9,True),(74,7,9,True),(75,14,15,True)]
  for age,male,female,works in stages:
   for gender,expected in [(0,male),(1,female)]:
    with self.subTest(age=age,gender=gender):
     actor={**self.actor,'startAge':age,'gender':gender};self.assertEqual(int(world.current_villager_type(actor,1000)['id']),expected);self.assertEqual(world.can_work(actor,1000),works)
 def test_elapsed_year_crosses_thirteen_without_changing_identity_or_birth_time(self):
  before=copy.deepcopy(self.actor);self.assertFalse(world.can_work(self.actor,87399));self.assertTrue(world.can_work(self.actor,87400));self.assertEqual(self.actor,before)
 def test_pregnant_life_stages_cannot_work(self):
  for age,expected in [(18,2),(40,18),(55,19),(80,19)]:
   person={**self.actor,'startAge':age,'pregnant':'true'};self.assertEqual(int(world.current_villager_type(person,1000)['id']),expected);self.assertFalse(world.can_work(person,1000))
 def test_special_infant_appearance_and_dog_are_preserved(self):
  person={**self.actor,'templateId':21,'startAge':0};self.assertEqual(world.current_villager_type(person,1000)['id'],'21');self.assertFalse(world.can_work(person,1000))
  person['templateId']=40;self.assertEqual(world.current_villager_type(person,100000)['id'],'40')
 def fund(self):
  for req in world.rows('requirement_set_item'):self.state['inventory'][req['materialType']]=max(self.state['inventory'].get(req['materialType'],0),float(req['quantity'])+float(req['quantityUsed'])+100)
 def test_observed_flint_well_accepts_aged_mary_and_rejects_same_character_before_transition(self):
  self.fund();definition=next(v for v in world.rows('building_task') if v['taskId']=='163');point={'x':4000,'y':4000,'rotation':0,'areaId':1};self.state['world']['entities'].append({'id':'test-well-foundation','templateType':'building_task','templateId':int(definition['id']),'position':point,'serverPersisted':True})
  data={'villagerId':self.actor['id'],'taskTypeId':163,**point}
  with self.assertRaises(ValueError):tasks.start(copy.deepcopy(self.state),data,1000,'ClientTaskService/StartBuildingTask')
  response,changed=tasks.start(self.state,data,87400,'ClientTaskService/StartBuildingTask');self.assertTrue(changed);self.assertEqual(response['villager']['id'],'sister');world.validate_world(self.state)
 def test_aged_character_can_light_fire_using_same_shared_rule(self):
  self.fund();fire=next(e for e in self.state['world']['entities'] if e['templateType']=='fire_type');data={'userFireId':fire['id'],'villagerId':'sister'}
  with self.assertRaises(ValueError):habitats.start_fire(copy.deepcopy(self.state),data,1000)
  self.assertTrue(habitats.start_fire(self.state,data,87400)[1])
 def test_login_and_area_project_current_age_without_rewriting_saved_birth_data(self):
  for age,male,female in [(0,3,4),(2,16,17),(5,10,11),(13,12,13),(18,1,5),(40,6,8),(55,7,9),(75,14,15)]:
   for gender,expected in [(0,male),(1,female)]:
    with self.subTest(age=age,gender=gender):
     person=next(e for e in self.state['world']['entities'] if e['id']=='baby male')
     person.update(templateId=3 if gender==0 else 4,startAge=age,gender=gender)
     before=copy.deepcopy(self.state)
     startup=world.startup(self.state,1000)['world']['entities'];area=world.area_content(self.state,1,1000)['areaJson']['entities']
     for entities in [startup,area]:self.assertEqual(next(e['templateId'] for e in entities if e['id']==person['id']),expected)
     self.assertEqual(self.state,before)

if __name__=='__main__':unittest.main()
