import copy
import json
import importlib.util
from pathlib import Path
import tempfile
import unittest

from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.protocol.original_client.sessions import OriginalClientSessions
from villagelife.protocol.original_client.wants import OriginalWantRules
import test_original_daily as daily_fixture


class SaveEfficiencyTests(unittest.TestCase):
    def test_compact_old_consumption_preserves_replay_and_unknown_fields(self):
        fixture = daily_fixture.DailyLifeTests()
        fixture.setUp()
        rules, state = fixture.rules, fixture.state
        want = fixture.generate('Food')[0]
        data = {'VillagerStringID': want['VillagerStringID'], 'MaterialTypeID': want['MaterialID'],
                'WantID': want['WantId']}
        rules.consume(state, data, 1000, 'first')
        record = state['consumptionReceipts'][str(want['WantId'])]
        self.assertNotIn('inventory', record['response'])
        # Reconstruct the old save shape to exercise upgrade, not only new data.
        record['response']['inventory'] = [{'old': 'inventory'}] * 100
        record['response']['result']['inventory'] = [{'old': 'inventory'}] * 100
        record['futureField'] = {'preserve': True}
        state['inventory']['6'] += 7
        expected = rules._current_receipt(state, record)
        before = copy.deepcopy(state)
        self.assertEqual(rules.compact_consumption_history(state), 2)
        self.assertEqual(rules.compact_consumption_history(state), 0)
        self.assertEqual(rules.consume(state, data, 1001, 'retry'), expected)
        self.assertEqual(state['inventory'], before['inventory'])
        self.assertEqual(record['futureField'], {'preserve': True})
        self.assertLess(len(json.dumps(state)), len(json.dumps(before)))

    def test_session_rotation_discards_only_invalidated_session_receipts(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = SqliteSaveRepository(Path(folder) / 'worlds.sqlite3')
            sessions = OriginalClientSessions(repo)
            old, _, _ = sessions.login('test-device')
            keys = ['original:' + old.session_token + ':1', 'original:migrate:test',
                    'original:another-active-session:1']
            for key in keys:
                repo.mutate(old.village_id, operation_key=key, request={}, change=lambda state: {})
            new, _, _ = sessions.login('test-device')
            self.assertNotEqual(old.session_token, new.session_token)
            with repo.connect() as db:
                remaining = {row[0] for row in db.execute('SELECT operation_key FROM receipts')}
            self.assertEqual(remaining, set(keys))
            # Even an already-authenticated, in-flight old call cannot execute
            # its mutation again after the response body has been retired.
            _, _, replay = repo.mutate(old.village_id, operation_key=keys[0], request={},
                change=lambda state: self.fail('old reward was granted twice'))
            self.assertTrue(replay)
            key = 'original:' + new.session_token + ':1'
            repo.mutate(new.village_id, operation_key=key, request={}, change=lambda state: {'ok': True})
            _, response, replay = repo.mutate(new.village_id, operation_key=key, request={},
                change=lambda state: self.fail('active retry executed twice'))
            self.assertEqual((response, replay), ({'ok': True}, True))

    def test_unchanged_action_does_not_write_payload_column(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = SqliteSaveRepository(Path(folder) / 'worlds.sqlite3')
            owner = repo.create_account()
            village = repo.create_village(owner, {'large': 'x' * 100000})
            with repo.connect() as db:
                db.execute("CREATE TRIGGER forbid_payload_write BEFORE UPDATE OF payload_json ON villages "
                           "BEGIN SELECT RAISE(ABORT, 'payload rewritten'); END")
            snapshot, response, replay = repo.mutate(village, operation_key='unchanged', request={},
                                                     change=lambda state: {'ok': True})
            self.assertEqual(snapshot.revision, 1)
            self.assertEqual((response, replay), ({'ok': True}, False))
            self.assertEqual(repo.read_village(village).payload['large'], 'x' * 100000)

    def test_selected_village_relogin_retires_previous_selected_token(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = SqliteSaveRepository(Path(folder) / 'worlds.sqlite3')
            normal = OriginalClientSessions(repo)
            owner, _, _ = normal.login('old-device')
            repo.mutate(owner.village_id, operation_key='seed', request={},
                        change=lambda state: state.update(originalSave={'normal': {'user': {}}}) or {})
            selected = OriginalClientSessions(repo, selected_village=owner.village_id)
            old, _, _ = selected.login('new-device')
            key = 'original:' + old.session_token + ':1'
            repo.mutate(old.village_id, operation_key=key, request={}, change=lambda state: {})
            selected.login('new-device')
            with self.assertRaises(PermissionError):
                selected.authenticate({'deviceId': 'new-device', 'pId': old.player_id,
                                       'sessionId': old.session_token})
            with repo.connect() as db:
                self.assertEqual(db.execute('SELECT response_json FROM receipts WHERE operation_key=?',
                                            (key,)).fetchone()[0], '{}')

    def test_audit_is_read_only_and_does_not_export_player_values(self):
        path = Path(__file__).resolve().parents[1] / 'tools/audit_save_performance.py'
        spec = importlib.util.spec_from_file_location('save_audit', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as folder:
            repo = SqliteSaveRepository(Path(folder) / 'worlds.sqlite3')
            owner = repo.create_account('private-player-name')
            repo.create_village(owner, {'originalSave': {'normal': {'inventory': {'private-material': 8}}}})
            before = repo.path.read_bytes()
            report = module.audit(repo.path)
            self.assertEqual(repo.path.read_bytes(), before)
            self.assertEqual(report['tables']['villages']['rows'], 1)
            self.assertNotIn(owner, json.dumps(report))
            self.assertNotIn('private-', json.dumps(report))
