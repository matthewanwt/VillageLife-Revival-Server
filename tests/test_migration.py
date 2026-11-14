import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.persistence.legacy_import import LegacySaveImporter
from villagelife.persistence.legacy_launcher import import_copy, preview, protect_original_instance, saved_copies
from villagelife.protocol.original_client.sessions import OriginalClientSessions
from villagelife.services.dispatcher import ActionDispatcher
from villagelife.core.errors import InvalidAction


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'legacy-private-state'
        self.source.mkdir()
        self.key = 'a' * 64
        self.profile_path = self.source / (self.key + '.json')
        self.save_path = self.source / (self.key + '.tutorial.json')
        self.profile = {'deviceId': 'fictional-device', 'pId': '1001', 'displayName': 'Sample'}
        self.save = {'version': 1, 'normal': {'world': {'entities': [{'id': 'family-member-1',
                    'unknownFieldFromOriginal': [1,2,3]}]}, 'familyTree': {'a': 'b'}},
                     'unknownFutureField': {'stillHere': True}}
        self.profile_path.write_text(json.dumps(self.profile), encoding='utf-8')
        self.save_path.write_text(json.dumps(self.save), encoding='utf-8')
        self.original_digest = hashlib.sha256(self.save_path.read_bytes()).hexdigest()
        self.repo = SqliteSaveRepository(self.root / 'new.sqlite3')

    def test_dry_run_import_and_repeat(self):
        importer = LegacySaveImporter(self.repo)
        self.assertEqual(importer.import_directory(self.source)[0].status, 'ready-to-import (dry run)')
        imported = importer.import_directory(self.source, apply=True)[0]
        self.assertEqual(imported.status, 'imported (original untouched)')
        self.assertEqual(importer.import_directory(self.source, apply=True)[0].status, 'already-imported')
        snap = self.repo.read_village(imported.village_id)
        self.assertEqual(snap.format, 'legacy.profile+tutorial.v1')
        self.assertEqual(snap.payload['originalSave'], self.save)
        self.assertEqual(snap.payload['originalProfile'], self.profile)
        self.assertEqual(hashlib.sha256(self.save_path.read_bytes()).hexdigest(), self.original_digest)
        with self.assertRaises(InvalidAction):
            ActionDispatcher.safe_default(self.repo).execute(
                imported.village_id, name='area.change', payload={'areaId': 1}, operation_key='1')

    def test_changed_input_does_not_overwrite(self):
        importer = LegacySaveImporter(self.repo)
        importer.import_directory(self.source, apply=True)
        self.save_path.write_text(json.dumps({**self.save, 'changed': True}), encoding='utf-8')
        self.assertIn('CONFLICT', importer.import_directory(self.source, apply=True)[0].status)

    def test_launcher_accepts_backup_larger_than_old_limit(self):
        key = OriginalClientSessions.device_key(self.profile['deviceId'])
        (self.source / (key + '.json')).write_text(json.dumps(self.profile), encoding='utf-8')
        save = {'version': 1, 'userHash': {'data': {'villagers': []}}}
        # The original server's formatted gameplay history can exceed 20 MiB.
        path = self.source / (key + '.tutorial.json')
        with path.open('w', encoding='utf-8') as stream:
            json.dump(save, stream)
            for _ in range(21):
                stream.write(' ' * (1024 * 1024))
        candidate, = preview(self.source)['villages']
        storage = self.root / 'imported'
        import_copy(self.source, storage, key, candidate['fingerprint'])
        repo = SqliteSaveRepository(storage / (key + '.sqlite3'))
        self.assertEqual(repo.list_all_villages()[0].payload['originalSave'], save)

    def test_launcher_copy_survives_device_change_and_keeps_current_village(self):
        old_install = self.root / '0.2.6'
        source = old_install / 'backend' / 'private_state'
        source.mkdir(parents=True)
        (old_install / 'play-settings.json').write_text('{"instance":"Pie64_2"}', encoding='utf-8')
        key = OriginalClientSessions.device_key(self.profile['deviceId'])
        profile = source / (key + '.json')
        save = source / (key + '.tutorial.json')
        profile.write_text(json.dumps(self.profile), encoding='utf-8')
        data = {'version': 1, 'userHash': {'activeSequence': 10, 'data': {'villagers': []}}}
        save.write_text(json.dumps(data), encoding='utf-8')
        storage = self.root / 'imported-villages'
        current = OriginalClientSessions(self.repo).login('new-instance')[0]

        candidate, = preview(old_install)['villages']
        self.assertEqual(candidate['source_instance'], 'Pie64_2')
        self.assertFalse(storage.exists())
        args = old_install, storage, key, candidate['fingerprint']
        import_copy(*args)
        self.assertEqual(import_copy(*args)['status'], 'already-imported')
        self.assertEqual(saved_copies(storage), [candidate])
        with self.assertRaisesRegex(ValueError, 'original 0.2.6 instance'):
            protect_original_instance(storage, 'Pie64_2')

        copied = SqliteSaveRepository(storage / (key + '.sqlite3'))
        identity, _, payload = OriginalClientSessions(copied).login('new-instance')
        self.assertEqual(identity.player_id, '1001')
        self.assertNotEqual(identity.village_id, current.village_id)
        self.assertEqual(payload['originalSave'], data)
        self.assertEqual(OriginalClientSessions(self.repo).login('new-instance')[0].village_id,
                         current.village_id)
        self.assertEqual(OriginalClientSessions(copied).login('new-instance')[0].village_id,
                         identity.village_id)
        with self.assertRaises(InvalidAction):
            OriginalClientSessions(copied).login('another-instance')
        self.assertEqual(json.loads(save.read_bytes()), data)
        self.assertEqual(json.loads(profile.read_bytes()), self.profile)

        save.write_text(json.dumps({**data, 'changed': True}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'changed after preview'):
            import_copy(*args)
        updated, = preview(source)['villages']
        with self.assertRaisesRegex(ValueError, 'imported before'):
            import_copy(source, storage, key, updated['fingerprint'])
        self.assertEqual(copied.read_village(identity.village_id).payload['originalSave'], data)


if __name__ == '__main__':
    unittest.main()
