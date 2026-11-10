"""Private, disposable original-client HTTP smoke test for extracted original definitions.

Runs only on 127.0.0.1 using a throwaway SQLite database. No BlueStacks,
APK launch, firewall changes, or real-save changes. Never prints player IDs,
request bodies, or local private paths. Does NOT prove playable client parity.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import urllib.request
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.persistence.legacy_import import LegacySaveImporter
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.services import OriginalClientGame
from villagelife.protocol.legacy_codec import encode, decode
from villagelife.transport.http_api import ApiServer


def check(tables:Path, legacy:Path|None=None)->None:
    with tempfile.TemporaryDirectory(prefix='vl-original-client-smoke-') as folder:
        repo=SqliteSaveRepository(Path(folder)/'new.sqlite3')
        if legacy is not None:
            if not legacy.is_dir():raise ValueError('Save migration source must be a directory')
            originals={p.name: hashlib.sha256(p.read_bytes()).digest()
                       for p in legacy.glob('*.json') if p.is_file() and p.stat().st_size<20_000_000}
            LegacySaveImporter(repo).import_directory(legacy, apply=True)
            if originals != {p.name: hashlib.sha256(p.read_bytes()).digest()
                       for p in legacy.glob('*.json') if p.is_file() and p.stat().st_size<20_000_000}:
                raise AssertionError('Unexpected legacy save source modification')
        game=OriginalClientGame(repo, OriginalDefinitions(tables))
        http=ApiServer(('127.0.0.1',0),repo,game)
        thread=threading.Thread(target=http.serve_forever,daemon=True)
        thread.start()
        def post(endpoint,record):
            req=urllib.request.Request('http://127.0.0.1:'+str(http.server_port)+endpoint,
                   data=encode(record,compressed=True),method='POST')
            with urllib.request.urlopen(req,timeout=15) as res:
                if res.status!=200:raise AssertionError('Original HTTP status not 200')
                return decode(res.read())[0]
        def rpc(profile,service,data=None,request_id='1'):
            record={k:profile[k] for k in ('deviceId','sessionId','pId')}
            record['data']={'calls':[{'id':request_id,'service':service,'data':data or {}}]}
            answer=post('/web/ClientService/Process',record)['data']['calls'][0]
            if answer['code']!=200:
                raise AssertionError('Original client RPC not implemented in smoke path: '+service+': '+str(answer['code']))
            return answer['data']
        try:
            a=post('/web/ClientService/Login',{'deviceId':'smoke-a'})['data']['users'][0]
            b=post('/web/ClientService/Login',{'deviceId':'smoke-b'})['data']['users'][0]
            assert a['pId']!=b['pId'],'New player IDs collide'
            rpc(a,'ClientUserHashService/GetUserHash',request_id='1')
            rpc(a,'ClientUserHashService/SetActiveSequence',{'activeSequence':217},request_id='2')
            rpc(a,'ClientUserService/ProgressArea',request_id='3')
            start=rpc(a,'ClientStartupService/GetStartupInfo',request_id='4')
            area=rpc(a,'ClientStartupService/GetAreaContent',{'areaId':1},request_id='5')
            assert isinstance(start.get('world'),dict) and isinstance(area.get('areaJson'),dict)
            assert rpc(b,'ClientUserHashService/GetUserHash',request_id='1')['userHash']['activeSequence']==0
            a2=post('/web/ClientService/Login',{'deviceId':'smoke-a'})['data']['users'][0]
            assert a2['pId']==a['pId'] and a2['sessionId']!=a['sessionId']
            rpc(a2,'ClientStartupService/GetStartupInfo',request_id='4')
            print('PASS: original wire login, tutorial bridge, startup, area-1, separate players and restart')
            print('LIMIT: original APK rendering, all gameplay RPCs, Wi-Fi isolation and installer NOT verified')
        finally:
            http.shutdown();http.server_close();thread.join(timeout=5)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-tables',type=Path,required=True)
    parser.add_argument('--legacy-saves',type=Path,help='Optional original save directory: original files remain unchanged')
    args=parser.parse_args()
    check(args.game_tables,args.legacy_saves)

if __name__=='__main__':main()
