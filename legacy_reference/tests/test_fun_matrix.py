"""Table-wide completion contracts; native pathfinding is tested separately."""
import copy,json,unittest
import world,session,fun,needs

class FunMatrixTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.seed=world.build_bridge_world(session.fresh_tutorial(),1000)
  cls.types=world.rows('villager_type')
  cls.members=world.rows('villager_set_item')

 def fixture(self,building,typ):
  state=copy.deepcopy(self.seed);person=fun.actor(state,'steve')
  person.update(templateId=int(typ['id']),gender=int(typ['genderType']),startAge=int(typ['minAge']),pregnant='true' if typ['isPregnant']=='1' else 'false',xp=0,energyLevel=int(typ['maxEnergy']))
  item={'id':'matrix-fun','templateType':'fun_building','templateId':int(building['id']),'position':{'x':1950,'y':3050,'areaId':1,'rotation':0},'serverPersisted':True,'localCreated':True}
  state['world']['entities'].append(item);fun.initialize(item)
  return state,person,item

 def test_every_original_building_and_eligible_villager_type(self):
  completed=blocked=0
  for building in world.rows('fun_building'):
   activity=world.by_id('fun_activity',building['funActivity'])
   members={v['villagerType'] for v in self.members if v['villagerSet']==activity['usedBy']}
   random_rewards=any(v['chance']!='1' for v in world.rows('reward_set_item') if activity['rewardSet']!='0' and v['setId']==activity['rewardSet'])
   for typ in self.types:
    if typ['id'] not in members:continue
    with self.subTest(building=building['id'],activity=activity['id'],villagerType=typ['id']):
     state,person,item=self.fixture(building,typ);data={'villagerId':person['id'],'funActivityId':int(activity['id']),'userFunBuildingTypeId':item['id']}
     state['wants']=[{'WantId':1,'VillagerStringID':person['id'],'MaterialID':int(activity['materialType']),'wantableCategoryType':3,'updatedAt':1000}]
     before=copy.deepcopy(state)
     if random_rewards:
      with self.assertRaisesRegex(NotImplementedError,'Probabilistic'):fun.perform(state,data,1030,'matrix:1')
      self.assertEqual(state,before);blocked+=1;continue
     response,changed=fun.perform(state,data,1030,'matrix:1');self.assertTrue(changed)
     self.assertEqual(response['SatisfiedWantModels'],[{'WantId':1,'VillagerStringID':person['id']}]);self.assertFalse(state['wants'])
     self.assertEqual(item['amount'],before['world']['entities'][-1]['amount']-(activity.get('unbreakable')!='1'))
     self.assertGreater(person['xp'],0);world.validate_world(state)
     reloaded=json.loads(json.dumps(state));snapshot=copy.deepcopy(reloaded)
     self.assertFalse(fun.perform(reloaded,data,1031,'matrix:1')[1]);self.assertEqual(reloaded,snapshot)
     completed+=1
  self.assertEqual((completed,blocked),(1533,60))

 def test_infants_and_toddlers_have_both_original_creche_slots(self):
  animations=world.rows('avatar_animation');activity=world.by_id('fun_activity',21)
  for typ in ['3','4','16','17']:
   with self.subTest(villagerType=typ):
    slots={int(v['positionAllocation']) for v in animations if v['villagerType']==typ and v['action']==activity['avatarAction'] and v['emotionalState']=='0'}
    self.assertEqual(slots,{1,2})

 def test_birthday_rechecks_fun_eligibility_and_removes_obsolete_wish(self):
  building=world.by_id('fun_building',9);typ=world.by_id('villager_type',3)
  state,person,item=self.fixture(building,typ);person['startAge']=4
  item['amount']=0
  state['wants']=[{'WantId':1,'VillagerStringID':'steve','MaterialID':442,'wantableCategoryType':3,'updatedAt':1000}]
  needs.generate(state,'ClientWant/GenerateFunWants',1000)
  self.assertTrue(any(w['VillagerStringID']=='steve' for w in state['wants']))
  before=copy.deepcopy(person);needs.generate(state,'ClientWant/GenerateFunWants',87400)
  self.assertFalse(any(w['VillagerStringID']=='steve' for w in state['wants']));self.assertEqual(person,before)

 def test_exhausted_creche_cannot_pay_again_or_create_fun_wish(self):
  state,person,item=self.fixture(world.by_id('fun_building',9),world.by_id('villager_type',3));item['amount']=0
  before=copy.deepcopy(state)
  with self.assertRaisesRegex(ValueError,'no uses'):fun.perform(state,{'villagerId':person['id'],'funActivityId':21,'userFunBuildingTypeId':item['id']},1030,'matrix:1')
  self.assertEqual(state,before);needs.generate(state,'ClientWant/GenerateFunWants',1030)
  self.assertFalse(any(w['VillagerStringID']=='steve' for w in state['wants']))

 def test_owned_wish_reconciliation_covers_every_building_and_eligible_type(self):
  state=copy.deepcopy(self.seed);state['wants']=[];owned=world.rows('fun_building')
  for b in owned:
   item={'id':'owned-'+b['id'],'templateType':'fun_building','templateId':int(b['id']),'position':{'x':1950,'y':3050,'areaId':1,'rotation':0}}
   fun.initialize(item);state['world']['entities'].append(item)
  prototype=copy.deepcopy(fun.actor(state,'steve'));count=0
  for typ in self.types:
   person=copy.deepcopy(prototype);person.update(id='age-type-'+typ['id'],templateId=int(typ['id']),gender=int(typ['genderType']),startAge=int(typ['minAge']),pregnant='true' if typ['isPregnant']=='1' else 'false',xp=0)
   state['world']['entities'].append(person)
   for b in owned:
    a=world.by_id('fun_activity',b['funActivity'])
    if not fun.eligible(person,a,1000):continue
    count+=1;state['wants'].append({'WantId':count,'VillagerStringID':person['id'],'MaterialID':int(a['materialType']),'wantableCategoryType':3,'updatedAt':1000})
  self.assertEqual(count,1593);inventory=copy.deepcopy(state['inventory']);entities=copy.deepcopy(state['world']['entities'])
  response,changed=needs.generate(state,'ClientWant/GenerateFunWants',1000)
  self.assertTrue(changed);self.assertEqual(response['result'],[]);self.assertEqual(state['inventory'],inventory);self.assertEqual(state['world']['entities'],entities)
  before=copy.deepcopy(state);self.assertFalse(needs.generate(state,'ClientWant/GenerateFunWants',1001)[1]);self.assertEqual(state,before)

 def test_missing_or_worn_building_wish_is_retained_and_other_needs_unchanged(self):
  state,person,item=self.fixture(world.by_id('fun_building',9),world.by_id('villager_type',3));item['amount']=0
  state['wants']=[{'WantId':1,'VillagerStringID':person['id'],'MaterialID':442,'wantableCategoryType':3,'updatedAt':1000},{'WantId':2,'VillagerStringID':person['id'],'MaterialID':6,'wantableCategoryType':1,'updatedAt':1000}]
  before=copy.deepcopy(state['wants']);self.assertEqual(needs.generate(state,'ClientWant/GenerateFunWants',1000)[0]['result'],before)
  state['world']['entities'].remove(item);self.assertEqual(needs.generate(state,'ClientWant/GenerateFunWants',1001)[0]['result'],before)
  state['world']['entities'].append(item);item['amount']=50;response,_=needs.generate(state,'ClientWant/GenerateFunWants',1002)
  self.assertEqual(response['result'],[before[1]])

 def test_building_completion_clears_both_babies_ownership_wishes_once(self):
  import tasks
  state=copy.deepcopy(self.seed)
  for req in world.rows('requirement_set_item'):
   key=req['materialType'];state['inventory'][key]=max(state['inventory'].get(key,0),float(req['quantity'])+float(req['quantityUsed'])+100)
  building=next(v for v in world.rows('building_type') if v['entityRef']=='fun_building' and v['entityID']=='9')
  definition=next(v for v in world.rows('building_task') if v['buildingType']==building['id'])
  point={'x':1950,'y':3050,'areaId':1,'rotation':0}
  state['world']['entities'].append({'id':'creche-foundation','templateType':'building_task','templateId':int(definition['id']),'position':point,'serverPersisted':True})
  state['wants']=[{'WantId':i,'VillagerStringID':ident,'MaterialID':442,'wantableCategoryType':3,'updatedAt':1000} for i,ident in enumerate(['baby male','baby female'],1)]
  data={'villagerId':'steve','taskTypeId':int(definition['taskId']),**point}
  started,_=tasks.start(state,data,1000,'ClientTaskService/StartBuildingTask');harvest={'workAreaId':started['workAreaId'],'taskTypeId':data['taskTypeId']}
  response,changed=tasks.harvest(state,harvest,started['completionTime'])
  self.assertTrue(changed);self.assertEqual(response['SatisfiedWantModels'],[{'WantId':1,'VillagerStringID':'baby male'},{'WantId':2,'VillagerStringID':'baby female'}]);self.assertEqual(state['wants'],[])
  before=copy.deepcopy(state);replay,changed=tasks.harvest(state,harvest,started['completionTime']+1)
  self.assertFalse(changed);self.assertEqual(response,replay);self.assertEqual(state,before)

 def test_login_removes_obsolete_ownership_wishes_before_any_startup_reply(self):
  import tempfile
  from pathlib import Path
  from unittest.mock import patch
  state,person,item=self.fixture(world.by_id('fun_building',9),world.by_id('villager_type',3))
  state['wants']=[{'WantId':1,'VillagerStringID':person['id'],'MaterialID':442,'wantableCategoryType':3,'updatedAt':1000}]
  with tempfile.TemporaryDirectory() as directory,patch.object(session,'STATE',Path(directory)),patch.object(session,'wire_time',return_value=1000):
   session.login({'deviceId':'fun-wish-login-test'});path=session.profile_path('fun-wish-login-test').with_suffix('.tutorial.json')
   session.atomic_json(path,{'normal':state,**session.fresh_tutorial()});session.login({'deviceId':'fun-wish-login-test'})
   loaded=json.loads(path.read_text(encoding='utf-8'))['normal'];self.assertEqual(loaded['wants'],[])
   self.assertEqual(loaded['world']['entities'],state['world']['entities']);self.assertEqual(loaded['inventory'],state['inventory'])

if __name__=='__main__':unittest.main()
