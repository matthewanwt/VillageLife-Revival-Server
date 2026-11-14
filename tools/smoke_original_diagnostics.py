"""Run a guarded synthetic RPC macro against a disposable original-client save.

This is a protocol/dispatch regression check, not a real-game acceptance test.
It uses no BlueStacks, APK, network socket, private tables, or existing save.
All generated files live inside one uniquely named temporary directory.
"""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import zipfile

from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.protocol.legacy_codec import decode, encode
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.services import OriginalClientGame
from villagelife.support import export_missing


def _write_fixture(path: Path) -> None:
    """Create only the authored rows needed for this isolated macro."""
    tables = {
        'seq_state_tablet_ftue': [
            {'id': '0', 'order': '1', 'sequenceType': '62',
             'dataJSON': json.dumps({'refId': 'steve'}), 'persist': '217'},
            {'id': '217', 'order': '2', 'sequenceType': '62',
             'dataJSON': json.dumps({'refId': 'jill'}), 'persist': '410'},
        ],
        'villager_starting_variation': [
            {'id': '1', 'refId': 'steve', 'name': 'Fixture Steve',
             'villagerType': '1', 'startAge': '21'},
            {'id': '2', 'refId': 'jill', 'name': 'Fixture Jill',
             'villagerType': '1', 'startAge': '21'},
        ],
        'bundle': [{'id': '1'}, {'id': '2'}],
        'global': [{'id': '1', 'label': 'hours_per_year', 'value': '8760'}],
        'relation_type': [],
    }
    with closing(sqlite3.connect(path)) as db:
        db.executescript(
            'CREATE TABLE game_tables(id INTEGER PRIMARY KEY,source_id INTEGER,name TEXT,'
            'declared_rows INTEGER,actual_rows INTEGER);'
            'CREATE TABLE game_rows(table_id INTEGER,ordinal INTEGER,row_id TEXT,fields_json TEXT);'
        )
        for table_id, (name, rows) in enumerate(tables.items(), 1):
            db.execute('INSERT INTO game_tables VALUES (?,?,?,?,?)',
                       (table_id, 0, name, len(rows), len(rows)))
            db.executemany('INSERT INTO game_rows VALUES (?,?,?,?)', [
                (table_id, ordinal, str(row.get('id', ordinal)), json.dumps(row))
                for ordinal, row in enumerate(rows)
            ])
        db.commit()


def _round_trip(value: dict) -> dict:
    """Exercise the actual compressed/XOR framing without opening a socket."""
    request, mode = decode(encode(value, compressed=True))
    if mode != 'zlib-xor':
        raise AssertionError('Synthetic macro did not use compressed/XOR framing')
    return request


