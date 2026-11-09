"""Area unlock/access/transfer preserve earlier worlds and family identities."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import areas,family,habitats,native_identity,session,tasks,world

class AreaTests(unittest.TestCase):
 def setUp(self):
  self.state=world.build_bridge_world(session.fresh_tutorial(),2000000000)
  self.state['user'].update(userLevel=20,userLevelID=20,xp=22469)
 def test_original_riverside_and_mountain_seed_once_and_area_projection_isolated(self):
  original={e['id']:copy.deepcopy(e) for e in self.state['world']['entities']}
  for ident,scenario in [(2,3),(3,8)]:
   areas.unlock(self.state,{'areaId':str(ident)},2000000001);areas.view(self.state,ident,2000000001)
   self.assertEqual(self.state['user']['scenarioId'],scenario)
   self.assertTrue(any(e['templateType']=='workshop' for e in world.area_content(self.state,ident,2000000001)['areaJson']['entities']))
   self.assertTrue(all(world.entity_area(e)==ident for e in world.startup(self.state,2000000001)['world']['entities']))
   snapshot=copy.deepcopy(self.state);self.assertFalse(areas.unlock(self.state,{'areaId':ident},2000000002)[1]);self.assertEqual(snapshot,self.state)
  self.state=json.loads(json.dumps(self.state));areas.view(self.state,1,2000000002)
  for ident,entity in original.items():self.assertEqual(next(e for e in self.state['world']['entities'] if e['id']==ident),entity)
  world.validate_world(self.state)
 def test_level_sequential_and_unknown_area_guards_do_not_mutate(self):
  for ident,level in [(2,9),(3,20),(4,50),(True,50)]:
   self.state['user']['userLevelID']=level;snapshot=copy.deepcopy(self.state)
   with self.assertRaises(ValueError):areas.unlock(self.state,{'areaId':ident},2000000001)
   self.assertEqual(snapshot,self.state)
  snapshot=copy.deepcopy(self.state)
  with self.assertRaises(ValueError):areas.view(self.state,2,2000000001)
  self.assertEqual(snapshot,self.state)
 def test_move_releases_bed_keeps_family_ages_and_delayed_replay_does_not_undo_return(self):
  home={'id':'home','templateType':'shelter','templateId':1,'position':{'x':4000,'y':4000,'rotation':0,'areaId':1}}
  habitats.initialize(home,2000000000);self.state['world']['entities'].append(home);habitats.assign(self.state,{'villagerId':'steve','shelterBedId':home['beds'][0]['id']},2000000000)
  person=family.actor(self.state,'steve');relations=copy.deepcopy(person['relations']);born=person['bornAt'];age=person['startAge']
  areas.unlock(self.state,{'areaId':2},2000000001)
  areas.move(self.state,{'villagerIds':['steve'],'areaId':2},2000000002,'out','42')
  self.assertEqual(person['position']['areaId'],2);self.assertEqual(person['shelterBedId'],'');self.assertFalse(home['beds'][0]['villagerId'])
  self.assertEqual(person['relations'],relations);self.assertEqual((person['bornAt'],person['startAge']),(born,age))
  areas.move(self.state,{'villagerIds':['steve'],'areaId':1},2000000003,'back','42');snapshot=copy.deepcopy(self.state)
  self.assertFalse(areas.move(self.state,{'villagerIds':['steve'],'areaId':2},2000000004,'out','42')[1]);self.assertEqual(snapshot,self.state)
  world.validate_world(self.state)
 def test_busy_actor_unknown_owner_and_duplicate_list_rejected_before_mutation(self):
  areas.unlock(self.state,{'areaId':2},2000000001)
  source=next(e for e in self.state['world']['entities'] if e.get('refId')=='Strawberries')
  tasks.start(self.state,{'villagerId':'steve','taskTypeId':14,'userMaterialSourceId':source['id'],**source['position']},2000000001)
  for ids in [['steve'],['foreign'],['jill','jill']]:
   snapshot=copy.deepcopy(self.state)
   with self.assertRaises(ValueError):areas.move(self.state,{'villagerIds':ids,'areaId':2},2000000002,'bad','42')
   self.assertEqual(snapshot,self.state)
 def test_authenticated_unlock_visit_return_and_restart(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(session,'STATE',Path(tmp)),patch.object(session,'wire_time',return_value=2000000001):
   profile=session.login({'deviceId':'area-test'})['data']['users'][0];path=session.profile_path('area-test').with_suffix('.tutorial.json')
   session.atomic_json(path,{**session.fresh_tutorial(),'version':3,'normal':self.state,'gameSettings':{'activeSequenceId':'-1','isFtueComplete':'1'}})
   def call(service,data,ident):return native_identity.process({**profile,'data':{'calls':[{'id':ident,'service':service,'data':data}]}})['data']['calls'][0]
   self.assertEqual(call('ClientUserService/UnlockArea',{'areaId':'2'},'unlock')['code'],200)
   self.assertEqual(call('ClientStartupService/GetAreaContent',{'areaId':2},'area')['code'],200)
   self.assertEqual(call('ClientVillagerService/MoveVillagers',{'villagerIds':['steve'],'areaId':2},'move')['code'],200)
   saved=json.loads(path.read_text());self.assertEqual(saved['normal']['areaId'],2);self.assertEqual(family.actor(saved['normal'],'steve')['position']['areaId'],2)
   self.assertEqual(call('ClientStartupService/GetStartupInfo',{},'reload')['code'],200)
   self.assertEqual(call('ClientStartupService/GetAreaContent',{'areaId':1},'return')['code'],200)

if __name__=='__main__':unittest.main()
