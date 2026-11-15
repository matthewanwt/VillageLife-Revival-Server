"""Pure fixtures for original APK wire contracts; ships NO proprietary rows."""
from __future__ import annotations
import csv
import io
import json
import sqlite3
import tempfile
from contextlib import closing
import threading
import unittest
import urllib.request
import zipfile
from pathlib import Path
from unittest.mock import patch

from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.persistence.legacy_import import LegacySaveImporter
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.services import OriginalClientGame
from villagelife.protocol.original_client.assets import ClientAssets
from villagelife.protocol.original_client.native_ids import mappings,translate
from villagelife.protocol.legacy_codec import encode,decode
from villagelife.transport.http_api import ApiServer


def fake_tables(db:Path):
    with closing(sqlite3.connect(db)) as con:
        con.executescript('CREATE TABLE game_tables(id INTEGER PRIMARY KEY,source_id INTEGER,name TEXT,declared_rows INTEGER,actual_rows INTEGER);'
                          'CREATE TABLE game_rows(table_id INTEGER,ordinal INTEGER,row_id TEXT,fields_json TEXT);')
        tables={
            'seq_state_tablet_ftue':[{'id':'0','order':'1','sequenceType':'62','dataJSON':json.dumps({'refId':'steve'}),'persist':'217'},
                                     {'id':'217','order':'2','sequenceType':'62','dataJSON':json.dumps({'refId':'jill'}),'persist':'410'}],
            'villager_starting_variation':[{'id':'0','refId':'steve','name':'Example','villagerType':'1','startAge':'21'},
                                          {'id':'4','refId':'jill','name':'Other','villagerType':'1','startAge':'21'}],
            'area':[{'id':'1','scenario':'2'}],
            'farm_building':[{'id':'0','numPlots':'1'}],
            'building_type':[{'id':'35','entityRef':'farm_building','entityID':'0','materialType':'700'}],
            'building_task':[{'id':'8','buildingType':'35','parentId':'-1'}],
            'villager_skill':[{'id':'2','area':'1'},{'id':'3','area':'1'},{'id':'8','area':'2'}],
            'farming_plot':[{'id':'0'}],
            'scenario':[{'id':'2','data':'<scenario><entities /></scenario>'}],
            'decor_item':[{'id':'7','isScenery':'0','multiPlacement':'1',
                           'requirement_set':'12','price_coins':'60','price_gems':'0',
                           'material_type':'700'}],
            'material_type':[{'id':ident} for ident in ('130','231','323','325','700')] + [
                {'id':ident, 'learnDurationSec':'60', 'unlockLevel':'2',
                 'parentID':parent, 'area':'1', 'seasonal':'0'}
                for ident,parent in (('178','-1'), ('179','178'))
            ],
            'global':[{'id':str(index), 'label':label, 'value':value}
                      for index,(label,value) in enumerate({
                          'learningMax':'3','learningMaxSeasonal':'1',
                          'hours_per_year':'24','skill_slots_max':'3',
                          'skill_gem_cost':'95','skill_gem_buyout_discount':'0.8',
                          'gemCurveVariableTime1min':'60','gemCurveVariableTime1hour':'3600',
                          'gemCurveVariableTime1day':'86400','gemCurveVariableTime1week':'604800',
                          'gemCalcValue1':'1','gemCalcValue2':'2',
                          'gemCalcValue3':'8','gemCalcValue4':'50',
                      }.items())],
            'requirement_set_item':[{'id':'1','requirementSet':'12',
                                     'materialType':'130','quantity':'1'}],
        }
        for i,(name, rows) in enumerate(tables.items(),1):
            con.execute('INSERT INTO game_tables VALUES (?,?,?,?,?)',(i,0,name,len(rows),len(rows)))
            con.executemany('INSERT INTO game_rows VALUES (?,?,?,?)',
                            [(i,j,row['id'],json.dumps(row)) for j,row in enumerate(rows)])
        con.commit()


