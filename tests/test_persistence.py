"""No user data: all records in these tests are invented fixtures."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from villagelife.cli import run
from villagelife.core.errors import (DuplicateActionConflict, RevisionConflict,
                                     InvalidAction, SaveSchemaError)
from villagelife.core.model import empty_native_village
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.persistence.portable import PortableSaves


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = SqliteSaveRepository(self.root / 'state.sqlite3')
        self.account = self.repo.create_account('test-only')
        self.village = self.repo.create_village(self.account, empty_native_village())

    def test_transaction_revision_and_replay(self):
        def add(state):
            state['inventory']['example'] = state['inventory'].get('example', 0) + 1
            return {'added': 1}
        _, r1, replay = self.repo.mutate(self.village, operation_key='abc', request={'x':1}, change=add,
                                         expected_revision=0)
        self.assertEqual((r1, replay), ({'added':1}, False))
        _, r2, replay = self.repo.mutate(self.village, operation_key='abc', request={'x':1}, change=add,
                                         expected_revision=0)
        self.assertEqual((r2, replay), ({'added':1}, True))
        self.assertEqual(self.repo.read_village(self.village).payload['inventory']['example'], 1)
        with self.assertRaises(DuplicateActionConflict):
            self.repo.mutate(self.village, operation_key='abc', request={'x':2}, change=add)
        with self.assertRaises(RevisionConflict):
            self.repo.mutate(self.village, operation_key='def', request={}, change=add,
                             expected_revision=0)
        self.assertEqual(self.repo.read_village(self.village).revision, 1)

    def test_failed_mutation_rolls_back(self):
        def broken(state):
            state['inventory']['example'] = 88
            raise InvalidAction('not allowed')
        with self.assertRaises(InvalidAction):
            self.repo.mutate(self.village, operation_key='bad', request={}, change=broken)
        self.assertEqual(self.repo.read_village(self.village).revision, 0)
        self.assertEqual(self.repo.read_village(self.village).payload['inventory'], {})

    def test_portable_roundtrip_and_checksum(self):
        archive = self.root / 'export.vl-save.zip'
        PortableSaves(self.repo).export(self.village, archive)
        other = self.repo.create_account('other')
        new_village = PortableSaves(self.repo).import_as_new(archive, other)
        snap = self.repo.read_village(new_village)
        self.assertEqual(snap.account_id, other)
        self.assertEqual(snap.payload, empty_native_village())
        self.assertNotEqual(new_village, self.village)

    def test_backup_is_consistent(self):
        dest = self.root / 'backup.sqlite3'
        self.repo.backup_to(dest)
        copy = SqliteSaveRepository(dest)
        self.assertEqual(copy.read_village(self.village).account_id, self.account)

    def test_unsupported_schema_raises_an_actionable_error(self):
        with self.repo.connect() as db:
            db.execute("UPDATE metadata SET value='99' WHERE key='schema_version'")
        with self.assertRaises(SaveSchemaError) as caught:
            SqliteSaveRepository(self.repo.path)
        message = str(caught.exception)
        self.assertIn('99', message)
        self.assertIn('backup', message.casefold())
        self.assertIn('older server', message.casefold())

    def test_cli_reports_unsupported_schema_with_a_stable_code(self):
        with self.repo.connect() as db:
            db.execute("UPDATE metadata SET value='99' WHERE key='schema_version'")
        error = io.StringIO()
        with redirect_stderr(error):
            code = run(['--db', str(self.repo.path), 'list-gem-villages'])
        self.assertEqual(code, 3)
        self.assertIn('[VL-SAVE-SCHEMA-UNSUPPORTED]', error.getvalue())

    def test_cli_reports_backup_failure_with_a_stable_code(self):
        error = io.StringIO()
        destination = self.root / 'new-backup.sqlite3'
        with patch.object(SqliteSaveRepository, 'backup_to',
                          side_effect=PermissionError('denied')):
            with redirect_stderr(error):
                code = run(['--db', str(self.repo.path), 'backup-db', str(destination)])
        self.assertEqual(code, 3)
        self.assertIn('[VL-SAVE-BACKUP-FAILED]', error.getvalue())
        self.assertIn('active save was not changed', error.getvalue())


if __name__ == '__main__':
    unittest.main()
