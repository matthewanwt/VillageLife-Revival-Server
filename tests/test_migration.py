import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.persistence.legacy_import import LegacySaveImporter
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
        self.assertEqual(snap.format, 'legacy.v0_2_6')
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


if __name__ == '__main__':
    unittest.main()
