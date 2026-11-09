import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import world,session,tasks,starter_tools

class StarterToolRecoveryTests(unittest.TestCase):
 def setUp(self):self.state=world.build_bridge_world(session.fresh_tutorial(),1000)
 def test_only_original_uncraftable_starter_tools_are_selected(self):
  self.assertEqual({v[0] for v in starter_tools.definitions()},{'106','111','112','117','118'})
  self.assertTrue(all(v[1]==1 for v in starter_tools.definitions()))
 def test_exhausted_tools_recover_once_without_gems_or_other_materials(self):
  for ident,_,_ in starter_tools.definitions():self.state['inventory'][ident]=0
  self.state['inventory'].update({'717':0,'718':0,'323':23,'72':7})
  self.assertTrue(starter_tools.recover(self.state,1000))
  for ident,_,_ in starter_tools.definitions():self.assertEqual(self.state['inventory'][ident],1);self.assertEqual(self.state['starterToolRecovery'][ident]['replacements'],1)
  self.assertEqual({k:self.state['inventory'][k] for k in ['717','718','323','72']},{'717':0,'718':0,'323':23,'72':7})
  before=copy.deepcopy(self.state);self.assertFalse(starter_tools.recover(self.state,1001));self.assertEqual(self.state,before)
 def test_partial_tools_and_owned_stacks_are_never_topped_up(self):
  for amount in [.01,.1,.5,1,2]:
   for ident,_,_ in starter_tools.definitions():self.state['inventory'][ident]=amount
   before=copy.deepcopy(self.state);self.assertFalse(starter_tools.recover(self.state,1000));self.assertEqual(self.state,before)
 def test_ten_well_gathers_replace_exhausted_bucket_and_replay_does_not_duplicate(self):
  self.state['inventory']['117']=1
  definition=next(v for v in world.rows('material_source') if v['task']=='6')
  source={'id':'test-well','templateType':'material_source','templateId':int(definition['id']),'serverPersisted':True,'position':{'x':2000,'y':3000,'areaId':1,'rotation':0}}
  self.state['world']['entities'].append(source);before_water=self.state['inventory'].get('6',0);at=1000
  for i in range(10):
   response,_=tasks.start(self.state,{'villagerId':'steve','userMaterialSourceId':source['id'],'taskTypeId':6,'x':2000,'y':3000,'areaId':1},at)
   data={'workAreaId':response['workAreaId'],'taskTypeId':6};at=response['completionTime']
   collected,changed=tasks.harvest(self.state,data,at);self.assertTrue(changed)
   snapshot=copy.deepcopy(self.state);self.assertFalse(tasks.harvest(self.state,data,at+1)[1]);self.assertEqual(snapshot,self.state)
   at+=1
  self.assertGreater(self.state['inventory']['6'],before_water);self.assertEqual(self.state['inventory']['117'],1)
  self.assertEqual(self.state['starterToolRecovery']['117']['replacements'],1)
  self.assertEqual(next(v['amount'] for v in collected['inventory'] if v['materialTypeId']==117),1)
  world.validate_world(self.state)
 def test_login_repairs_exhausted_bucket_persists_and_reloads_without_duplicate(self):
  self.state['inventory']['117']=0
  with tempfile.TemporaryDirectory() as directory,patch.object(session,'STATE',Path(directory)),patch.object(session,'wire_time',return_value=1000):
   session.login({'deviceId':'starter-tool-test'});path=session.profile_path('starter-tool-test').with_suffix('.tutorial.json');session.atomic_json(path,{'normal':self.state,**session.fresh_tutorial()})
   session.login({'deviceId':'starter-tool-test'});normal=json.loads(path.read_text(encoding='utf-8'))['normal']
   self.assertEqual(normal['inventory']['117'],1);self.assertEqual(normal['starterToolRecovery']['117']['replacements'],1)
   session.login({'deviceId':'starter-tool-test'});reloaded=json.loads(path.read_text(encoding='utf-8'))['normal'];self.assertEqual(reloaded['starterToolRecovery'],normal['starterToolRecovery']);self.assertEqual(reloaded['inventory'],normal['inventory'])

if __name__=='__main__':unittest.main()