class OriginalTravelTests(unittest.TestCase):
    def test_hunting_gear_uses_lodge_capacity_and_replays_placement(self):
        from villagelife.protocol.original_client.buildings import OriginalBuildingRules

        class Definitions:
            def item(self, table, ident):
                if (table, ident) == ('HuntingLodgeType', 1):
                    return {'HuntingSledCount': '1'}
                if (table, ident) == ('HuntingSledType', 1):
                    return {}
                raise KeyError((table, ident))

        service = 'ClientHuntingService/PlaceHuntingSled'
        rules = OriginalBuildingRules(Definitions())
        state = {'areaId': 3, 'world': {'entities': []}}
        request = {'areaId': 3, 'x': 90, 'y': 100, 'rotation': 0}
        with self.assertRaisesRegex(ValueError, 'free equipment slot'):
            rules.place_area_equipment(state, service, request)
        state['world']['entities'].append({'id': 'lodge', 'templateType': 'HuntingLodgeType',
                                           'templateId': 1, 'position': {'areaId': 3}})
        answer = rules.place_area_equipment(state, service, request)
        self.assertEqual(rules.place_area_equipment(state, service, request), answer)
        placed = state['world']['entities'][1]
        self.assertEqual(placed['templateType'], 'HuntingSledType')
        self.assertEqual(answer['userHuntingSled']['userHuntingSledId'], placed['id'])
        with self.assertRaisesRegex(ValueError, 'free equipment slot'):
            rules.place_area_equipment(state, service, {**request, 'x': 100})
        self.assertEqual(len(state['world']['entities']), 2)

    def test_riverside_story_replay_does_not_add_completed_rescue_again(self):
        from villagelife.protocol.original_client.quests import OriginalQuestRules

        class Definitions:
            def item(self, table, ident):
                return {'targetObjectType': 'story'} if table == 'quest_type' else {}

        quest = {'id': 'rescued', 'questTypeId': 12, 'objectId': '74'}
        duplicate = {**quest, 'id': 'stale-reopened'}
        next_story = {'id': 'mountain-path', 'questTypeId': 12, 'objectId': '75'}
        response = {'inventory': [{'materialTypeId': 1532, 'amount': 1}]}
        state = {'quests': [duplicate, next_story],
                 'completedQuests': {'rescued': {'quest': quest, 'response': response}}}
        rules = OriginalQuestRules(Definitions())
        rules.reconcile_travel(state, 100)
        self.assertEqual(state['quests'], [next_story])
        self.assertEqual(rules.complete(state, {'userQuestId': duplicate['id']}, 100), response)
        self.assertEqual(rules.add(state, {'questTypeId': 12, 'objectId': '74'}, 101)['userQuest']['objectId'], '74')
        self.assertEqual(state['quests'], [next_story])

    def test_story_transfer_can_precede_unlock_and_replays_without_moving_twice(self):
        from copy import deepcopy
        from villagelife.protocol.original_client.areas import AreaRules

        class Definitions:
            def item(self, table, ident):
                return {'unlockLevel': '10'}

            def scenario_for_area(self, area):
                return {'name': 'Riverside'}, {'data': '<world><entities/></world>',
                    'clientData': json.dumps([{'id': 'workshop', 'templateType': 'workshop',
                                               'position': {'x': 300, 'y': 500, 'areaId': area}}]),
                    'serverScenarioId': '3'}

        areas = AreaRules(Definitions())
        state = {'areaId': 1, 'user': {'maxAreaId': 1, 'userLevelID': 9},
                 'world': {'entities': [{'id': 'person', 'templateType': 'villager_type',
                                         'position': {'x': 1, 'y': 2, 'areaId': 1}}]}}
        request = {'areaId': 2, 'villagerIds': ['person']}
        original = deepcopy(state)
        with self.assertRaisesRegex(ValueError, 'Village level too low'):
            areas.move(state, request, 100)
        self.assertEqual(state, original)
        state['user']['userLevelID'] = 10
        answer = areas.move(state, request, 100)
        self.assertEqual(answer, {'position': {'areaId': 2}, 'villagers': [{'id': 'person'}]})
        self.assertEqual(state['areaId'], 1)
        self.assertEqual(state['world']['entities'][0]['position']['areaId'], 2)
        moved = deepcopy(state)
        self.assertEqual(areas.move(state, request, 101), answer)
        self.assertEqual(areas.unlock(state, '2', 101)['userArea'], {'areaId': 2})
        self.assertEqual(state, moved)

    def test_later_area_restarts_with_its_own_scenario_and_scene(self):
        from villagelife.protocol.original_client.areas import AreaRules
        from villagelife.protocol.original_client.tutorial import TutorialRules

        class Definitions:
            def scenario_for_area(self, area):
                scene = [{'id': 'river-shrine', 'templateType': 'shrine',
                          'position': {'x': 91, 'y': 72, 'areaId': 2}}] if area == 2 else []
                return {'name': 'Riverside' if area == 2 else 'Woodland'}, {
                    'serverScenarioId': str(area + 1), 'clientData': json.dumps(scene),
                    'data': '<world><entities/></world>'
                }

        definitions = Definitions()
        areas = AreaRules(definitions)
        state = {'areaId': 1, 'scenarioId': 2, 'user': {'scenarioId': 2, 'maxAreaId': 2},
                 'world': {'camera': {'x': 4, 'y': 5, 'zoom': 1},
                           'entities': [{'id': 'woodland-person', 'templateType': 'villager_type',
                                         'serverPersisted': True, 'position': {'areaId': 1}}]},
                 'workAreas': {'old': {'status': 'working', 'position': {'areaId': 1},
                                       'taskTypeId': 9999}}}
        overlay = areas.view(state, 2, 100)['areaJson']['entities']
        self.assertEqual([entity['id'] for entity in overlay], ['woodland-person'])
        self.assertEqual(overlay[0]['position']['areaId'], 1)
        self.assertEqual(state['scenarioId'], 3)
        startup = areas.world.startup(state, 100)
        self.assertEqual(startup['world']['camera'], {'x': 91, 'y': 72, 'zoom': 1})
        self.assertEqual(startup['user']['scenarioId'], 3)
        saved = {'userHash': {}, 'normal': state, 'gameSettings': {'lastViewedArea': '1'}}
        settings, _ = TutorialRules(definitions).run(saved, 'ClientSettingService/GetUserGameSettings', {})
        self.assertIn({'key': 'lastViewedArea', 'value': '2'}, settings['gameSettings'])
        self.assertEqual(state['world']['camera'], {'x': 4, 'y': 5, 'zoom': 1})


class OriginalCraftingTests(unittest.TestCase):
    def test_work_eligibility_changes_at_the_authored_birthday(self):
        from villagelife.protocol.original_client.world import OriginalWorldRules

        child = {'id':'11','minAge':'5','maxAge':'12','genderType':'1','canWork':'0'}
        teen = {'id':'13','minAge':'13','maxAge':'17','genderType':'1','canWork':'1'}

        class Definitions:
            def item(self, table, ident):
                return child

            def rows(self, table):
                return {'global':[{'label':'hours_per_year','value':'24'}],
                        'villager_type':[child, teen],
                        'villager_set_item':[{'villagerType':'13','villagerSet':'9'}]}[table]

        world = OriginalWorldRules(Definitions())
        villager = {'templateId':11,'startAge':12,'bornAt':1000}
        self.assertFalse(world.can_work(villager, 87399))
        self.assertTrue(world.can_work(villager, 87400))
        self.assertFalse(world.can_work(villager, 87400, {'excludeVillagerSet':'9'}))
        self.assertEqual(villager['templateId'], 11)

    def test_native_crafting_payload_resolves_compatible_workshop_by_position(self):
        from villagelife.protocol.original_client.work import OriginalWorkRules

        class Definitions:
            def item(self, table, ident):
                return {
                    ('villager_skill', 6): {'professionMultiplier': '0.25'},
                    ('task', 8): {'taskType': '1', 'workAreaType': '7', 'skillId': '6',
                                  'rewardSet': '2', 'requirementSet': '0', 'duration': '10'},
                    ('villager_type', 1): {'canWork': '1'},
                    ('workshop', 0): {'tableIDs': '91', 'tableCount': '1'},
                    ('workshop', 1): {'tableIDs': '7,91', 'tableCount': '2'},
                }[table, ident]

            def rows(self, table):
                if table == 'reward_set_item':
                    return [{'setId': '2', 'chance': '1', 'quantity': '1', 'materialType': '5'}]
                return []

        entities = [
            {'id': 'actor', 'templateType': 'villager_type', 'templateId': 1,
             'position': {'areaId': 1}, 'skills': [{'skillTypeId': 6}, {'skilltypeId': 6}]},
            {'id': 'wrong-table', 'templateType': 'workshop', 'templateId': 0,
             'position': {'areaId': 1, 'x': 10, 'y': 20}},
            {'id': 'compatible', 'templateType': 'workshop', 'templateId': 1,
             'position': {'areaId': 1, 'x': 12, 'y': 20}},
        ]
        state = {'areaId': 1, 'world': {'entities': entities}, 'inventory': {}}
        request = {'areaId': 1, 'rotation': 0, 'taskTypeId': 8,
                   'villagerId': 'actor', 'x': 10, 'y': 20}
        result = OriginalWorkRules(Definitions()).start(
            state, 'ClientTaskService/StartCraftingTask', request, 100)
        self.assertEqual(state['workAreas'][result['workAreaId']]['sourceId'], 'compatible')
        self.assertEqual(result['completionTime'], 105)
        self.assertEqual(state['workAreas'][result['workAreaId']]['completionTime'], 105)
        work = OriginalWorkRules(Definitions())
        task = {'duration': '61', 'skillId': '6'}
        self.assertEqual(work._duration(task, {'skills': [{'skilltypeId': 7}]}), 61)
        self.assertEqual(work._duration(task, {'skills': [{'skilltypeId': 6}] * 4}), 15)