def run() -> None:
    with tempfile.TemporaryDirectory(prefix='vl-rpc-macro-') as temp:
        root = Path(temp).resolve()
        if not root.is_dir() or 'vl-rpc-macro-' not in root.name:
            raise RuntimeError('Refusing to run outside the dedicated temporary workspace')
        database = root / 'synthetic-tables.sqlite3'
        save_path = root / 'synthetic-save.sqlite3'
        _write_fixture(database)

        repo = SqliteSaveRepository(save_path)
        game = OriginalClientGame(repo, OriginalDefinitions(database))

        def login(device: str) -> dict:
            request = _round_trip({'deviceId': device})
            answer = game.login(request)
            return decode(encode(answer, compressed=True))[0]['data']['users'][0]

        def rpc(profile: dict, service: str, data: dict | None, call_id: str) -> dict:
            request = {key: profile[key] for key in ('deviceId', 'sessionId', 'pId')}
            request['data'] = {'calls': [{'id': call_id, 'service': service,
                                          'data': data or {}}]}
            answer = game.process(_round_trip(request))
            return decode(encode(answer, compressed=True))[0]['data']['calls'][0]

        owner = login('synthetic-device-owner')
        other = login('synthetic-device-other')
        if owner['pId'] == other['pId']:
            raise AssertionError('Synthetic accounts unexpectedly share an identity')

        # Seed a normal village only in this macro's fresh disposable database.
        owner_village = game.sessions.authenticate(owner).village_id
        def seed(payload: dict) -> dict:
            payload['originalSave']['normal'] = {
                'areaId': 1, 'scenarioId': 2, 'revision': 0,
                'user': {'userLevelID': 1, 'userLevel': 1, 'xp': 0,
                         'populationCap': 2, 'maxAreaId': 1},
                'inventory': {}, 'world': {'entities': []}, 'bundles': [],
            }
            return {'seeded': True}
        repo.mutate(owner_village, operation_key='macro:seed',
                    request={'fixture': 'synthetic-normal-village'}, change=seed)

        # Verify the previously broken bundle handler, idempotent replay, and
        # rejection of the same RPC ID with changed input.
        created = rpc(owner, 'ClientUserBundleService/CreateUserBundle',
                      {'bundleId': 1}, 'macro-bundle-1')
        replay = rpc(owner, 'ClientUserBundleService/CreateUserBundle',
                     {'bundleId': 1}, 'macro-bundle-1')
        conflict = rpc(owner, 'ClientUserBundleService/CreateUserBundle',
                       {'bundleId': 2}, 'macro-bundle-1')
        listed = rpc(owner, 'ClientUserBundleService/GetUserBundles', {}, 'macro-read-1')
        if created['code'] != 200 or replay['code'] != 200 or conflict['code'] != 409:
            raise AssertionError('Bundle mutation/replay contract failed')
        if len(listed['data'].get('userBundles', [])) != 1:
            raise AssertionError('Bundle replay created duplicate state')

        # Reproduce the other capture's routed-but-sensitive paths. Completion
        # and empty local relations should work for a seeded normal village;
        # malformed task data should validate as 400, and unknown work stays 501.
        complete = rpc(owner, 'ClientUser/CompleteTutorial', {}, 'macro-ftue-1')
        relations = rpc(owner, 'ClientVillagerService/GetVillagerRelations', {}, 'macro-rel-1')
        invalid_task = rpc(owner, 'ClientTaskService/StartBuildingTask', {}, 'macro-task-1')
        unknown = rpc(owner, 'ClientFriendService/GetFriends', {}, 'macro-unknown-1')
        if complete['code'] != 200 or relations['code'] != 200:
            raise AssertionError('Routed tutorial/relation handler failed')
        if invalid_task['code'] != 400 or unknown['code'] != 501:
            raise AssertionError('Validation/unsupported diagnostic statuses changed')

        # Verify no data crossed between the two synthetic accounts.
        other_hash = rpc(other, 'ClientUserHashService/GetUserHash', {}, 'macro-user-1')
        if other_hash['code'] != 200 or other_hash['data']['userHash']['activeSequence'] != 0:
            raise AssertionError('Synthetic account state leaked across identities')

        report_path = export_missing(repo, root / 'diagnostics.zip')
        with zipfile.ZipFile(report_path) as archive:
            diagnostic = archive.read('missing-requests.json').decode('utf-8')
        report = json.loads(diagnostic)
        serialized = json.dumps(report)
        for secret in ('synthetic-device-owner', 'synthetic-device-other',
                       'macro-bundle-1', 'Fixture Steve', 'Fixture Jill'):
            if secret in serialized:
                raise AssertionError('Diagnostic export leaked synthetic private values')
        codes = {row['response_code'] for row in report['call_outcomes']}
        if not {200, 400, 409, 501}.issubset(codes):
            raise AssertionError('Diagnostic export did not capture each exercised outcome')
        if not any(row['endpoint_shape'] == 'ClientFriendService/GetFriends'
                   and row['response_status'] == 501 for row in report['records']):
            raise AssertionError('Unsupported RPC was not captured in missing-request report')

        print('PASS: isolated synthetic save; compressed/XOR framing; account isolation;')
        print('      bundle mutation/replay/conflict; tutorial and relation routes;')
        print('      validation/501 reporting; privacy-safe diagnostic export.')
        print('LIMIT: synthetic definitions only; no original APK, BlueStacks, or live game rules exercised.')


if __name__ == '__main__':
    run()
