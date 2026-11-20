"""Invented fixtures for duplicate community ticket symptoms, November 2026."""
import copy
from pathlib import Path
import tempfile
import unittest
import json
from types import SimpleNamespace
from unittest.mock import patch

from villagelife.persistence.history import History
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.protocol.original_client.buildings import OriginalBuildingRules
from villagelife.protocol.original_client.habitats import OriginalHabitatRules
from villagelife.protocol.original_client.inventory import OriginalInventoryRules
from villagelife.protocol.original_client.wants import OriginalWantRules
from test_original_daily import Definitions as DailyDefinitions
from test_original_gathering_duration import Definitions as WorkDefinitions
from test_original_client import fake_tables
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.services import OriginalClientGame
from villagelife.support import begin_diagnostic_run
from villagelife.protocol.original_client.work import OriginalWorkRules
from villagelife.protocol.original_client.birth_skills import (
    parent_shields, restore_birth_shields, restore_starter_shields)
from villagelife.protocol.original_client.villagers import OriginalVillagerRules
from villagelife.protocol.original_client.charms import OriginalBabyCharmRules
from villagelife.protocol.original_client.family import OriginalFamilyRules
from villagelife.protocol.original_client.quests import OriginalQuestRules


class Definitions:
    def rows(self, table):
        return {
            'seq_state_tablet_ftue': [{'sequenceType':'64', 'dataJSON':'{"inventory":{"501":1,"502":1}}'}],
            'task': [{'taskType':'1', 'rewardSet':'5'}],
            'reward_set_item': [{'setId':'5','materialType':'502','quantity':'1','chance':'1'}],
            'material_mastery': [{'materialType':'501','materialRequirement':'601'},
                                 {'materialType':'502','materialRequirement':'602'}],
            'material_type': [{'id':'501','categoryId':'12'}, {'id':'502','categoryId':'12'}],
            'building_task': [{'id':'7','buildingType':'10','parentId':'-1'},
                              {'id':'8','buildingType':'11','parentId':'7'}],
            'building_type': [{'id':'10','entityRef':'workshop','entityID':'1','materialType':'701'},
                              {'id':'11','entityRef':'workshop','entityID':'2','materialType':'702'}],
            'workshop': [{'id':'1'},{'id':'2'}],
            'villager_skill': [{'id':str(i)} for i in (2,3,6,7)],
            'gachaVillager': [{'id':'741','star':'6','name':'Invented Hero','genderType':'0',
                'ageRange':'0,13,18','villagerType':'3,12,1','equipment':'invented-equipment',
                'skills':'2,3,6,2,2,3,3,6,6'}],
            'villager_type': [{'id':str(i),'minAge':str(low),'maxAge':str(high),'maxEnergy':'40'}
                              for i,low,high in [(3,0,4),(12,13,17),(1,18,100)]],
        }.get(table, [])

    def item(self, table, ident):
        for row in self.rows(table):
            if row.get('id') == str(ident):
                return row
        raise KeyError((table, ident))