class OriginalBirthSkillTests(unittest.TestCase):
    def test_baby_charm_colours_matching_extra_ranks_without_exceeding_mastery(self):
        from villagelife.protocol.original_client.birth_skills import newborn_shields

        class Definitions:
            def rows(self, table):
                return [{'id':str(i)} for i in (2,3,6,7)]

        inherited = [{'skilltypeId':2,'skillOriginType':2},
                     {'skilltypeId':2,'skillOriginType':1}]
        choice = {'skills':'3,6,7,2,2,2,6'}
        self.assertEqual(newborn_shields(Definitions(), inherited, choice, 3),[
            {'skilltypeId':2,'skillOriginType':2}, {'skilltypeId':2,'skillOriginType':1},
            {'skilltypeId':2,'skillOriginType':0}, {'skilltypeId':6,'skillOriginType':0},
        ])
        self.assertEqual(newborn_shields(Definitions(), inherited, {'skills':'3,6,7'}, 3),inherited)


class OriginalClientHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        fake_tables(root/'tables.sqlite3')
        self.repo=SqliteSaveRepository(root/'new.sqlite3')
        game=OriginalClientGame(self.repo,OriginalDefinitions(root/'tables.sqlite3'))
        self.server=ApiServer(('127.0.0.1',0),self.repo,game)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=4)

    def post(self,route:str,data:dict):
        request=urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}{route}',
                                       encode(data,compressed=True),method='POST')
        with urllib.request.urlopen(request,timeout=5) as response:
            self.assertEqual(response.status,200)
            return decode(response.read())[0]

    def login(self,device):
        return self.post('/web/ClientService/Login',{'deviceId':device})['data']['users'][0]

    def call(self,profile,service,data=None,call_id='1'):
        request={k:profile[k] for k in ('deviceId','sessionId','pId')}
        request['data']={'calls':[{'id':call_id,'service':service,'data':data or {}}]}
        return self.post('/web/ClientService/Process',request)['data']['calls'][0]

    def test_login_two_devices_and_persistence(self):
        a=self.login('device-A');b=self.login('device-B')
        self.assertNotEqual(a['pId'],b['pId'])
        refreshed=self.login('device-A')
        self.assertEqual(refreshed['pId'],a['pId'])
        a=refreshed
        self.assertEqual(self.call(a,'ClientUserHashService/GetUserHash')['code'],200)
        result=self.call(a,'ClientUserHashService/SetActiveSequence',{'activeSequence':217},'2')
        self.assertEqual(result['code'],200)
        second=self.call(b,'ClientUserHashService/GetUserHash')['data']['userHash']
        self.assertEqual(second['activeSequence'],0)
        first=self.call(a,'ClientUserHashService/GetUserHash')['data']['userHash']
        self.assertEqual(first['activeSequence'],217)
        self.assertEqual(first['data']['villagers'][0]['name'],'Example')

    def test_offline_consumption_does_not_create_an_empty_inbox_request(self):
        game = self.server.original
        profile = self.login('offline-inbox')
        identity = game.sessions.authenticate(profile)
        totals = {'FoodQuantity': 3, 'DrinksQuantity': 2, 'TotalXp': 5}

        def seed(payload):
            payload['originalSave']['normal'] = {
                'areaId': 1, 'world': {'entities': []}, 'user': {}, 'inventory': {},
                'offlineConsumption': totals,
            }
            return {}

        self.repo.mutate(identity.village_id, operation_key='fixture:offline-inbox', request={}, change=seed)
        empty = dict.fromkeys(totals, 0)
        for method in ('GetStartupInfo', 'GetStartupInfoForExtras'):
            result = self.call(profile, 'ClientStartupService/' + method)
            self.assertEqual(result['code'], 200)
            self.assertEqual(result['data']['OfflineConsumptionMessageModel'], empty)
        saved = self.repo.read_village(identity.village_id).payload['originalSave']['normal']
        self.assertEqual(saved['offlineConsumption'], totals)

    def test_two_npc_weddings_with_older_device_records(self):
        game = self.server.original
        old_profile = self.login('device-older')
        profile = self.login('device-family')
        identity = game.sessions.authenticate(profile)
        now = 1_800_000_000
        types = [{'id':str(i + 1), 'genderType':str(i), 'minAge':'18', 'maxAge':'55',
                  'isDateable':'1', 'maxEnergy':'40', 'name':'Adult'} for i in range(2)]
        variants = [{'id':'20', 'Gender':'1', 'startAge':'22', 'name':'Guest',
                     'equipment':{}, 'genetics':{}, 'villagerType':'2'}]
        rows = {'villager_type':types, 'villager_starting_variation':variants,
                'relation_type':[{'id':str(i), 'Relationship':str(group), 'genderTypeId':str(gender)}
                                 for i,group,gender in [(4,2,1),(5,2,0),(8,4,1),(9,4,0)]]}
        settings = {'communityDatesAvailable':'2', 'communityDatesExpiry':'500',
                    'date_return_time_seconds':'20', 'minAgeForDating':'18',
                    'maxAgeForMarriage':'55', 'marriage_want_delay':'30', 'hours_per_year':'24',
                    'WantIntervalRelationship':'5'}
        rows['global'] = [{'label':key, 'value':value} for key,value in settings.items()]

        def seed(payload):
            payload['originalSave']['normal'] = {
                'areaId':1, 'world':{'entities':[{'id':f'local-{i}', 'name':f'Local {i}',
                    'templateType':'villager_type', 'templateId':1, 'gender':0,
                    'startAge':22, 'bornAt':now, 'equipment':{}, 'rarity':1,
                    'position':{'x':5, 'areaId':1}, 'relations':[]} for i in range(2)]},
                'user':{'populationCap':4},
            }
            return {}

        self.repo.mutate(identity.village_id,operation_key='fixture:family',request={},change=seed)
        counter = iter(range(1, 60))

        def rpc(service, data=None):
            reply = self.call(profile,service,data,str(next(counter)))
            self.assertEqual(reply['code'],200,reply)
            return reply['data']

        def community(service,data=None,*,owner=None,expected=200):
            response = self.post('/Playdemic.Community.Web/Client/Home',
                                 {'UserId':int(owner or profile['pId']),
                                  'Calls':[{'Id:':1,'Service':service,'Data':data or {}}]})
            reply, = response['data']
            self.assertEqual(reply['code'],expected,reply)
            return reply['Data']

        with (patch.object(game.world,'global_values',settings),
              patch.object(game.defs,'rows',side_effect=rows.__getitem__),
              patch.object(game.dating,'npc_skills',side_effect=[(2,[]), (0,[])]),
              patch('villagelife.protocol.original_client.relationships.randbelow',return_value=0),
              patch('time.time',return_value=now) as clock):
            wishes = rpc('ClientWant/GenerateRelationshipWants')['result']
            self.assertEqual([w['MaterialID'] for w in wishes],[340,340])
            locals_by_suffix = {w['VillagerStringID'].rsplit('_',1)[1]:w['VillagerStringID'] for w in wishes}
            entries = rpc('ClientVillager/GetCommunityVillagers',{'Gender':1})['result']
            roster = [json.loads(entry['data']) for entry in entries]
            for local,npc in zip(locals_by_suffix.values(),roster,strict=True):
                rpc('ClientVillagerService/OptIntoCommunity',{'villagerId':local})
                invite = {'ForUserIds':[int(npc['user']['id'])],
                          'CharacterIds':[int(npc['villager']['id'].rsplit('_',1)[1])],
                          'FriendCharacterId':int(local.rsplit('_',1)[1])}
                community('CharacterRequest/Create',invite,owner=old_profile['pId'],expected=403)
                community('CharacterRequest/Create',invite)
                community('CharacterRequest/Create',invite)
            self.assertEqual(community('CharacterRequest/GetReceived')['CharacterRequests'],[])
            self.assertEqual(rpc('ClientWant/GenerateRelationshipWants')['result'],[])
            clock.return_value = now + 20
            dates = community('CharacterRequest/GetReceived')['CharacterRequests']
            self.assertEqual(len(dates),2)
            for date in dates:
                rpc('ClientRequest/AcceptDatingRequest',{'RequestID':date['ID']})
            def restore_stale_wishes(payload):
                payload['originalSave']['normal']['wants'] = [
                    {**wish, 'VillagerStringID':f'local-{i}'} for i, wish in enumerate(wishes)]
                return {}
            self.repo.mutate(identity.village_id,operation_key='fixture:stale-dating-wishes',
                             request={},change=restore_stale_wishes)
            self.assertEqual(rpc('ClientWant/GenerateRelationshipWants')['result'],[])
            clock.return_value = now + 50
            self.assertEqual([w['MaterialID'] for w in rpc('ClientWant/GenerateRelationshipWants')['result']],
                             [342,342])
            weddings = []
            for date in dates:
                npc = next(npc for npc in roster if npc['user']['id']==date['ByUserID'])
                proposal = rpc('ClientRequestService/SendMarriageRequest',{
                    'senderVillagerId':locals_by_suffix[date['CharacterID']],
                    'recipientVillagerId':npc['villager']['id'],
                    'recipientUserId':npc['user']['id'], 'stars':str(npc['villager']['rarity'])})['userRequest']
                weddings.append({'RequestID':proposal['id']})
            clock.return_value = now + 70
            notices = rpc('ClientUserService/GetUserNotifications')['userNotifications']
            self.assertEqual([n['notificationTypeId'] for n in notices],[12,12])
            for wedding in weddings:
                prepared = rpc('ClientRelationship/PrepareWedding',wedding)['result']
                self.assertTrue(prepared['Congregation'])
                principals = {prepared[k]['Name'] for k in ('Bride','Groom')}
                self.assertTrue(any(p['Name'] not in principals for p in prepared['Congregation']))
                rpc('ClientNotification/ProcessAcceptedProposal',wedding)
                rpc('ClientNotification/ProcessAcceptedProposal',wedding)
            startup = rpc('ClientStartupService/GetStartupInfo')
            people = {p['id']:p for p in startup['world']['entities']}
            self.assertEqual(len(people),4)
            for local in locals_by_suffix.values():
                relation, = people[local]['relations']
                self.assertEqual(relation['type'],4)
                self.assertEqual(people[relation['villagerId']]['relations'],
                                 [{'villagerId':local,'type':5}])

    def test_coming_of_age_notice_and_skill_are_stable_across_retries(self):
        game = self.server.original
        profile = self.login('device-birthday')
        identity = game.sessions.authenticate(profile)
        birthday = 1_800_000_000
        child = {'id':'11','genderType':'1','minAge':'5','maxAge':'12','canWork':'0','name':'Child'}
        teen = {'id':'13','genderType':'1','minAge':'13','maxAge':'17','canWork':'1','name':'Teen'}
        rows = {'villager_type':[child,teen], 'villager_skill':[{'id':'2','area':'1'}]}
        globals_ = {'hours_per_year':'24','coming_of_age':'13','skill_slots_max':'3'}
        mastered = [{'skilltypeId':2, 'skillOriginType':origin} for origin in (1,2,3)]

        def seed(payload):
            person = {'id':'child','name':'Child','templateType':'villager_type',
                      'templateId':11,'gender':1,'startAge':12,'bornAt':birthday-86400,'equipment':'test'}
            payload['originalSave']['normal'] = {
                'areaId':1, 'user':{'maxAreaId':1},
                'world':{'entities':[person, {**person, 'id':'maxed', 'name':'Maxed', 'skills':mastered}]},
            }
            return {}

        self.repo.mutate(identity.village_id,operation_key='fixture:birthday',request={},change=seed)
        state = self.repo.read_village(identity.village_id).payload['originalSave']['normal']
        local = mappings(state,profile['pId'])[0]['child']

        def call(service, data, call_id, expected=200):
            reply = self.call(profile,service,data,call_id)
            self.assertEqual(reply['code'],expected,reply)
            return reply['data']

        with (patch.object(game.world,'global_values',globals_),
              patch.object(game.defs,'rows',side_effect=rows.__getitem__),
              patch('time.time',return_value=birthday-1) as clock):
            self.assertEqual(call('ClientUserService/GetUserNotifications',{},'1')['userNotifications'],[])
            selection = {'villagerId':local,'skillTypeId':2}
            call('ClientVillagerService/SetVillagerSkill',selection,'2',400)
            clock.return_value = birthday
            startup = call('ClientStartupService/GetStartupInfo',{},'3')
            projected = startup['world']['entities'][0]
            self.assertEqual((projected['templateId'], projected['startAge'], projected['bornAt']),
                             (13, 13, birthday))
            notice, = call('ClientUserService/GetUserNotifications',{},'4')['userNotifications']
            self.assertEqual(notice['notificationTypeId'],0)
            self.assertEqual(notice['data']['recipient']['villager']['id'],local)
            auth = {k:profile[k] for k in ('deviceId','sessionId','pId')}
            reply = self.post('/web/ClientService/Process',{**auth,'data':{'calls':[]}})
            message, = reply['messages']
            self.assertEqual(message['data'],notice)
            call('ClientUserService/HandleUserMessages',{'userMessageIds':message['id']},'message')
            self.assertEqual(self.post('/web/ClientService/Process',
                                       {**auth,'data':{'calls':[]}})['messages'],[])
            call('ClientUserService/HandleUserNotification',{'userNotificationId':notice['id']},'5')
            self.assertEqual(call('ClientUserService/GetUserNotifications',{},'6')['userNotifications'],[notice])
            call('ClientVillagerService/SetVillagerSkill',selection,'7')
            call('ClientVillagerService/SetVillagerSkill',selection,'8')
            call('ClientVillagerService/SetVillagerSkill',{**selection,'skillTypeId':0},'9',400)
            self.assertEqual(call('ClientUserService/GetUserNotifications',{},'10')['userNotifications'],[])
            result = call('ClientVillagerService/GetVillagerSkills',{
                'villagerIds':json.dumps({'villagerIds':[local]})},'11')
            self.assertEqual(result['villagerSkills'],[
                {'villagerId':local,'skilltypeId':2,'skillOriginType':0}])
        person, maxed = self.repo.read_village(identity.village_id).payload['originalSave']['normal']['world']['entities']
        self.assertEqual((person['templateId'], person['startAge'], person['bornAt']),
                         (11, 12, birthday-86400))
        self.assertEqual(person['comingOfAgeCompletedAt'],birthday)
        self.assertEqual((maxed['comingOfAgeSkill'], maxed['comingOfAgeCompletedAt']), (0, birthday))
        self.assertEqual(maxed['skills'], mastered)

    def test_maxed_villager_can_complete_coming_of_age(self):
        from types import SimpleNamespace
        from villagelife.protocol.original_client.life_stages import OriginalLifeStages

        skills = [{'skilltypeId': 2, 'skillOriginType': 1}] * 3
        person = {'id': 'child', 'templateType': 'villager_type', 'skills': skills}
        state = {'areaId': 1, 'user': {'maxAreaId': 1}, 'world': {'entities': [person]}}
        definition = {'id': '2', 'area': '1'}
        defs = SimpleNamespace(item=lambda *_: definition, rows=lambda _: [definition])
        stages = OriginalLifeStages(SimpleNamespace(defs=defs, global_value=lambda _: '3'))
        with patch.object(stages, 'ready', return_value=100):
            selection = {'villagerId': 'child', 'skillTypeId': 2}
            self.assertEqual(stages.choose_skill(state, selection, 100), {})
            self.assertEqual(stages.choose_skill(state, selection, 101), {})
        self.assertEqual(person['skills'], skills)
        self.assertEqual(person['comingOfAgeCompletedAt'], 100)

    def test_imported_pregnancy_skip_returns_same_newborn_and_charges_once(self):
        game = self.server.original
        profile = self.login('device-birth')
        identity = game.sessions.authenticate(profile)
        now = 1_800_000_000
        seed = {'id':'30','refId':'baby female','name':'Newborn','equipment':'1','genetics':'2'}
        rows = {
            'villager_starting_variation':[seed],
            'villager_type':[{'id':str(i),'name':'Human','genderType':'1',
                              'minAge':'0','maxAge':'99'} for i in (4,1,5)],
            'relation_type':[],
            'global':[{'label':'hours_per_year','value':'24'}],
            'material_type':[{'id':'323'}],
            'villager_skill':[{'id':'2'},{'id':'3'},{'id':'7'}],
            'building_task':[],
            'requirement_set_item':[],
        }
        globals_ = {'gemCurveVariablePregnancySkipTime'+k:str(v)
                    for k,v in zip(('1min','1hour','1day','1week'),(60,3600,86400,604800))}
        globals_['hours_per_year'] = '24'
        globals_.update({'gemCalcPregnancySkipValue'+str(i):str(v)
                         for i,v in enumerate((1,3,33,125),1)})

        def seed_import(payload):
            people = [{'id':name,'name':name,'templateType':'villager_type','templateId':kind,
                       'gender':gender,'position':{'x':10,'y':20,'areaId':1},
                       'pregnant':flag,'relations':[]}
                      for name,kind,gender,flag in [('mother',5,1,'true'),('father',1,0,'false')]]
            people[0]['skills'] = [{'skilltypeId':7,'skillOriginType':3},
                                   {'skilltypeId':2,'skillOriginType':0}]
            people[1]['skills'] = [{'skilltypeId':3,'skillOriginType':0}]
            payload['originalSave']['normal'] = {
                'areaId':1, 'world':{'entities':people}, 'inventory':{'323':12},
                'user':{'populationCap':4,'maxAreaId':0}, 'pregnancies':{'mother':{
                    'id':'legacy-birth','motherId':'mother','fatherId':'father',
                    'status':'pregnant','readyAt':now+86400,
                    'children':[{'rawId':'legacy-child','seedId':'30','gender':1}]}},
            }
            return {}

        self.repo.mutate(identity.village_id,operation_key='fixture:imported-birth',request={},change=seed_import)
        state = self.repo.read_village(identity.village_id).payload['originalSave']['normal']
        outward,_ = mappings(state,profile['pId'])
        request = {'motherVillagerId':outward['mother'],'fatherVillagerId':outward['father'],'areaId':1}
        with (patch.object(game.world,'global_values',globals_),
              patch.object(game.defs,'rows',side_effect=rows.__getitem__),
              patch('time.time',return_value=now)):
            rejected = self.call(profile,'ClientVillagerService/SkipPregnancy',request,'skip')
            self.assertEqual(rejected['code'],400,rejected)
            self.assertEqual(rejected['data'],{'error':'INSUFFICIENT_GEMS',
                                             'gemsRequired':33,'gemsAvailable':12,'gemsShortfall':21})
            snapshot = self.repo.read_village(identity.village_id)
            self.assertEqual(snapshot.payload['originalSave']['normal'],state)

            def credit_fixture(payload):
                payload['originalSave']['normal']['inventory']['323'] = 100
                return {}

            self.repo.mutate(identity.village_id,operation_key='fixture:enough-gems',
                             request={},change=credit_fixture)
            skipped = self.call(profile,'ClientVillagerService/SkipPregnancy',request,'skip')
            self.assertEqual(skipped['code'],200,skipped)
            newborn, = skipped['data']['result']['villagers']
            self.assertEqual(newborn['Skills'],[
                {'SkillTypeID':3,'SkillSourceType':2},
                {'SkillTypeID':2,'SkillSourceType':1},
            ])
            inventory, = skipped['data']['result']['inventory']
            self.assertEqual(inventory['amount'],67)
            repeat = self.call(profile,'ClientVillagerService/SkipPregnancy',request,'skip-again')
            self.assertEqual(repeat['data'],skipped['data'])
            new_id = 'Villager_'+profile['pId']+'_'+newborn['ID']
            named = self.call(profile,'ClientVillagerService/SetName',{'villagerId':new_id,'name':'Renamed'},'name')
            self.assertEqual(named['code'],200,named)
            startup = self.call(profile,'ClientStartupService/GetStartupInfo',{},'startup')
            self.assertEqual(startup['code'],200,startup)
            child = next(p for p in startup['data']['world']['entities'] if p['id']==new_id)
            self.assertEqual(child['skills'],[
                {'type':3,'skillOriginType':2}, {'type':2,'skillOriginType':1},
            ])
        state = self.repo.read_village(identity.village_id).payload['originalSave']['normal']
        self.assertEqual(len(state['world']['entities']),3)
        self.assertEqual(state['world']['entities'][-1]['name'],'Renamed')
        self.assertEqual(state['inventory']['323'],67)

    def test_decor_placement_charges_once_and_reappears_after_reconnect(self):
        game = self.server.original
        device = {'deviceId':'device-decor'}
        profile = game.login(device)['data']['users'][0]
        identity = game.sessions.authenticate(profile)

        def seed(payload):
            payload['originalSave']['normal'] = {
                'areaId':1, 'world':{'entities':[]}, 'inventory':{'325':100}, 'user':{},
            }
            return {}

        self.repo.mutate(identity.village_id, operation_key='fixture:decor', request={}, change=seed)

        def call(service, data, call_id):
            return self.call(profile, service, data, call_id)

        request = {'decorItemId':7,'areaId':1,'x':-10.5,'y':20.5,'rotation':1}
        service = 'ClientUserDecorItemService/CreateUserDecorItem'
        rejected = call(service, request, 'locked')
        self.assertEqual(rejected['code'], 400, rejected)
        self.assertIn('unlock requirement', rejected['message'])

        def cross_bridge(payload):
            payload['originalSave']['normal'].update(
                transitionKey='bridge-1-to-2', scenarioId=2)
            return {}

        self.repo.mutate(identity.village_id, operation_key='fixture:bridge', request={}, change=cross_bridge)
        placed = call(service, request, 'place')
        self.assertEqual(placed['code'], 200, placed)
        self.assertEqual(call(service, request, 'place'), placed)
        self.assertEqual(call(service, {**request, 'x':12}, 'other')['code'], 400)
        profile = game.login(device)['data']['users'][0]
        area = call('ClientStartupService/GetAreaContent', {'areaId':1}, 'reload')
        entities = [entity for entity in area['data']['areaJson']['entities']
                    if entity['templateType'] == 'decor_item']
        self.assertEqual(len(entities), 1)
        decor = placed['data']['userDecorItem']
        self.assertEqual(entities[0]['id'], decor['userDecorItemId'])
        self.assertEqual(entities[0]['position'], decor['position'])
        inventory = call('ClientMaterialService/GetUserMaterialTypes', {}, 'inventory')
        amounts = {row['materialTypeId']:row['amount'] for row in inventory['data']['inventory']}
        self.assertEqual((amounts[325], amounts[700], amounts[130]), (40, 1, 1))
        self.assertNotIn('130', self.repo.read_village(identity.village_id).payload
                         ['originalSave']['normal']['inventory'])
        move = {**decor['position'], 'positionId': decor['position']['id'], 'rotation': 2}
        self.assertEqual(call('ClientUtilityService/UpdatePosition', move, 'rotate')['code'], 200)
        area = call('ClientStartupService/GetAreaContent', {'areaId':1}, 'rotated')
        self.assertEqual(area['data']['areaJson']['entities'][0]['position']['rotation'], 2)
        removed = call('ClientUserDecorItemService/DeleteUserDecorItem',
                       {'userDecorItemId': decor['userDecorItemId']}, 'remove')
        self.assertEqual(removed['code'], 200, removed)
        area = call('ClientStartupService/GetAreaContent', {'areaId':1}, 'removed')
        self.assertEqual(area['data']['areaJson']['entities'], [])

    def test_login_repairs_completed_farm_foundation_without_removing_other_sites(self):
        profile = self.login('device-farm-ghost')
        ident = self.server.original.sessions.authenticate(profile)

        def seed(payload):
            position = {'areaId':1,'x':100,'y':100,'rotation':0}
            base = {'templateType':'building_task','templateId':8,'serverPersisted':True}
            payload['originalSave']['normal'] = {
                'areaId':1,'user':{},'inventory':{},'world':{'entities':[
                    {**base,'id':'obsolete','position':position},
                    {**base,'id':'other-site','position':{**position,'y':150}},
                    {'id':'completed-farm','templateType':'farm_building','templateId':0,
                     'localCreated':True,'serverPersisted':True,'position':{**position,'y':101}},
                ]},
            }
            return {}

        self.repo.mutate(ident.village_id, operation_key='fixture:farm-ghost', request={}, change=seed)
        for _ in range(2):
            profile = self.login('device-farm-ghost')
            response = self.call(profile, 'ClientStartupService/GetAreaContent', {'areaId':1}, 'area')
            self.assertEqual(response['code'], 200, response)
            self.assertEqual({row['id'] for row in response['data']['areaJson']['entities']},
                             {'other-site','completed-farm'})

    def test_villager_skill_purchase_ranks_and_bundle_survive_relogin(self):
        device = 'device-skill'
        profile = self.login(device)
        ident = self.server.original.sessions.authenticate(profile)

        def seed(payload):
            payload['originalSave']['normal'] = {
                'areaId':1,'user':{'maxAreaId':1},'inventory':{'323':1000},
                'world':{'entities':[{'id':'fixture-trainee','templateType':'villager_type',
                                      'templateId':1,'startAge':21,'skills':[]}]},
            }
            return {}

        self.repo.mutate(ident.village_id, operation_key='fixture:skill', request={}, change=seed)
        snap = self.repo.read_village(ident.village_id).payload['originalSave']['normal']
        outward,_ = mappings(snap,ident.player_id)
        target = {'villagerId':outward['fixture-trainee']}
        single = 'ClientVillagerService/BuyVillagerSkill'
        bundle = 'ClientVillagerService/BuySkillsBundle'
        self.assertEqual(self.call(profile,single,{**target,'skillTypeId':8},'locked')['code'],400)
        learned = self.call(profile,single,{**target,'skillTypeId':2},'learn')
        self.assertEqual(learned['code'],200,learned)
        self.assertEqual(self.call(profile,single,{**target,'skillTypeId':2},'learn'),learned)
        self.assertEqual(self.call(profile,bundle,target,'bundle')['code'],200)
        profile = self.login(device)
        result = self.call(profile,'ClientVillagerService/GetVillagerSkills',
                           {'villagerIds':json.dumps({'villagerIds':[target['villagerId']]})},'read')
        self.assertEqual(result['code'],200,result)
        skills = result['data']['villagerSkills']
        self.assertEqual([row['skilltypeId'] for row in skills],[2,2,2,3,3,3])
        self.assertTrue(all(row['skillOriginType']==3 for row in skills))
        self.assertEqual(self.call(profile,bundle,target,'bundle-again')['code'],200)
        saved = self.repo.read_village(ident.village_id).payload['originalSave']['normal']
        self.assertEqual(saved['inventory']['323'],1000-95-5*76)

    def test_native_farm_plot_placement_persists_and_enforces_capacity(self):
        profile = self.login('device-farm')
        ident = self.server.original.sessions.authenticate(profile)

        def seed(payload):
            payload['originalSave']['normal'] = {
                'areaId':1, 'user':{}, 'inventory':{}, 'world':{'entities':[
                    {'id':'fixture-farm','templateType':'farm_building','templateId':0,
                     'localCreated':True,'serverPersisted':True,
                     'position':{'areaId':1,'x':40,'y':60,'rotation':0}},
                ]},
            }
            return {}

        self.repo.mutate(ident.village_id, operation_key='fixture:farm', request={}, change=seed)
        service = 'ClientFarmingService/PlaceFarmPlot'
        position = {'areaId':1, 'x':-18, 'y':60, 'rotation':0}
        placed = self.call(profile, service, position, 'place')
        self.assertEqual(placed['code'], 200, placed)
        self.assertEqual(self.call(profile, service, position, 'replay')['data'], placed['data'])
        self.assertEqual(self.call(profile, service, {**position,'x':28}, 'extra')['code'], 400)
        profile = self.login('device-farm')
        response = self.call(profile, 'ClientStartupService/GetAreaContent', {'areaId':1}, 'reload')
        plots = [e for e in response['data']['areaJson']['entities'] if e['templateType']=='farming_plot']
        self.assertEqual(len(plots), 1)
        self.assertEqual(plots[0]['id'], placed['data']['userFarmPlot']['userFarmPlotId'])
        self.assertEqual(plots[0]['position'], placed['data']['userFarmPlot']['position'])

    def test_saved_happiness_and_shelter_slots_through_native_requests(self):
        profile = self.login('device-happiness')
        identity = self.server.original.sessions.authenticate(profile)

        def seed(payload):
            position = {'areaId':1,'x':50,'y':60,'rotation':0}
            payload['originalSave']['normal'] = {
                'areaId':1, 'user':{'xp':32}, 'inventory':{},
                'world':{'entities':[
                    {'id':'fixture-actor','templateType':'villager_type','templateId':1,
                     'serverPersisted':True,'position':position,'xp':8},
                    {'id':'fixture-home','templateType':'shelter','templateId':0,
                     'localCreated':True,'serverPersisted':True,'position':position,
                     'happinessCollectedAt':0,'beds':[
                        {'id':'fixture-bed','shelterSlotID':12,'villagerId':''},
                        {'id':'fixture-bed2','shelterSlotID':13,'villagerId':''},
                     ]},
                ]},
            }
            return {}

        self.repo.mutate(identity.village_id, operation_key='fixture:home', request={}, change=seed)
        result = self.call(profile, 'ClientStartupService/GetAreaContent', {'areaId':1}, 'area')
        self.assertEqual(result['code'], 200, result)
        actor, home = result['data']['areaJson']['entities']
        bed = home['beds'][0]['bed']
        self.assertEqual(bed['shelterSlotID'], 12)
        assigned = self.call(profile, 'ClientUserShelterService/AssignBedToVillager',
                             {'shelterBedId':bed['id'], 'villagerId':actor['id']}, 'assign')
        self.assertEqual(assigned['code'], 200, assigned)
        xp_service = 'ClientVillager/ReleaseXp'
        xp_request = {'VillagerStringID':actor['id']}
        collected = self.call(profile, xp_service, xp_request, 'collect')
        self.assertEqual(collected['code'], 200, collected)
        self.assertEqual(collected['data']['result']['UserXp'], 40)
        self.assertEqual(self.call(profile, xp_service, xp_request, 'collect'), collected)
        self.assertEqual(self.call(profile, xp_service, xp_request, 'collect-again')['data']
                         ['result']['UserXp'], 40)
        emptied = self.call(profile, 'ClientUserShelterService/EmptyBed',
                            {'shelterBedId':bed['id']}, 'empty')
        self.assertEqual(emptied['code'], 200, emptied)
        state = self.repo.read_village(identity.village_id).payload['originalSave']['normal']
        person, shelter = state['world']['entities']
        self.assertEqual((state['user']['xp'], person['xp'], person['shelterBedId']), (40, 0, ''))
        self.assertEqual(shelter['beds'][0]['villagerId'], '')
        self.assertEqual(shelter['beds'][0]['id'], 'fixture-bed')

    def test_material_learning_survives_relogin_and_skip_charges_once(self):
        device = 'device-learning'
        profile = self.login(device)
        ident = self.server.original.sessions.authenticate(profile)

        def seed(payload):
            payload['originalSave']['normal'] = {
                'areaId':1, 'world':{'entities':[]}, 'user':{'userLevelID':2},
                'inventory':{'323':10},
            }
            return {}

        self.repo.mutate(ident.village_id, operation_key='fixture:learn', request={}, change=seed)
        def learn(action, material, at, call_id):
            with patch('villagelife.protocol.original_client.services.time') as clock:
                clock.time.return_value = at
                return self.call(profile, f'ClientMaterialService/{action}LearningMaterial',
                                 {'materialTypeId':material}, call_id)

        self.assertEqual(learn('Start', 179, 1000, 'parent-locked')['code'], 400)
        started = learn('Start', 178, 1000, 'start')
        self.assertEqual(started['code'], 200, started)
        self.assertEqual(started['data']['result'], {'UpdatedTime':1000,'Gem':10})
        locked = next(row for row in started['data']['inventory'] if row['materialTypeId']==178)
        self.assertEqual((locked['isUnlocked'], locked['amount']), (False, 0))
        self.assertEqual(learn('Start', 178, 1010, 'retry')['data'], started['data'])
        self.assertEqual(learn('Complete', 178, 1059, 'early')['code'], 400)
        profile = self.login(device)
        completed = learn('Complete', 178, 1060, 'complete')
        self.assertEqual(completed['code'], 200, completed)
        self.assertEqual(completed['data']['result']['Gem'], 10)
        self.assertEqual(learn('Start', 179, 1060, 'next')['code'], 200)
        skipped = learn('Skip', 179, 1061, 'skip')
        self.assertEqual(skipped['code'], 200, skipped)
        self.assertEqual(skipped['data']['result']['Gem'], 9)
        profile = self.login(device)
        self.assertEqual(learn('Skip', 179, 1062, 'skip-retry')['data'], skipped['data'])
        amounts = {row['materialTypeId']:row for row in skipped['data']['inventory']}
        for material in (178, 179):
            self.assertEqual((amounts[material]['isUnlocked'], amounts[material]['amount']), (True, 0))

    def test_login_rotates_session_and_rpc_ids_can_restart_safely(self):
        before=self.login('device-A')
        result=self.call(before,'ClientSettingService/SaveGameSetting',
                         {'key':'sound','value':'off'},'1')
        self.assertEqual(result['code'],200)
        after=self.login('device-A')
        self.assertEqual(before['pId'],after['pId'])
        self.assertNotEqual(before['sessionId'],after['sessionId'])
        self.assertEqual(self.call(before,'ClientUserHashService/GetUserHash')['code'],403)
        # Fresh login: the same client-generated request ID must be independent.
        result=self.call(after,'ClientSettingService/SaveGameSetting',
                         {'key':'sound','value':'on'},'1')
        self.assertEqual(result['code'],200)
        settings=self.call(after,'ClientSettingService/GetUserGameSettings')['data']['gameSettings']
        self.assertIn({'key':'sound','value':'on'},settings)

    def test_session_forgery_unknown_calls_and_replay(self):
        a=self.login('device-A');b=self.login('device-B')
        fake={**a,'sessionId':b['sessionId']}
        self.assertEqual(self.call(fake,'ClientUserHashService/GetUserHash')['code'],403)
        self.assertEqual(self.call(a,'ClientTaskService/HarvestTask',{'amount':999999})['code'],400)
        # This route now has a handler; a malformed request is validation failure,
        # not evidence that the operation is unimplemented.
        self.assertEqual(self.call(a,'ClientTaskService/StartBuildingTask',{'amount':999999})['code'],400)
        self.assertEqual(self.call(a,'ClientExampleService/UnknownOperation')['code'],501)
        self.assertEqual(self.call(a,'ClientSettingService/SaveGameSetting',
                                   {'key':'musicEnabled','value':'false'},'save-1')['code'],200)
        self.assertEqual(self.call(a,'ClientSettingService/SaveGameSetting',
                                   {'key':'musicEnabled','value':'true'},'save-1')['code'],409)
        self.assertEqual(self.call(a,'ClientSettingService/GetUserGameSettings')['data'],
                         {'gameSettings':[{'key':'musicEnabled','value':'false'}]})
        with self.repo.connect() as conn:
            count=conn.execute('SELECT count(*) FROM missing_requests').fetchone()[0]
        self.assertGreaterEqual(count,1)

    def test_reject_malformed_nonempty_and_empty_session(self):
        p=self.login('other')
        self.assertEqual(self.call(p,'ClientUserHashService/SetActiveSequence',
                                   {'activeSequence':500000})['code'],400)
        self.assertEqual(self.call(p,'ClientUserHashService/GetUserHash')['data']['userHash']['activeSequence'],0)

    def test_imported_state_can_bind_by_device_hash(self):
        profile=self.login('device-legacy')
        import hashlib
        name=hashlib.sha256('device-legacy2'.encode()).hexdigest()
        folder=Path(self.temp.name)/'historical';folder.mkdir()
        legacy={'pId':'2345678','deviceId':'device-legacy2','sessionId':'not-used','createdAt':123,
                'isNewUser':False}
        state={'version':4,'userHash':{'activeSequence':217,'data':{'villagers':[]}},
               'gameSettings':{},'normal':{'areaId':1,'world':{'entities':[]},
               'user':{'userLevelID':1,'scenarioId':2}}}
        (folder/(name+'.json')).write_text(json.dumps(legacy),encoding='utf-8')
        (folder/(name+'.tutorial.json')).write_text(json.dumps(state),encoding='utf-8')
        result=LegacySaveImporter(self.repo).import_directory(folder,apply=True)
        self.assertEqual(result[0].status,'imported (original untouched)')
        imported=self.login('device-legacy2')
        self.assertEqual(imported['pId'],'2345678')
        self.assertFalse(imported['isNewUser'])
        self.assertEqual(self.call(imported,'ClientUserHashService/GetUserHash')['data']['userHash']['activeSequence'],217)
        self.assertEqual(json.loads((folder/(name+'.tutorial.json')).read_text()),state)

    def test_native_ids_are_owner_scoped(self):
        world={'world':{'entities':[{'id':'Alice','templateType':'villager_type'},
                                   {'id':'Bob','templateType':'villager_type'}]}}
        first,inbound=mappings(world,'1234')
        self.assertNotEqual(first['Alice'],mappings(world,'9999')[0]['Alice'])
        self.assertEqual(translate({'villagerId':'Alice'},first)['villagerId'],first['Alice'])
        self.assertEqual(translate({'villagerId':first['Alice']},inbound)['villagerId'],'Alice')


class OriginalAssetTests(unittest.TestCase):
    def test_manifest_and_bounded_original_resources(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);apk=root/'com.example.apk';xapk=root/'test.xapk';obb=root/'main.obb'
            with zipfile.ZipFile(apk,'w') as z:z.writestr('assets/origmanifest.xml',b'<manifest>example</manifest>')
            with zipfile.ZipFile(xapk,'w') as z:z.write(apk,apk.name)
            obb.write_bytes(b'ABCDEFGH')
            inventory=root/'inventory.csv'
            with inventory.open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=['path','offset_in_tcf','stored_bytes']);writer.writeheader()
                writer.writerow({'path':'files/test/item.bin','offset_in_tcf':2,'stored_bytes':4})
            assets=ClientAssets(xapk=xapk,obb=obb,inventory=inventory)
            self.assertEqual(assets.manifest,b'<manifest>example</manifest>')
            self.assertEqual(assets.content('/assets/v270/files/test/item.bin'),b'CDEF')
            self.assertIsNone(assets.content('/files/absent'))
