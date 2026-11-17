"""Synthetic house-removal contracts; no proprietary rows or player saves."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from villagelife.protocol.original_client.shelter_removal import SERVICE,remove_shelter
from villagelife.protocol.original_client.world import OriginalWorldRules
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.services import OriginalClientGame
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from test_original_client import fake_tables


class Definitions:
    def __init__(self, base=None):self.base=base
    def item(self, table, ident):
        if table=='shelter':return {'id':str(ident),'immovable':'1' if ident in (36,41) else '0'}
        if self.base:return self.base.item(table,ident)
        raise KeyError((table,ident))
    def rows(self, table):return self.base.rows(table) if self.base else []


def fixture(template=0, occupied=False):
    home={'id':'home','templateType':'shelter','templateId':template,
          'position':{'areaId':1,'x':100,'y':100},
          'beds':[{'id':'bed','shelterSlotID':12,'villagerId':'person' if occupied else ''}]}
    person={'id':'person','templateType':'villager_type','shelterBedId':'bed' if occupied else '',
            'relationships':{'spouse':'other'},'opaque':'retain'}
    return {'areaId':1,'revision':1,'user':{'userLevelID':1,'xp':0},
            'world':{'entities':[home,person]},'inventory':{'323':77},
            'workAreas':{},'opaque':{'retain':[1,2]}}


class ShelterRemovalTests(unittest.TestCase):
    def test_empty_removal_and_replay_preserve_people_items_and_unknowns(self):
        state=fixture();before=deepcopy(state)
        self.assertEqual(remove_shelter(state,{'userShelterId':'home'},Definitions()),({},True))
        self.assertEqual(state['world']['entities'],before['world']['entities'][1:])
        for key in ('inventory','workAreas','opaque'):self.assertEqual(state[key],before[key])
        self.assertEqual(state['deletedShelters'],['home'])
        before=deepcopy(state)
        self.assertEqual(remove_shelter(state,{'userShelterId':'home'},Definitions()),({},False))
        self.assertEqual(state,before)

    def test_invalid_protected_occupied_other_area_and_active_work_do_not_mutate(self):
        cases=[fixture(19),fixture(36),fixture(41),fixture(occupied=True)]
        state=fixture();state['world']['entities'][1]['shelterBedId']='bed';cases.append(state)
        state=fixture();state['world']['entities'][0]['position']['areaId']=2;cases.append(state)
        for key in ('sourceId','targetId','subjectId'):
            state=fixture();state['workAreas']={'job':{'status':'working',key:'home'}};cases.append(state)
        state=fixture();state['workAreas']={'job':{'status':'working','sourceSnapshot':{'id':'home'}}};cases.append(state)
        for state in cases:
            with self.subTest(state=state):
                before=deepcopy(state)
                with self.assertRaises(ValueError):remove_shelter(state,{'userShelterId':'home'},Definitions())
                self.assertEqual(state,before)

    def test_authored_reconciliation_honors_the_tombstone(self):
        state=fixture();home=deepcopy(state['world']['entities'][0])
        remove_shelter(state,{'userShelterId':'home'},Definitions())
        world=OriginalWorldRules(Definitions());world.authored=lambda area:[home]
        self.assertFalse(world.reconcile_authored(state,1,100))
        self.assertFalse(any(e['id']=='home' for e in state['world']['entities']))

    def test_unrelated_null_snapshot_is_not_an_active_reference(self):
        state=fixture();state['workAreas']={'job':{'status':'working','sourceId':'other','sourceSnapshot':None}}
        jobs=deepcopy(state['workAreas'])
        remove_shelter(state,{'userShelterId':'home'},Definitions())
        self.assertEqual(state['workAreas'],jobs)

    def test_malformed_tasks_reject_without_partial_changes(self):
        for jobs in ([],{'job':None},{'job':{'sourceSnapshot':[]}},{'job':{'sourceSnapshot':'invalid'}}):
            state=fixture();state['workAreas']=jobs;before=deepcopy(state)
            with self.assertRaises(ValueError):remove_shelter(state,{'userShelterId':'home'},Definitions())
            self.assertEqual(state,before)

    def test_authenticated_batch_preflight_replay_and_sqlite_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);table=root/'tables.sqlite';fake_tables(table)
            db=root/'village.sqlite';repo=SqliteSaveRepository(db)
            game=OriginalClientGame(repo,Definitions(OriginalDefinitions(table)))
            ident,profile,_=game.sessions.login('synthetic-house-device')
            def seed(payload):payload.update(originalSave={'normal':fixture(36,True)},opaque={'keep':True});return {}
            repo.mutate(ident.village_id,operation_key='fixture',request={},change=seed)
            def request(suffix):
                return {'deviceId':'synthetic-house-device','pId':profile['pId'],'sessionId':profile['sessionId'],
                        'data':{'calls':[{'id':'empty-'+suffix,'service':'ClientUserShelterService/EmptyBed','data':{'shelterBedId':'bed'}},
                                         {'id':'delete-'+suffix,'service':SERVICE,'data':{'userShelterId':'home'}}]}}
            before=repo.read_village(ident.village_id)
            self.assertEqual([c['code'] for c in game.process(request('protected'))['data']['calls']],[400,400])
            self.assertEqual(repo.read_village(ident.village_id),before)
            def permit(payload):
                state=payload['originalSave']['normal'];state['world']['entities'][0]['templateId']=0
                state['workAreas']={'unrelated':{'status':'working','sourceId':'other','sourceSnapshot':None}}
                return {}
            repo.mutate(ident.village_id,operation_key='permit',request={},change=permit)
            def add_second_resident(payload):
                state = payload['originalSave']['normal']
                home, person = state['world']['entities']
                home['beds'].append({'id':'bed-2','shelterSlotID':13,'villagerId':'second'})
                state['world']['entities'].append({**person,'id':'second','shelterBedId':'bed-2'})
                return {}
            repo.mutate(ident.village_id,operation_key='second-resident',request={},change=add_second_resident)
            before = repo.read_village(ident.village_id)
            self.assertEqual([c['code'] for c in game.process(request('partial'))['data']['calls']],[400,400])
            self.assertEqual(repo.read_village(ident.village_id),before)
            def remove_second_resident(payload):
                state = payload['originalSave']['normal']
                state['world']['entities'][0]['beds'].pop()
                state['world']['entities'].pop()
                return {}
            repo.mutate(ident.village_id,operation_key='remove-second',request={},change=remove_second_resident)
            self.assertEqual([c['code'] for c in game.process(request('valid'))['data']['calls']],[200,200])
            saved=repo.read_village(ident.village_id)
            state=saved.payload['originalSave']['normal']
            self.assertEqual(state['inventory'],{'323':77});self.assertEqual(saved.payload['opaque'],{'keep':True})
            self.assertEqual(state['world']['entities'],[fixture()['world']['entities'][1]])
            self.assertEqual(state['deletedShelters'],['home'])
            self.assertEqual([c['code'] for c in game.process(request('valid'))['data']['calls']],[200,200])
            self.assertEqual(repo.read_village(ident.village_id),saved)
            repo.checkpoint();reopened=SqliteSaveRepository(db)
            self.assertEqual(reopened.read_village(ident.village_id),saved)
            with reopened.connect() as c:
                self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])


if __name__=='__main__':unittest.main()
