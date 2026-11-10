"""End-to-end local smoke test for NEW API and privacy-safe unsupported RPC logging.

Uses a temporary SQLite database and ephemeral localhost port; never starts
BlueStacks or imports real player data.
"""
from pathlib import Path
from contextlib import closing
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
import json


def smoke() -> None:
    with tempfile.TemporaryDirectory(prefix='vl-new-backend-test-') as folder:
        with closing(socket.socket()) as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        db = Path(folder)/'synthetic.sqlite3'
        env = dict(os.environ, VILLAGELIFE_DB=str(db))
        proc = subprocess.Popen([sys.executable,'-m','villagelife','serve','--port',str(port)],
                                env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            addr = f'http://127.0.0.1:{port}'
            for _ in range(60):
                if proc.poll() is not None:
                    raise RuntimeError('NEW backend exited before accepting requests')
                try:
                    with urllib.request.urlopen(addr+'/health',timeout=0.5) as response:
                        obj=json.loads(response.read())
                        if obj.get('ok') and obj.get('api')==1: break
                except (OSError,ValueError): time.sleep(0.12)
            else: raise RuntimeError('NEW backend failed localhost health check')
            req=urllib.request.Request(addr+'/web/ClientService/Process?private_query=DO_NOT_STORE',
                                       data=b'synthetic-body', method='POST')
            try: urllib.request.urlopen(req,timeout=3)
            except urllib.error.HTTPError as response:
                if response.code!=501:raise RuntimeError('Expected explicit unimplemented 501')
                response.close()
            else:raise RuntimeError('Unexpected legacy compatibility claim')
            from villagelife.persistence.sqlite_store import SqliteSaveRepository
            from villagelife.support import export_missing
            report=export_missing(SqliteSaveRepository(db),Path(folder)/'reported.zip')
            with zipfile.ZipFile(report) as z: payload=z.read('missing-requests.json')
            assert b'ClientService/Process' in payload
            assert b'DO_NOT_STORE' not in payload
            assert b'synthetic-body' not in payload
            print('PASS: NEW API health, legacy-protocol rejection, missing-request privacy, and fresh temporary SQLite store')
        finally:
            proc.terminate()
            try:proc.wait(timeout=4)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=4)


if __name__ == '__main__': smoke()