class TicketRegressions(unittest.TestCase):
    def test_foundation_cleanup_and_travel_checks_use_direct_archived_references(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo=SqliteSaveRepository(Path(temporary)/'worlds.sqlite3')
            normal={'world':{'entities':[]},
                'completedFoundationJobs':{'site':'finished'},
                'workAreas':{'finished':{'id':'finished','sourceId':'site','family':'2','status':'harvested'}},
                'completedQuests':{'travel':{'quest':{'questTypeId':12,'objectId':'24'}},
                    **{str(i):{'quest':{'questTypeId':1,'objectId':'other'}} for i in range(3000)}}}
            OriginalQuestRules.completed_travel_stories(normal)
            village=repo.create_village(repo.create_account(),{'originalSave':{'normal':normal}})
            repo.enable_history_storage()
            repo.mutate(village,operation_key='archive',request={},change=lambda state:{})
            def cleanup(payload):
                state=payload['originalSave']['normal']
                OriginalBuildingRules(Definitions()).delete(state,{'userBuildingTaskId':'site'})
                stories=OriginalQuestRules.completed_travel_stories(state)
                self.assertEqual(stories['24']['quest']['objectId'],'24')
                return {}
            with patch.object(History,'__iter__',side_effect=AssertionError('scanned completed history')):
                repo.mutate(village,operation_key='cleanup',request={},change=cleanup)
            self.assertEqual(repo.read_village(village).payload['originalSave']['normal']['deletedFoundations'],['site'])

    def test_diagnostics_measure_inventory_action_without_identifiers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);fake_tables(root/'tables.sqlite3')
            repo=SqliteSaveRepository(root/'worlds.sqlite3')
            game=OriginalClientGame(repo,OriginalDefinitions(root/'tables.sqlite3'))
            profile=game.login({'deviceId':'invented-timing-device'})['data']['users'][0]
            identity=game.sessions.authenticate(profile)
            def prepare(payload):
                payload['originalSave']['normal']={'areaId':1,'world':{'entities':[]},
                    'user':{'maxAreaId':1},'inventory':{}}
                return {}
            repo.mutate(identity.village_id,operation_key='timing-seed',request={},change=prepare)
            begin_diagnostic_run(repo)
            request={key:profile[key] for key in ('deviceId','pId','sessionId')}
            request['data']={'calls':[{'id':'read','service':'ClientMaterialService/GetUserMaterialTypes','data':{}}]}
            self.assertEqual(game.process(request)['data']['calls'][0]['code'],200)
            with repo.connect() as db:
                row=db.execute("select count,total_ms,max_ms from request_timings where phase='rpc_inventory'").fetchone()
                self.assertEqual(row['count'],1)
                self.assertGreaterEqual(row['total_ms'],0)
                self.assertGreaterEqual(row['max_ms'],0)

    def test_food_wishes_follow_the_current_area_and_do_not_fall_back_to_woodland(self):
        class RegionalDefinitions(DailyDefinitions):
            def rows(self,table):
                base=super().rows(table)
                if table=='material_type':
                    return [{**r,'area':'1'} if r['id']=='107' else r for r in base]+[
                        {'id':'115','categoryId':'8','area':'2','unlockLevel':'1'},
                        {'id':'1463','categoryId':'8','area':'3','unlockLevel':'1'},
                        {'id':'171','categoryId':'31','area':'2','unlockLevel':'1'},
                        {'id':'172','categoryId':'31','area':'3','unlockLevel':'1'}]
                if table=='building_type':return [
                    {'entityRef':'shelter','materialType':'171'},{'entityRef':'shelter','materialType':'172'}]
                if table=='task':return [{'id':'71','rewardSet':'81'},{'id':'72','rewardSet':'82'}]
                if table=='reward_set_item':return [
                    {'setId':'81','materialType':'115','quantity':'1','chance':'1'},
                    {'setId':'82','materialType':'1463','quantity':'1','chance':'1'}]
                if table=='material_source':return [{'id':'1','task':'71'},{'id':'2','task':'72'}]
                return base
        rules=OriginalWantRules(RegionalDefinitions())
        adult={'id':'caregiver','templateType':'villager_type','templateId':1,
               'startAge':21,'bornAt':1000,'position':{'areaId':2},'xp':0}
        state={'areaId':2,'world':{'entities':[adult,
                    {'templateType':'material_source','templateId':1,'position':{'areaId':2}},
                    {'templateType':'material_source','templateId':2,'position':{'areaId':3}}]},
               'user':{'userLevelID':3},'inventory':{'107':5,'115':5,'1463':5},
               'wants':[{'WantId':1,'VillagerStringID':'caregiver','MaterialID':107,'wantableCategoryType':2}]}
        self.assertEqual(rules.generate(state,'ClientWant/GenerateFoodWants',1000)['result'][0]['MaterialID'],115)
        shelters=rules.generate(state,'ClientWant/GenerateShelterWants',1000)['result']
        self.assertEqual(next(w for w in shelters if w['wantableCategoryType']==6)['MaterialID'],171)
        state['areaId']=adult['position']['areaId']=3
        food=rules.generate(state,'ClientWant/GenerateFoodWants',1001)['result']
        self.assertEqual(next(w for w in food if w['wantableCategoryType']==2)['MaterialID'],1463)
        shelters=rules.generate(state,'ClientWant/GenerateShelterWants',1001)['result']
        self.assertEqual(next(w for w in shelters if w['wantableCategoryType']==6)['MaterialID'],172)
        # A hungry villager with no local food in stock asks for a gatherable
        # food from their own area, rather than an unavailable Woodland fruit.
        state['wants']=[];state['inventory']['1463']=0
        self.assertEqual(rules.generate(state,'ClientWant/GenerateFoodWants',1002)['result'][0]['MaterialID'],1463)

    def test_disabled_reward_rows_do_not_block_deterministic_work_but_random_rewards_still_reject(self):
        class RewardDefinitions(WorkDefinitions):
            chance='0'
            def rows(self,table):
                rows=super().rows(table)
                if table=='reward_set_item':
                    return rows+[{'setId':'2','chance':self.chance,'quantity':'1','materialType':'99'},
                                 {'setId':'2','chance':'1','quantity':'0','materialType':'98'}]
                return rows
        defs=RewardDefinitions();rules=OriginalWorkRules(defs)
        initial={'areaId':1,'world':{'entities':[
            {'id':'worker','templateType':'villager_type','templateId':1,'position':{'areaId':1}},
            {'id':'source','templateType':'material_source','templateId':1,
             'position':{'areaId':1,'x':10,'y':20}}]},'inventory':{}}
        request={'areaId':1,'taskTypeId':31,'villagerId':'worker','userMaterialSourceId':'source','x':10,'y':20}
        state=copy.deepcopy(initial)
        reply=rules.start(state,'ClientTaskService/StartGatheringTask',request,100)
        self.assertEqual(state['workAreas'][reply['workAreaId']]['rewards'],[{'materialTypeId':5,'amount':1}])
        defs.chance='0.5';state=copy.deepcopy(initial)
        with self.assertRaises(NotImplementedError):
            rules.start(state,'ClientTaskService/StartGatheringTask',request,100)
        self.assertEqual(state,initial)

    def test_saved_pregnancy_cannot_be_overwritten_when_its_display_flag_is_missing(self):
        rules=OriginalFamilyRules(SimpleNamespace(defs=Definitions()),None,None)
        mother={'id':'mother','templateType':'villager_type','gender':1,'pregnant':'false'}
        record={'status':'pregnant','fatherId':'father','attemptedAt':100,
                'children':[{'id':'planned-baby'}],'designFinalized':True,'readyAt':1000}
        state={'world':{'entities':[mother]},'pregnancies':{'mother':record},
               'inventory':{'323':25},'wants':[{'WantId':1,'VillagerStringID':'mother',
                   'MaterialID':'343','wantableCategoryType':5}]}
        before=copy.deepcopy(record)
        result=rules.conceive(state,{'villagerId':'mother'},200,None)
        self.assertEqual(record,before)
        self.assertEqual(state['inventory'],{'323':25})
        self.assertEqual(state['wants'],[])
        self.assertEqual(result['result']['PregnancyInfo']['pregnant'],1)
        self.assertEqual(result['result']['SatisfiedWantModels'],[{'WantId':1,'VillagerStringID':'mother'}])
        state['wants']=[{'WantId':2,'VillagerStringID':'mother','MaterialID':'343','wantableCategoryType':5}]
        with patch.object(rules,'eligible',return_value=False):
            self.assertEqual(rules.generate(state,201)['result'],[])

    def test_starter_shields_persist_and_children_use_the_actual_parent_professions(self):
        class StarterDefinitions(Definitions):
            def rows(self,table):
                return {
                    'villager_skill':[{'id':str(i),'area':'1'} for i in (2,3,6,7)],
                    'seq_state_tablet_ftue':[{'sequenceType':'62','dataJSON':json.dumps({'refId':ref})}
                                            for ref in ('father','mother','baby')],
                    'villager_starting_variation':[
                        {'id':str(i),'refId':ref,'startAge':str(age),'equipment':'seed-'+ref}
                        for i,ref,age in [(1,'father',21),(2,'mother',21),(3,'baby',0)]],
                }.get(table,super().rows(table))
        father={'id':'father','templateType':'villager_type','villagerBaseId':1,'refId':'father',
                'equipment':'seed-father','gender':0,'skills':[{'type':6,'skillOriginType':0}]}
        mother={'id':'mother','templateType':'villager_type','villagerBaseId':2,'refId':'mother',
                'equipment':'seed-mother','gender':1,'skills':[{'type':7,'skillOriginType':0}]}
        baby={'id':'baby','templateType':'villager_type','villagerBaseId':3,'refId':'baby',
              'equipment':'seed-baby','gender':1,'skills':[],
              'relations':[{'villagerId':'mother','type':0},{'villagerId':'father','type':0}]}
        unrelated={**copy.deepcopy(father),'id':'other','equipment':'not-the-authored-appearance','skills':[]}
        state={'world':{'entities':[baby,father,mother,unrelated]}}
        self.assertTrue(restore_starter_shields(StarterDefinitions(),state))
        self.assertEqual([len(p['skills']) for p in (father,mother,baby)],[3,3,2])
        self.assertEqual(baby['skills'],[{'skilltypeId':6,'skillOriginType':2},
                                       {'skilltypeId':7,'skillOriginType':1}])
        self.assertEqual(unrelated['skills'],[])
        before=copy.deepcopy(state)
        self.assertFalse(restore_starter_shields(StarterDefinitions(),state))
        self.assertEqual(state,before)

    def test_imported_skill_field_spellings_have_the_same_read_contract(self):
        rules=OriginalVillagerRules(Definitions())
        for spelling in ('type','skillTypeId','skilltypeId'):
            state={'world':{'entities':[{'id':'person','templateType':'villager_type',
                    'skills':[{spelling:6,'skillOriginType':1}]}]}}
            self.assertEqual(rules.skills(state,{'villagerIds':json.dumps({'villagerIds':['person']})}),
                             {'villagerSkills':[{'villagerId':'person','skilltypeId':6,'skillOriginType':1}]})

    def test_adult_charm_has_parent_and_profession_shields_and_is_already_of_age(self):
        defs=Definitions()
        family=SimpleNamespace(defs=defs,setting=lambda name:3,
            world=SimpleNamespace(_area=lambda e:e.get('position',{}).get('areaId',1),
                                  seconds_per_year=86400,current_age=lambda p,at:21))
        rules=OriginalBabyCharmRules(family,SimpleNamespace(_choose=None))
        state={'areaId':1,'world':{'entities':[]}}
        adult=rules._award_villager(state,741,10000000)
        self.assertEqual(adult['skills'][:3],[
            {'skilltypeId':2,'skillOriginType':2},
            {'skilltypeId':3,'skillOriginType':1},
            {'skilltypeId':6,'skillOriginType':0}])
        self.assertEqual(adult['comingOfAgeSkill'],6)
        self.assertEqual(parent_shields(defs,adult,adult),[
            {'skilltypeId':6,'skillOriginType':2},{'skilltypeId':6,'skillOriginType':1}])

    def test_known_adult_hero_ranks_recover_without_touching_unproven_people_or_purchases(self):
        defs=Definitions()
        family=SimpleNamespace(defs=defs,setting=lambda name:3,
            world=SimpleNamespace(current_age=lambda p,at:p.get('startAge',0)))
        rules=OriginalBabyCharmRules(family,SimpleNamespace(_choose=None))
        hero={'id':'imported-hero','templateType':'villager_type','villagerBaseId':741,
              'rarity':5,'equipment':'invented-equipment','startAge':21,'comingOfAgeSkill':7,
              'skills':[{'skilltypeId':k,'skillOriginType':0} for k in (2,3,6)]+
                       [{'skilltypeId':7,'skillOriginType':3}]}
        unknown={**copy.deepcopy(hero),'id':'unproven','equipment':'different'}
        state={'world':{'entities':[hero,unknown]}}
        before=copy.deepcopy(unknown)
        self.assertTrue(rules.restore_adult_shields(state,100))
        self.assertEqual([sum(s['skilltypeId']==k for s in hero['skills']) for k in (2,3,6)],[3,3,3])
        self.assertIn({'skilltypeId':7,'skillOriginType':3},hero['skills'])
        self.assertEqual(hero['comingOfAgeSkill'],7)
        self.assertEqual(unknown,before)
        self.assertFalse(rules.restore_adult_shields(state,101))

    def test_recorded_parent_shields_restore_once_and_never_exceed_the_rank_limit(self):
        person={'id':'child','templateType':'villager_type',
                'skills':[{'type':6,'skillOriginType':0},{'type':7,'skillOriginType':3}]}
        unrelated={'id':'unproven','templateType':'villager_type','skills':[]}
        shields=[{'skilltypeId':6,'skillOriginType':1},{'skilltypeId':6,'skillOriginType':2}]
        state={'world':{'entities':[person,unrelated]},'pregnancies':{
            'mother':{'status':'born','bornChildren':['child'],'inheritedSkills':shields}}}
        self.assertTrue(restore_birth_shields(Definitions(),state,3))
        self.assertEqual(len(person['skills']),4)
        self.assertFalse(restore_birth_shields(Definitions(),state,3))
        self.assertEqual(unrelated['skills'],[])
        person['skills']=[{'type':6,'skillOriginType':3} for _ in range(3)]
        self.assertFalse(restore_birth_shields(Definitions(),state,3))
        self.assertEqual(len(person['skills']),3)

    def test_free_starter_masteries_recover_but_craftable_mastery_is_not_given(self):
        rules = OriginalInventoryRules(Definitions())
        state = {'inventory':{'501':0,'502':0,'601':0,'323':42}}
        rules.restore_starter_tools(state)
        self.assertEqual(state['inventory'], {'501':1,'502':0,'601':1,'323':42})
        before=copy.deepcopy(state)
        rules.restore_starter_tools(state)
        self.assertEqual(state,before)

    def test_new_village_hero_home_gets_beds_and_keeps_residents_on_later_migration(self):
        rules=OriginalHabitatRules(Definitions())
        home={'id':'hero','templateType':'shelter','templateId':34,'position':{'areaId':1}}
        state={'world':{'entities':[home]}}
        self.assertTrue(rules.migrate(state,100))
        self.assertEqual(len(home['beds']),2)
        home['beds'][0]['villagerId']='resident'
        before=copy.deepcopy(home)
        self.assertFalse(rules.migrate(state,101))
        self.assertEqual(home,before)
        other={'id':'prop','templateType':'shelter','templateId':34,'position':{'areaId':2}}
        rules.initialize(other)
        self.assertNotIn('beds',other)

    def test_second_workshop_uses_its_foundation_without_replacing_first_workshop(self):
        rules=OriginalBuildingRules(Definitions())
        old={'id':'old','templateType':'workshop','templateId':1,
             'position':{'x':100,'y':100,'areaId':1}}
        foundation={'id':'new-site','templateType':'building_task','templateId':7,
                    'position':{'x':800,'y':200,'areaId':1}}
        state={'world':{'entities':[old,foundation]},'inventory':{}}
        before=copy.deepcopy(old)
        response=rules.complete(state,{'id':'job','sourceId':'new-site'})
        first,second=state['world']['entities']
        self.assertEqual(first,before)
        self.assertNotEqual(second['id'],first['id'])
        self.assertEqual(second['position'],foundation['position'])
        self.assertEqual(response[0]['id'],second['id'])
        # An explicit upgrade still replaces its selected workshop in place.
        result=rules.complete(state,{'id':'upgrade','sourceId':'old','upgradeDefinitionId':8})
        upgraded=next(e for e in state['world']['entities'] if e['id']=='old')
        self.assertEqual(upgraded['position'],before['position'])
        self.assertEqual(upgraded['templateId'],2)
        self.assertEqual(result[0]['id'],'old')

    def test_moving_a_building_never_reads_completed_work_history(self):
        rules=OriginalBuildingRules(Definitions())
        entity={'id':'workshop','templateType':'workshop','templateId':1,
                'position':{'x':100,'y':100,'areaId':1}}
        state={'areaId':1,'world':{'entities':[entity]},'workAreas':History(None,'fixture','workAreas',{})}
        with patch.object(History,'__iter__',side_effect=AssertionError('scanned archived work')):
            rules.update_position(state,{'positionId':'workshop-position','areaId':1,'x':300,'y':400})
        self.assertEqual(entity['position']['x'],300)

    def test_feeding_index_preserves_retries_without_reloading_all_archived_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo=SqliteSaveRepository(Path(temporary)/'worlds.sqlite3')
            rules=OriginalWantRules(DailyDefinitions())
            adult={'id':'caregiver','templateType':'villager_type','templateId':1,
                   'startAge':21,'bornAt':1000,'position':{'areaId':1},'xp':0}
            normal={'areaId':1,'world':{'entities':[adult]},'user':{'userLevelID':3},
                    'inventory':{'107':5},'directConsumptionReceipts':{
                        str(i):{'villagerId':'caregiver','materialId':107,'consumedAt':0,
                                'response':{'result':{}}} for i in range(3000)}}
            village=repo.create_village(repo.create_account(),{'originalSave':{'normal':normal}})
            repo.enable_history_storage()
            repo.mutate(village,operation_key='archive',request={},change=lambda state:{})
            def initialize(payload):
                rules._consumption_index(payload['originalSave']['normal'])
                return {}
            repo.mutate(village,operation_key='index',request={},change=initialize)
            def consume(key,at):
                return repo.mutate(village,operation_key=key,request={},change=lambda payload:
                    rules.consume(payload['originalSave']['normal'],
                                  {'VillagerStringID':'caregiver','MaterialTypeID':107},at,key))[1]
            with patch.object(History,'__iter__',side_effect=AssertionError('scanned archived receipts')):
                first=consume('eat',4000)
                second=consume('new-call-same-interval',4001)
                self.assertEqual(first['Xp'],second['result']['Xp'])
                state=repo.read_village(village).payload['originalSave']['normal']
                self.assertEqual(state['inventory']['107'],4)
                self.assertEqual(len(state['latestConsumptionReceipts']),1)
            # The next due meal is consumed normally after reopening the database.
            repo=SqliteSaveRepository(repo.path)
            consume('next-meal',4601)
            self.assertEqual(repo.read_village(village).payload['originalSave']['normal']['inventory']['107'],3)


if __name__=='__main__':
    unittest.main()
