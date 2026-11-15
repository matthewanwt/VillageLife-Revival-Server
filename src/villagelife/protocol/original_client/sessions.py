"""Original-client identities on NEW transactional SQLite villages.

Device IDs are never stored in this mapping: SHA-256 identifiers are used only
as local lookup keys. No legacy server or filesystem save modules are loaded.
Imported 2.11 saves remain byte-for-byte untouched at their source location.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import hashlib
from datetime import datetime
import json
import secrets
from threading import Lock
import time
import uuid

from villagelife.persistence.sqlite_store import SqliteSaveRepository, dumps
from villagelife.core.errors import InvalidAction

SESSION_SCHEMA='''
CREATE TABLE IF NOT EXISTS original_client_devices (
 device_hash TEXT PRIMARY KEY,
 account_id TEXT NOT NULL REFERENCES accounts(account_id),
 village_id TEXT NOT NULL REFERENCES villages(village_id),
 numeric_player_id TEXT NOT NULL UNIQUE,
 session_token TEXT NOT NULL,
 updated_at INTEGER NOT NULL
);
'''

@dataclass(frozen=True)
class ClientIdentity:
    account_id: str
    village_id: str
    player_id: str
    session_token: str

class OriginalClientSessions:
    def __init__(self, repo: SqliteSaveRepository, *, selected_village: str | None = None):
        self.repo=repo
        self.selected_owner = None
        self.selected_session: tuple[str, ClientIdentity] | None = None
        self.selection_lock = Lock()
        with repo.connect() as db:
            db.executescript(SESSION_SCHEMA)
            if selected_village is not None:
                self.selected_owner = db.execute('''
                    SELECT d.account_id, d.village_id, d.numeric_player_id
                    FROM original_client_devices d JOIN villages v USING (village_id)
                    WHERE d.village_id=? AND json_type(v.payload_json, '$.originalSave.normal')='object'
                    ORDER BY d.updated_at DESC LIMIT 1
                    ''', (selected_village,)).fetchone()
                if self.selected_owner is None:
                    raise ValueError('The selected village is missing. Choose a village again.')

    @staticmethod
    def device_key(device: str) -> str:
        if not isinstance(device,str) or not device or len(device)>512:
            raise InvalidAction('Original client deviceId required (max 512 characters)')
        return hashlib.sha256(device.encode('utf-8')).hexdigest()

    @staticmethod
    def _epoch(value:Any)->int:
        if value in (None,''):return 0
        if type(value) is int:return value
        if isinstance(value,str):
            if value.isdecimal():return int(value)
            try:return int(datetime.fromisoformat(value.replace('Z','+00:00')).timestamp())
            except ValueError:pass
        raise InvalidAction('Invalid original-client timestamp in imported profile')

    @staticmethod
    def profile(identity: ClientIdentity, device: str, initial: dict | None = None,
                has_world: bool = False) -> dict[str,Any]:
        base = dict(initial or {})
        base.update({'pId':identity.player_id, 'deviceId':device,
                     'sessionId':identity.session_token, 'fbId':base.get('fbId',''),
                     'zId':base.get('zId',''), 'fbHashId':base.get('fbHashId',''),
                     'scenarioId':2 if has_world else base.get('scenarioId',1),
                     'userLevelId':base.get('userLevelId',0),
                     'fbDeviceConnectedAt':OriginalClientSessions._epoch(base.get('fbDeviceConnectedAt')), 
                     'createdAt':OriginalClientSessions._epoch(base.get('createdAt')) or int(time.time()),
                     'isNewUser':not has_world})
        return base

    def login(self, device: str) -> tuple[ClientIdentity,dict,dict]:
        key=self.device_key(device)
        if self.selected_owner is not None:
            row = self.selected_owner
            with self.selection_lock:
                if self.selected_session is not None and self.selected_session[0] != key:
                    raise PermissionError('The explicitly selected village is open in another game instance')
                ident = ClientIdentity(row['account_id'], row['village_id'], row['numeric_player_id'],
                                       secrets.token_hex(16))
                self.selected_session = (key, ident)
            stored = self.repo.read_village(ident.village_id).payload
            return ident, self.saved_profile(ident, device, stored), stored
        now=int(time.time())
        # Entire identity creation is transactional. No overwrite of imported saves.
        with self.repo.transaction() as db:
            row=db.execute('SELECT * FROM original_client_devices WHERE device_hash=?',(key,)).fetchone()
            if row:
                # Rotate the session on each fresh client login. Original RPC call IDs
                # can restart at 1 after a game restart; persisting the previous
                # session token would wrongly turn new actions into replay conflicts.
                token=secrets.token_hex(16)
                db.execute('UPDATE original_client_devices SET session_token=?, updated_at=? WHERE device_hash=?',
                           (token,now,key))
                ident=ClientIdentity(row['account_id'],row['village_id'],row['numeric_player_id'],token)
            else:
                slot = db.execute("SELECT value FROM metadata WHERE key='legacy_launch_copy'").fetchone()
                if slot is not None:
                    if db.execute('SELECT 1 FROM original_client_devices LIMIT 1').fetchone():
                        raise InvalidAction('Open this imported village with the BlueStacks instance that first loaded it.')
                    legacy_key = json.loads(slot['value'])['key']
                else:
                    legacy_key = key
                imported=db.execute('SELECT * FROM legacy_imports WHERE legacy_key=?',(legacy_key,)).fetchone()
                if slot is not None and imported is None:
                    raise InvalidAction('The selected imported village is unavailable.')
                if imported:
                    account_id=imported['account_id'];village_id=imported['village_id']
                    stored=json.loads(db.execute('SELECT payload_json FROM villages WHERE village_id=?',(village_id,)).fetchone()[0])
                    old_profile=stored.get('originalProfile') or {}
                    requested=str(old_profile.get('pId',''))
                    if not requested.isdecimal():
                        raise InvalidAction('Imported original player ID is not numeric; manual migration required')
                    player_id=requested
                else:
                    account_id=str(uuid.uuid4());village_id=str(uuid.uuid4())
                    player_id=str(secrets.randbelow(2**48-1)+1)
                    db.execute('INSERT INTO accounts VALUES (?,?,?)',(account_id,now,''))
                    payload={'originalProfile':{}, 'originalSave':None,
                             'sourceFormat':'original.client.v1'}
                    db.execute('INSERT INTO villages VALUES (?,?,?,?,?,?,?,?)',
                               (village_id,account_id,'original.client.v1',1,0,dumps(payload),now,now))
                token=secrets.token_hex(16)
                try:
                    db.execute('INSERT INTO original_client_devices VALUES (?,?,?,?,?,?)',
                               (key,account_id,village_id,player_id,token,now))
                except Exception as exc:
                    if 'UNIQUE constraint failed' in str(exc):
                        raise InvalidAction('Original player ID already bound to another device') from exc
                    raise
                ident=ClientIdentity(account_id,village_id,player_id,token)
            stored=json.loads(db.execute('SELECT payload_json FROM villages WHERE village_id=?',(ident.village_id,)).fetchone()[0])
        return ident, self.saved_profile(ident, device, stored), stored

    def saved_profile(self, ident, device, stored):
        normal = (stored.get('originalSave') or {}).get('normal')
        profile = self.profile(ident, device, stored.get('originalProfile'), bool(normal))
        if normal:
            profile['userLevelId']=normal.get('user',{}).get('userLevelID',profile['userLevelId'])
            profile['scenarioId']=normal.get('user',{}).get('scenarioId',normal.get('scenarioId',2))
        return profile

    def authenticate(self, request: dict) -> ClientIdentity:
        key=self.device_key(request.get('deviceId'))
        if self.selected_owner is not None:
            with self.selection_lock:
                selected = self.selected_session
            if selected is not None:
                device, ident = selected
                if (key == device and secrets.compare_digest(str(request.get('sessionId', '')), ident.session_token)
                        and str(request.get('pId')) == ident.player_id):
                    return ident
            raise PermissionError('Original-client session mismatch')
        with self.repo.connect() as db:
            row=db.execute('SELECT * FROM original_client_devices WHERE device_hash=?',(key,)).fetchone()
        if (not row or not secrets.compare_digest(str(row['session_token']),str(request.get('sessionId','')))
                or str(row['numeric_player_id'])!=str(request.get('pId',''))):
            raise PermissionError('Original-client session mismatch')
        return ClientIdentity(row['account_id'],row['village_id'],row['numeric_player_id'],row['session_token'])
