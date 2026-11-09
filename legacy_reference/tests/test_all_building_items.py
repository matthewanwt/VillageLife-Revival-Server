"""Every screenshot-confirmed item: original costs, completion, use and reload.
Synthetic access to later areas is explicit; this is not native acceptance.
"""
import copy,json,unittest
from pathlib import Path
import buildings,fun,habitats,learning,placement,prerequisites,session,tasks,world
SCOPE=json.loads((Path(__file__).resolve().parents[1]/'notes/BUILDING_IMPLEMENTATION_SCOPE.json').read_text(encoding='utf-8'))['items']

class AllBuildingItems(unittest.TestCase):
 def state(self):
  state=world.build_bridge_world(session.fresh_tutorial(),1000)
  state['user'].update(userLevel=50,userLevelID=50,xp=372826,maxAreaId=3)
  state['inventory']['323']=1000000
  return state
 def costs(self,state,task):
  for r in world.rows('requirement_set_item'):
   if r['requirementSet']==task['requirementSet'] and float(r['quantityUsed'])>0:
    state['inventory'][r['materialType']]=float(r['quantity'])+float(r['quantityUsed'])+1
 def finish(self,state,task,data,paid=False):
  service='ClientTaskService/StartCraftingTask' if task['taskType']=='1' else 'ClientTaskService/StartBuildingTask'
  started,_=tasks.start(state,data,1000,service,'start')
  request={'workAreaId':started['workAreaId'],'taskTypeId':int(task['id'])}
  at=started['completionTime']
  if paid:tasks.instant_complete(state,request,1001);at=min(at,1001)
  state=json.loads(json.dumps(state));response,_=tasks.harvest(state,request,at)
  state=json.loads(json.dumps(state));snapshot=copy.deepcopy(state)
  self.assertFalse(tasks.harvest(state,request,at+1)[1]);self.assertEqual(snapshot,state)
  self.assertFalse(tasks.start(state,data,at+2,service,'start')[1]);self.assertEqual(snapshot,state)
  return state,response,at
 def prepare_structure(self,item,foundation):
  state=self.state();task=world.by_id('task',foundation['taskId']);target=world.by_id('building_type',foundation['buildingType'])
  point={'x':4000,'y':4000,'rotation':0,'areaId':1}
  if task['taskType']=='6':
   parent=world.by_id('building_type',world.by_id('building_task',foundation['parentId'])['buildingType'])
   state['world']['entities']=[e for e in state['world']['entities'] if e['templateType']!=parent['entityRef']]
   entity={'id':'built-parent','templateType':parent['entityRef'],'templateId':int(parent['entityID']),'position':point,'localCreated':True,'serverPersisted':True}
   fun.initialize(entity);habitats.initialize(entity,1000);state['world']['entities'].append(entity)
   state['inventory'][parent['materialType']]=1
  else:
   state['world']['entities']=[e for e in state['world']['entities'] if not(e['templateType']==target['entityRef'] and e['templateId']==int(target['entityID'])) and not(e['templateType']=='building_task' and e['templateId']==int(foundation['id']))]
   buildings.place(state,{'buildingTaskTypeId':int(foundation['id']),**point})
  self.costs(state,task)
  return state,task,{'villagerId':'steve','taskTypeId':int(task['id']),**point}
 def use_fun(self,state,item,entity,at):
  activity=world.by_id('fun_activity',item['activity_ids'][0]);person=fun.actor(state,'steve')
  typ=next(t for t in world.rows('villager_type') if t['id'] in {r['villagerType'] for r in world.rows('villager_set_item') if r['villagerSet']==activity['usedBy']} and int(t['id'])<=19)
  person.update(templateId=int(typ['id']),startAge=int(typ['minAge']),bornAt=at,gender=int(typ['genderType']),pregnant=typ['isPregnant']=='1',xp=0)
  data={'villagerId':person['id'],'funActivityId':int(activity['id'])}
  if entity:data['userFunBuildingTypeId']=entity['id']
  response,changed=fun.perform(state,data,at,'use');self.assertTrue(changed);self.assertGreater(response['HappinessModel']['Xp'],0)
  state=json.loads(json.dumps(state));snapshot=copy.deepcopy(state)
  self.assertFalse(fun.perform(state,data,at+1,'use')[1]);self.assertEqual(snapshot,state)
 def test_all_69_items_have_unique_original_matches(self):
  self.assertEqual(len(SCOPE),69);self.assertEqual(len({i['material_id'] for i in SCOPE}),69)
  for item in SCOPE:self.assertEqual(world.by_id('material_type',item['material_id'])['name'],item['name'])
 def test_all_57_structures_natural_and_paid_finish_restart_and_activity(self):
  count=0
  for item in SCOPE:
   if not item['foundation_ids']:continue
   foundation=next(world.by_id('building_task',i) for i in item['foundation_ids'] if world.by_id('task',world.by_id('building_task',i)['taskId'])['id']!='0')
   for paid in [False,True]:
    with self.subTest(item=item['name'],paid=paid):
     state,task,data=self.prepare_structure(item,foundation)
     state,response,at=self.finish(state,task,data,paid)
     entity=next(e for e in state['world']['entities'] if e['id']==response['objects'][0]['id'])
     self.assertGreaterEqual(state['inventory'][item['material_id']],1)
     self.assertTrue(any(e['id']==entity['id'] for e in world.area_content(state,1,at)['areaJson']['entities']))
     if item['activity_ids']:self.use_fun(state,item,entity,at)
     if entity['templateType']=='fire_type':
      firetask=world.by_id('task',next(f['taskId'] for f in world.rows('fire_task') if f['fireType']==str(entity['templateId'])))
      self.costs(state,firetask);response,_=habitats.operate(state,'ClientUserFireService/StartFire',{'userFireId':entity['id'],'villagerId':'steve'},at,'light')
      self.assertGreater(response['userFire']['endsAt'],at)
     if entity['templateType']=='material_source':
      task=world.by_id('task',world.by_id('material_source',entity['templateId'])['task']);self.costs(state,task)
      started,_=tasks.start(state,{'villagerId':'steve','taskTypeId':int(task['id']),'userMaterialSourceId':entity['id'],**entity['position']},at)
      tasks.harvest(state,{'workAreaId':started['workAreaId'],'taskTypeId':int(task['id'])},started['completionTime'])
     count+=1
  self.assertEqual(count,114)
 def test_all_12_portables_craft_finish_reload_and_eligible_use(self):
  count=0
  for item in SCOPE:
   if item['foundation_ids']:continue
   with self.subTest(item=item['name']):
    state=self.state();sets={r['setId'] for r in world.rows('reward_set_item') if r['materialType']==item['material_id']}
    task=next(t for t in world.rows('task') if t['taskType']=='1' and t['rewardSet']!='0' and t['rewardSet'] in sets)
    workshop=next(w for w in world.rows('workshop') if task['workAreaType'] in w['tableIDs'].split(','))
    point={'x':4000,'y':4000,'rotation':0,'areaId':1}
    state['world']['entities'].append({'id':'craft-workshop','templateType':'workshop','templateId':int(workshop['id']),'position':point,'localCreated':True})
    self.costs(state,task)
    state,_,at=self.finish(state,task,{'villagerId':'steve','taskTypeId':int(task['id']),**point},True)
    self.use_fun(state,item,None,at);count+=1
  self.assertEqual(count,12)
 def test_each_learning_timer_parent_and_completed_building_prerequisites(self):
  checked=0
  for item in SCOPE:
   definition=world.by_id('material_type',item['material_id'])
   if int(definition['learnDurationSec'])<=0:continue
   with self.subTest(item=item['name']):
    if item['foundation_ids']:
     foundation=next(world.by_id('building_task',i) for i in item['foundation_ids'] if world.by_id('building_task',i)['taskId']!='0')
     state,_,_=self.prepare_structure(item,foundation)
    else:state=self.state()
    ident=int(item['material_id']);state['inventory'].pop(str(ident),None)
    parent=int(definition['parentID'])
    if parent>0:state.setdefault('materialLearning',{})[str(parent)]={'status':'unlocked'}
    learning.operate(state,'ClientMaterialService/StartLearningMaterial',{'materialTypeId':ident},1000)
    state=json.loads(json.dumps(state));learning.operate(state,'ClientMaterialService/SkipLearningMaterial',{'materialTypeId':ident},1001)
    self.assertTrue(learning.unlocked(state,ident));checked+=1
  self.assertGreater(checked,40)
 def test_entire_storage_workshop_farm_chains_without_funded_old_tier_markers(self):
  chains=[[186,187,188,189,190],[222,223,224,225,226],[172,173,174,175,176,896],[227,196,197,198],[91,168,169,170,171]]
  for chain in chains:
   with self.subTest(chain=chain):
    state=self.state();at=1000;identity=None;materials=[];point={'x':4000,'y':4000,'rotation':0,'areaId':1}
    for task_id in chain:
     task=world.by_id('task',task_id)
     foundation=next(f for f in world.rows('building_task') if f['taskId']==str(task_id));target=world.by_id('building_type',foundation['buildingType'])
     if task['taskType']=='2':
      state['world']['entities']=[e for e in state['world']['entities'] if e['templateType']!=target['entityRef'] and not(e['templateType']=='building_task' and e['templateId']==int(foundation['id']))]
      buildings.place(state,{'buildingTaskTypeId':int(foundation['id']),**point})
     self.costs(state,task)
     data={'villagerId':'steve','taskTypeId':task_id,**point}
     started,_=tasks.start(state,data,at,'ClientTaskService/StartBuildingTask','chain:'+str(task_id));at=started['completionTime']
     response,_=tasks.harvest(state,{'workAreaId':started['workAreaId'],'taskTypeId':task_id},at)
     ident=response['objects'][0]['id']
     if identity:self.assertEqual(ident,identity)
     identity=ident;materials.append(target['materialType'])
     state=json.loads(json.dumps(state));projected={str(r['materialTypeId']):r for r in tasks.inventory(state)}
     for material in materials:
      self.assertGreaterEqual(projected[material]['amount'],1);self.assertTrue(projected[material]['isUnlocked'])
      self.assertGreaterEqual(prerequisites.quantity(state,material),1)
     at+=1
    # Older saves may retain only the final tier's marker. Recover the wire
    # milestones from the saved object without altering balances on disk.
    for material in materials[:-1]:state['inventory'].pop(material,None)
    snapshot=copy.deepcopy(state);projected={str(r['materialTypeId']):r for r in tasks.inventory(state)}
    for material in materials:self.assertGreaterEqual(projected[material]['amount'],1)
    self.assertEqual(snapshot,state)
 def test_learning_refuses_locked_riverside_but_accepts_existing_area_milestone(self):
  state=self.state();state['user']['maxAreaId']=1
  material=204;definition=world.by_id('material_type',material)
  parent=definition['parentID'];state.setdefault('materialLearning',{})[parent]={'status':'unlocked'}
  snapshot=copy.deepcopy(state)
  with self.assertRaises(ValueError):learning.operate(state,'ClientMaterialService/StartLearningMaterial',{'materialTypeId':material},1000)
  self.assertEqual(snapshot,state);state['user']['maxAreaId']=2
  self.assertTrue(learning.operate(state,'ClientMaterialService/StartLearningMaterial',{'materialTypeId':material},1000)[1])
 def test_unbuilt_authored_placeholder_does_not_unlock_ancestor(self):
  state=self.state();state['inventory'].pop('225',None)
  self.assertEqual(prerequisites.quantity(state,'225'),0)
 def test_area_milestones_do_not_grant_stock_or_bypass_locked_area(self):
  state=self.state();state['user']['maxAreaId']=1
  self.assertEqual(prerequisites.quantity(state,'231'),1);self.assertEqual(prerequisites.quantity(state,'232'),0)
  state['user']['maxAreaId']=2
  self.assertEqual(prerequisites.quantity(state,'232'),1);self.assertEqual(prerequisites.quantity(state,'1536'),0)
  self.assertNotIn('232',state['inventory'])

if __name__=='__main__':unittest.main()
