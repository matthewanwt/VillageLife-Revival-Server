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
            'seq_state_tablet_ftue':[{'id':'0','sequenceType':'62','dataJSON':json.dumps({'refId':'steve'}),'persist':'217'},
                                     {'id':'217','sequenceType':'62','dataJSON':json.dumps({'refId':'jill'}),'persist':'410'}],
            'villager_starting_variation':[{'id':'0','refId':'steve','name':'Example','villagerType':'1','startAge':'21'},
                                          {'id':'4','refId':'jill','name':'Other','villagerType':'1','startAge':'21'}],
        }
        for i,(name, rows) in enumerate(tables.items(),1):
            con.execute('INSERT INTO game_tables VALUES (?,?,?,?,?)',(i,0,name,len(rows),len(rows)))
            con.executemany('INSERT INTO game_rows VALUES (?,?,?,?)',
                            [(i,j,row['id'],json.dumps(row)) for j,row in enumerate(rows)])
        con.commit()


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
        self.assertEqual(self.call(a,'ClientTaskService/StartBuildingTask',{'amount':999999})['code'],501)
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
