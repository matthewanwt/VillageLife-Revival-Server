"""Construction uses real prerequisite sources and survives paid/replayed completion."""
import copy
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import buildings
import placement
import prerequisites
import session
import tasks
import world


class ConstructionJourneys(unittest.TestCase):
    def setUp(self):
        self.state=world.build_bridge_world(session.fresh_tutorial(),1000)
        self.state['inventory']['323']=1000000
        self.state['user'].update(userLevel=3,userLevelID=3,xp=106)

    def fund_costs(self, task_id):
        task=world.by_id('task',task_id)
        for req in world.rows('requirement_set_item'):
            if req['requirementSet']==task['requirementSet']:
                self.state['inventory'][req['materialType']]=float(req['quantity'])+float(req['quantityUsed'])+1
        return task

    def farm_request(self):
        foundation=next(e for e in self.state['world']['entities'] if e['templateType']=='building_task' and e['templateId']==8)
        return {'villagerId':'steve','taskTypeId':91,**foundation['position']}

    def test_xp_gate_reads_shrine_xp_not_invented_inventory_stock(self):
        self.assertNotIn('7',self.state['inventory'])
        self.assertEqual(prerequisites.quantity(self.state,'7'),106)
        self.fund_costs(91)
        tasks.start(self.state,self.farm_request(),1000,'ClientTaskService/StartBuildingTask','farm')
        self.assertEqual(self.state['user']['xp'],106)
        self.assertNotIn('7',self.state['inventory'])

    def test_funded_fake_xp_stock_cannot_bypass_real_xp_threshold(self):
        self.fund_costs(91);self.state['user']['xp']=105;self.state['inventory']['7']=1000000
        before=copy.deepcopy(self.state)
        with self.assertRaises(ValueError):tasks.start(self.state,self.farm_request(),1000,'ClientTaskService/StartBuildingTask','farm')
        self.assertEqual(self.state,before)

    def test_mud_farm_house_natural_finish_reload_and_no_crop_grant(self):
        self.fund_costs(91)
        started,_=tasks.start(self.state,self.farm_request(),1000,'ClientTaskService/StartBuildingTask','farm')
        self.assertEqual(started['completionTime'],15400)
        request={'workAreaId':started['workAreaId'],'taskTypeId':91}
        self.state=json.loads(json.dumps(self.state));before=copy.deepcopy(self.state)
        with self.assertRaises(ValueError):tasks.harvest(self.state,request,15399)
        self.assertEqual(self.state,before)
        reply,_=tasks.harvest(self.state,request,15400)
        entity=next(e for e in self.state['world']['entities'] if e['templateType']=='farm_building')
        self.assertEqual(entity['templateId'],0);self.assertEqual(world.by_id('farm_building',0)['numPlots'],'1')
        self.assertEqual(len(reply['objects']),1)
        self.assertFalse(any(e['templateType'] in {'farm_plot','farming_plot'} for e in self.state['world']['entities']))
        self.state=json.loads(json.dumps(self.state));before=copy.deepcopy(self.state)
        self.assertFalse(tasks.harvest(self.state,request,15401)[1]);self.assertEqual(self.state,before)
        self.assertEqual(sum(e['templateType']=='farm_building' for e in world.area_content(self.state,1,15401)['areaJson']['entities']),1)

    def test_paid_finish_and_delayed_start_replay_do_not_charge_or_duplicate(self):
        self.fund_costs(91);data=self.farm_request()
        started,_=tasks.start(self.state,data,1000,'ClientTaskService/StartBuildingTask','farm')
        request={'workAreaId':started['workAreaId'],'taskTypeId':91};cost=tasks.instant_price(14399);gems=self.state['inventory']['323']
        tasks.instant_complete(self.state,request,1001);tasks.harvest(self.state,request,1001)
        self.state=json.loads(json.dumps(self.state));before=copy.deepcopy(self.state)
        replay,changed=tasks.start(self.state,data,1002,'ClientTaskService/StartBuildingTask','farm')
        self.assertFalse(changed);self.assertEqual(replay['completionTime'],1001)
        self.assertFalse(tasks.instant_complete(self.state,request,1002)[1]);self.assertEqual(self.state,before)
        self.assertEqual(self.state['inventory']['323'],gems-cost)
        with self.assertRaises(ValueError):tasks.start(self.state,{**data,'x':data['x']+1},1002,'ClientTaskService/StartBuildingTask','farm')
        self.assertEqual(self.state,before)

    def test_farm_upgrade_chain_keeps_one_identity(self):
        self.fund_costs(91);data=self.farm_request();at=1000
        started,_=tasks.start(self.state,data,at,'ClientTaskService/StartBuildingTask','farm')
        at=started['completionTime'];tasks.harvest(self.state,{'workAreaId':started['workAreaId'],'taskTypeId':91},at)
        entity=next(e for e in self.state['world']['entities'] if e['templateType']=='farm_building');identity=entity['id']
        for task_id in [168,169,170,171]:
            task=self.fund_costs(task_id)
            for req in world.rows('requirement_set_item'):
                if req['requirementSet']==task['levelRequirement']:
                    if req['materialType']=='7':self.state['user']['xp']=max(self.state['user']['xp'],float(req['quantity']))
                    elif req['materialType']!='0':self.state['inventory'][req['materialType']]=max(self.state['inventory'].get(req['materialType'],0),float(req['quantity']))
            data={'villagerId':'steve','taskTypeId':task_id,**entity['position']};at+=1
            started,_=tasks.start(self.state,data,at,'ClientTaskService/StartBuildingTask','upgrade:'+str(task_id))
            at=started['completionTime'];tasks.harvest(self.state,{'workAreaId':started['workAreaId'],'taskTypeId':task_id},at)
            self.state=json.loads(json.dumps(self.state));entity=next(e for e in self.state['world']['entities'] if e['templateType']=='farm_building')
            self.assertEqual(entity['id'],identity)
            self.assertEqual(sum(e['templateType']=='farm_building' for e in self.state['world']['entities']),1)

    def test_mud_shelter_completion_uses_one_position_identity(self):
        self.fund_costs(135);point={'x':4000,'y':4000,'rotation':0,'areaId':1}
        buildings.place(self.state,{'buildingTaskTypeId':11,**point})
        started,_=tasks.start(self.state,{'villagerId':'steve','taskTypeId':135,**point},1000,'ClientTaskService/StartBuildingTask','shelter')
        reply,_=tasks.harvest(self.state,{'workAreaId':started['workAreaId'],'taskTypeId':135},started['completionTime'])
        entity=next(e for e in self.state['world']['entities'] if e['templateType']=='shelter' and e.get('sourceWorkAreaId')==started['workAreaId'])
        self.assertEqual(reply['objects'][0]['position']['id'],placement.position_id(entity))
        self.assertTrue(entity['beds']);world.validate_world(self.state)

    def test_authenticated_start_retry_after_paid_finish_and_relogin_projection(self):
        self.fund_costs(91)
        with tempfile.TemporaryDirectory() as temp,patch.object(session,'STATE',Path(temp)):
            profile=session.login({'deviceId':'construction-test'})['data']['users'][0]
            path=session.profile_path('construction-test').with_suffix('.tutorial.json')
            session.atomic_json(path,{**session.fresh_tutorial(),'version':3,'normal':self.state,
                'gameSettings':{'activeSequenceId':'-1','isFtueComplete':'1'}})
            def call(service,data,ident,at):
                with patch.object(session,'wire_time',return_value=at):
                    return session.process({**profile,'data':{'calls':[{'id':ident,'service':service,'data':data}]}},native_ids=True)['data']['calls'][0]
            request=self.farm_request();started=call('ClientTaskService/StartBuildingTask',request,'build',1000)
            self.assertEqual(started['code'],200)
            job={'workAreaId':started['data']['workAreaId'],'taskTypeId':91}
            self.assertEqual(call('ClientTaskService/InstantCompleteTaskCurve',job,'skip',1001)['code'],200)
            self.assertEqual(call('ClientTaskService/HarvestTask',job,'claim',1001)['code'],200)
            before=path.read_bytes()
            replay=call('ClientTaskService/StartBuildingTask',request,'build',1002)
            self.assertEqual(replay['code'],200);self.assertEqual(replay['data']['completionTime'],1001)
            self.assertEqual(path.read_bytes(),before)
            profile=session.login({'deviceId':'construction-test'})['data']['users'][0]
            area=call('ClientStartupService/GetAreaContent',{'areaId':1},'area',1003)
            self.assertEqual(area['code'],200)
            self.assertEqual(sum(e['templateType']=='farm_building' for e in area['data']['areaJson']['entities']),1)
