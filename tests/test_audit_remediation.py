"""Large-history, batching and local transport regressions using invented data."""
from pathlib import Path
import copy
import http.client
import json
import tempfile
import threading
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from contextlib import closing
import unittest
from unittest.mock import patch

from test_original_client import fake_tables
from villagelife.persistence.sqlite_store import SqliteSaveRepository, dumps
from villagelife.persistence.history import History, active_work, pack_record, unpack_record
from villagelife.persistence.portable import PortableSaves
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.services import OriginalClientGame
from villagelife.support import begin_diagnostic_run, export_missing
from villagelife.transport.http_api import ApiServer


class AuditRemediationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = SqliteSaveRepository(self.root / 'worlds.sqlite3')
        self.owner = self.repo.create_account()

    def test_cold_history_migrates_losslessly_and_replay_updates_only_one_record(self):
        normal = {'inventory': {'323': 25}, 'world': {'entities': []},
            'workAreas': {str(i): {'status': 'harvested', 'opaque': 'x' * 1000,
                                 'harvestResponse': {'amount': i}} for i in range(2000)}}
        normal['workAreas']['active'] = {'status': 'working', 'completionTime': 42}
        original = {'originalSave': {'normal': normal}, 'unknown': {'preserve': [1, 2]}}
        village = self.repo.create_village(self.owner, original)
        self.repo.enable_history_storage()
        backups = list((self.root / 'backups').glob('*.sqlite3'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(SqliteSaveRepository(backups[0]).read_village(village).payload, original)
        with self.repo.connect() as db:
            self.assertEqual(db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0], '2')
        with closing(sqlite3.connect(backups[0])) as old:
            self.assertEqual(old.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0], '1')
        self.repo.mutate(village, operation_key='migrate', request={}, change=lambda state: {})
        with self.repo.connect() as db:
            self.assertLess(len(db.execute('SELECT payload_json FROM villages').fetchone()[0]), 1000)
            self.assertEqual(db.execute('SELECT count(*) FROM action_history').fetchone()[0], 2000)
        payload = self.repo.read_village(village).payload
        history = payload['originalSave']['normal']['workAreas']
        self.assertIsInstance(history, History)
        self.assertEqual(history.loaded, {})
        self.assertEqual(list(active_work(payload['originalSave']['normal'])), [normal['workAreas']['active']])
        self.assertEqual(history.loaded, {})
        self.assertEqual(json.loads(dumps(payload)), original)
        def update(state):
            state['originalSave']['normal']['workAreas']['5']['opaque'] = 'changed'
            return {'ok': True}
        self.repo.mutate(village, operation_key='change-one', request={}, change=update)
        expected = copy.deepcopy(original)
        expected['originalSave']['normal']['workAreas']['5']['opaque'] = 'changed'
        self.assertEqual(json.loads(dumps(self.repo.read_village(village).payload)), expected)
        _, _, replayed = self.repo.mutate(village, operation_key='change-one', request={},
                                         change=lambda state: self.fail('duplicate reward'))
        self.assertTrue(replayed)
        archive = self.root / 'export.zip'
        PortableSaves(self.repo).export(village, archive)
        copied = PortableSaves(self.repo).import_as_new(archive, self.owner)
        self.assertEqual(json.loads(dumps(self.repo.read_village(copied).payload)), expected)

    def test_history_failure_rolls_back_world_and_archive_together(self):
        village = self.repo.create_village(self.owner, {'originalSave': {'normal': {
            'completedQuests': {'one': {'reward': 1}}, 'inventory': {'323': 10}}}})
        self.repo.enable_history_storage()
        self.repo.mutate(village, operation_key='migrate', request={}, change=lambda state: {})
        before = dumps(self.repo.read_village(village).payload)
        def broken(state):
            state['originalSave']['normal']['completedQuests']['one']['reward'] = 99
            state['originalSave']['normal']['inventory']['323'] = 0
            raise ValueError('interrupted')
        with self.assertRaises(ValueError):
            self.repo.mutate(village, operation_key='failure', request={}, change=broken)
        self.assertEqual(dumps(self.repo.read_village(village).payload), before)

    def test_read_batch_uses_one_payload_read_and_one_diagnostic_commit(self):
        fake_tables(self.root / 'tables.sqlite3')
        game = OriginalClientGame(self.repo, OriginalDefinitions(self.root / 'tables.sqlite3'))
        profile = game.login({'deviceId': 'batch-fixture'})['data']['users'][0]
        begin_diagnostic_run(self.repo)
        request = {key: profile[key] for key in ('deviceId', 'sessionId', 'pId')}
        request['data'] = {'calls': [{'id': str(i), 'service': 'ClientSettingService/GetUserGameSettings',
                                    'data': {}} for i in range(50)]}
        with patch.object(self.repo, 'read_village', wraps=self.repo.read_village) as reads, \
                patch.object(self.repo, 'transaction', wraps=self.repo.transaction) as writes:
            reply = game.process(request)
        self.assertTrue(all(row['code'] == 200 for row in reply['data']['calls']))
        self.assertEqual(reads.call_count, 1)
        self.assertEqual(writes.call_count, 1)
        with self.repo.connect() as db:
            self.assertEqual(db.execute('SELECT sum(count) FROM diagnostic_run_outcomes').fetchone()[0], 50)
            self.assertGreater(db.execute('SELECT count(*) FROM request_timings').fetchone()[0], 0)
        export_missing(self.repo, self.root / 'diagnostics.zip')

    def test_transport_rejects_origin_missing_capability_and_bad_compression(self):
        fake_tables(self.root / 'tables.sqlite3')
        game = OriginalClientGame(self.repo, OriginalDefinitions(self.root / 'tables.sqlite3'))
        server = ApiServer(('127.0.0.1', 0), self.repo, game, transport_key='fixture-key1')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            def post(path, data, headers=None):
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    connection.request('POST', path, data, headers or {})
                    response = connection.getresponse(); response.read()
                    return response.status
                finally:
                    connection.close()
            raw = b'{"deviceId":"security-fixture"}'
            self.assertEqual(post('/web/ClientService/Login', raw), 403)
            self.assertEqual(post('/fixture-key1/web/ClientService/Login', raw, {'Origin': 'https://evil.example'}), 403)
            self.assertEqual(post('/fixture-key1/web/ClientService/Login', raw), 200)
            self.assertEqual(post('/fixture-key1/web/ClientService/Process', b'not-zlib'), 400)
            self.assertEqual(post('/health-bypass', raw), 403)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)

    def test_definition_caches_do_not_share_mutable_results(self):
        fake_tables(self.root / 'tables.sqlite3')
        defs = OriginalDefinitions(self.root / 'tables.sqlite3')
        row = defs.item('material_type', '130')
        row['id'] = 'changed'
        self.assertEqual(defs.item('material_type', '130')['id'], '130')
        rows = defs.rows('material_type'); rows[0]['id'] = 'changed'
        self.assertNotEqual(defs.rows('material_type')[0]['id'], 'changed')

    def test_disk_full_rolls_back_acknowledged_world(self):
        village = self.repo.create_village(self.owner, {'gems': 17})
        with self.repo.request_scope():
            with self.repo.connect() as db:
                pages = db.execute('PRAGMA page_count').fetchone()[0]
                db.execute('PRAGMA max_page_count=' + str(pages))
            with self.assertRaises(sqlite3.DatabaseError):
                self.repo.mutate(village, operation_key='too-large', request={},
                    change=lambda state: state.update(gems=0, enormous='x' * 2_000_000) or {})
            self.assertEqual(self.repo.read_village(village).payload, {'gems': 17})

    def test_migration_backup_failure_leaves_old_layout_playable(self):
        village = self.repo.create_village(self.owner, {'gems': 17})
        with patch.object(self.repo, 'backup_to', side_effect=PermissionError('backup unavailable')):
            with self.assertRaises(PermissionError):
                self.repo.enable_history_storage()
        self.assertFalse(self.repo.history_enabled)
        self.assertEqual(self.repo.read_village(village).payload, {'gems': 17})

    def test_interrupted_history_and_world_write_roll_back_together(self):
        village = self.repo.create_village(self.owner, {'originalSave': {'normal': {
            'completedQuests': {'one': {'reward': 1}}, 'inventory': {'323': 10}}}})
        self.repo.enable_history_storage()
        self.repo.mutate(village, operation_key='archive', request={}, change=lambda state: {})
        before = dumps(self.repo.read_village(village).payload)
        child = subprocess.Popen([sys.executable, '-c', '''
import sqlite3,sys,time
db=sqlite3.connect(sys.argv[1],isolation_level=None)
db.execute('BEGIN IMMEDIATE')
db.execute('UPDATE action_history SET payload_json=?', ('{"reward":99}',))
db.execute('UPDATE villages SET payload_json=?', ('{"erased":true}',))
print('interrupted',flush=True)
time.sleep(30)
''', str(self.repo.path)], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'interrupted')
        finally:
            child.kill(); child.wait(timeout=5); child.stdout.close()
        reopened = SqliteSaveRepository(self.repo.path)
        self.assertEqual(dumps(reopened.read_village(village).payload), before)

    def test_due_index_avoids_full_scan_and_batches_transitions(self):
        from villagelife.services.jobs import WorldTickCoordinator
        village = self.repo.create_village(self.owner, {'jobs': {
            str(i): {'status': 'working', 'dueAt': 1} for i in range(20)}})
        coordinator = WorldTickCoordinator(self.repo, SimpleNamespace(now=lambda: 10))
        with patch.object(self.repo, 'list_all_villages', side_effect=AssertionError('full scan')), \
                patch.object(self.repo, 'mutate', wraps=self.repo.mutate) as writes:
            result = coordinator.advance_all()
        self.assertEqual(len(result[village]), 20)
        self.assertEqual(writes.call_count, 1)
        self.assertEqual(coordinator.advance_all(), {})

    def test_archive_compression_is_lossless_and_rejects_damaged_data(self):
        raw = dumps({'inventory': ['unchanged'] * 2000})
        packed = pack_record(raw)
        self.assertIsInstance(packed, bytes)
        self.assertLess(len(packed), len(raw) // 10)
        self.assertEqual(unpack_record(packed), raw)
        with self.assertRaises(ValueError):
            unpack_record(packed[:-3])
