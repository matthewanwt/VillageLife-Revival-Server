"""Independent village creation, listing, deletion and recovery tests.

All databases are temporary; no player save or launcher state is touched.
"""
from pathlib import Path
import tempfile
import unittest

from villagelife.core.errors import InvalidAction, NotFound, SaveBackupError
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.services import OriginalClientGame
from villagelife.protocol.original_client.villages import (
    create_local_village,
    delete_imported_village,
    delete_local_village,
    list_local_villages,
    restore_portable_village,
)
from test_original_client import fake_tables


class LocalVillageLifecycleTests(unittest.TestCase):
    def test_created_village_is_listed_and_first_login_uses_fresh_tutorial(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fake_tables(root / 'tables.sqlite3')
            repo = SqliteSaveRepository(root / 'worlds.sqlite3')
            created = create_local_village(repo)
            self.assertEqual(created['stage'], 'tutorial')
            listed = list_local_villages(repo)
            self.assertEqual([row['village_id'] for row in listed],
                             [created['village_id']])
            self.assertEqual(listed[0]['stage'], 'tutorial')
            self.assertIn(created['village_id'][:8], listed[0]['name'])

            game = OriginalClientGame(repo, OriginalDefinitions(root / 'tables.sqlite3'),
                                      selected_village=created['village_id'])
            self.assertEqual(game.login({'deviceId': 'new-village-device'})['code'], 200)
            payload = repo.read_village(created['village_id']).payload
            villagers = payload['originalSave']['userHash']['data']['villagers']
            self.assertEqual([row['refId'] for row in villagers], ['steve', 'jill'])
            # A tutorial village stays in the tutorial stage until the client
            # completes it, but it must remain selectable in the meantime.
            self.assertEqual(list_local_villages(repo)[0]['stage'], 'tutorial')

    def test_two_created_villages_keep_separate_ids_and_progress(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fake_tables(root / 'tables.sqlite3')
            repo = SqliteSaveRepository(root / 'worlds.sqlite3')
            first = create_local_village(repo)
            second = create_local_village(repo)
            self.assertNotEqual(first['village_id'], second['village_id'])
            self.assertNotEqual(first['account_id'], second['account_id'])
            self.assertEqual(len(list_local_villages(repo)), 2)

            game = OriginalClientGame(repo, OriginalDefinitions(root / 'tables.sqlite3'),
                                      selected_village=second['village_id'])
            game.login({'deviceId': 'second-village-device'})
            first_game = OriginalClientGame(repo, OriginalDefinitions(root / 'tables.sqlite3'),
                                            selected_village=first['village_id'])
            first_game.login({'deviceId': 'first-village-device'})
            repo.mutate(second['village_id'], operation_key='fixture:second-progress',
                        request={}, change=lambda payload: payload['originalSave'].update(
                            {'fixtureProgress': True}) or {})
            self.assertNotIn('fixtureProgress',
                             repo.read_village(first['village_id']).payload['originalSave'])
            self.assertTrue(repo.read_village(second['village_id']).payload[
                'originalSave']['fixtureProgress'])

    def test_delete_creates_recovery_archive_and_keeps_other_villages(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repo = SqliteSaveRepository(root / 'worlds.sqlite3')
            keep = create_local_village(repo)
            remove = create_local_village(repo)
            before = repo.read_village(remove['village_id']).payload
            repo.mutate(keep['village_id'], operation_key='fixture:keep',
                        request={}, change=lambda payload: {})
            backup = root / 'deleted.zip'
            result = delete_local_village(repo, remove['village_id'], backup=backup)
            self.assertEqual(result['village_id'], remove['village_id'])
            self.assertTrue(backup.is_file())
            self.assertEqual([row['village_id'] for row in list_local_villages(repo)],
                             [keep['village_id']])
            with repo.connect() as db:
                self.assertIsNotNone(db.execute(
                    'SELECT 1 FROM receipts WHERE village_id=?',
                    (keep['village_id'],)).fetchone())
                self.assertIsNone(db.execute(
                    'SELECT 1 FROM receipts WHERE village_id=?',
                    (remove['village_id'],)).fetchone())

            restored = restore_portable_village(repo, backup)
            self.assertNotEqual(restored['village_id'], remove['village_id'])
            self.assertEqual(repo.read_village(restored['village_id']).payload, before)

    def test_delete_is_cancelled_when_the_recovery_copy_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repo = SqliteSaveRepository(root / 'worlds.sqlite3')
            created = create_local_village(repo)
            existing = root / 'existing.zip'
            existing.write_bytes(b'keep')
            with self.assertRaises(SaveBackupError):
                delete_local_village(repo, created['village_id'], backup=existing)
            self.assertEqual([row['village_id'] for row in list_local_villages(repo)],
                             [created['village_id']])

    def test_unknown_village_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = SqliteSaveRepository(Path(folder) / 'worlds.sqlite3')
            with self.assertRaises(NotFound):
                delete_local_village(repo, 'missing-village')

    def test_imported_delete_keeps_other_copies_and_creates_a_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            storage = root / 'imported-villages'
            storage.mkdir()
            main = SqliteSaveRepository(root / 'worlds.sqlite3')
            keys = ['a' * 64, 'b' * 64]
            for key in keys:
                imported = SqliteSaveRepository(storage / (key + '.sqlite3'))
                owner = imported.create_account()
                imported.create_village(owner, {'originalSave': None})
            backup = root / 'deleted-imported.zip'
            result = delete_imported_village(main, keys[0], storage=storage,
                                             backup=backup)
            self.assertEqual(result['key'], keys[0])
            self.assertTrue(backup.is_file())
            self.assertFalse((storage / (keys[0] + '.sqlite3')).exists())
            self.assertTrue((storage / (keys[1] + '.sqlite3')).exists())

    def test_imported_delete_rejects_unknown_keys(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            repo = SqliteSaveRepository(root / 'worlds.sqlite3')
            with self.assertRaises(InvalidAction):
                delete_imported_village(repo, 'not-a-key', storage=root)
            with self.assertRaises(NotFound):
                delete_imported_village(repo, 'c' * 64, storage=root)


if __name__ == '__main__':
    unittest.main()
