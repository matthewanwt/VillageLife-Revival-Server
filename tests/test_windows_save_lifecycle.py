"""Synthetic multi-account/multi-save tests. No real player data required."""
from contextlib import closing
from pathlib import Path
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.persistence.legacy_import import LegacySaveImporter
from villagelife.persistence.portable import PortableSaves
from villagelife.core.model import empty_native_village
from villagelife.catalog.sqlite_catalog import OriginalGameCatalog


class WindowsSaveLifecycle(unittest.TestCase):
    def test_process_death_keeps_committed_save_and_discards_interrupted_write(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = SqliteSaveRepository(Path(directory) / 'worlds.sqlite3')
            village = repo.create_village(repo.create_account(), {'gems': 237})
            with repo.connect() as db:
                self.assertEqual(db.execute('PRAGMA synchronous').fetchone()[0], 2)
            child = subprocess.Popen([sys.executable, '-c', """
import sqlite3
import sys
import time
db = sqlite3.connect(sys.argv[1], isolation_level=None)
db.execute("PRAGMA synchronous=FULL")
db.execute("UPDATE villages SET payload_json=?", ('{"gems":238}',))
db.execute("BEGIN IMMEDIATE")
db.execute("UPDATE villages SET payload_json=?", ('{"gems":0}',))
print("interrupted", flush=True)
time.sleep(30)
""", str(repo.path)], stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'interrupted')
                self.assertGreater(repo.path.with_name(repo.path.name+'-wal').stat().st_size, 0)
            finally:
                if child.poll() is None:
                    child.kill()
                child.wait(timeout=10)
                child.stdout.close()
            reopened = SqliteSaveRepository(repo.path)
            self.assertEqual(reopened.read_village(village).payload, {'gems': 238})
            with reopened.connect() as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')

    def test_backup_closed_and_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); repo=SqliteSaveRepository(root/'active.sqlite3')
            owner=repo.create_account('private-local-A')
            village=repo.create_village(owner, empty_native_village())
            backup=root/'backup.sqlite3'
            repo.backup_to(backup)
            with self.assertRaises(FileExistsError): repo.backup_to(backup)
            with closing(sqlite3.connect(backup)) as conn:
                self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            backup.unlink() # Must not hold an open SQLite handle on Windows.
            self.assertTrue(repo.read_village(village).payload)
            # Also verify that all checkpoint/WAL connections are closed.
            repo.checkpoint()
            with closing(sqlite3.connect(repo.path)) as conn:
                self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            repo.path.unlink() # Windows regression: should not raise WinError 32.

    def test_catalog_can_be_removed_after_read(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'catalog.sqlite3'
            with closing(sqlite3.connect(path)) as conn:
                conn.execute('CREATE TABLE fixtures(id INTEGER PRIMARY KEY, name TEXT)')
                conn.execute('INSERT INTO fixtures VALUES (?,?)',(1,'A'))
                conn.commit()
            cat=OriginalGameCatalog(path)
            self.assertEqual(cat.row_by_id('fixtures',1)['name'],'A')
            self.assertEqual(len(cat.rows('fixtures')),1)
            path.unlink()

    def test_separate_players_and_rich_unknown_data_survive_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); old=root/'legacy-private-state'; old.mkdir()
            repo=SqliteSaveRepository(root/'new.sqlite3')
            source_hashes={}; originals={}
            for c, area, identity in [('a','Riverside','villager-A'),('b','Mountain','villager-B')]:
                key=c*64
                profile={'displayName': 'Test '+c, 'deviceId': 'synthetic-'+c,
                         'pId': 'fixture-'+c, 'opaque':{'future':'unchanged'}}
                save={'version':211, 'normal':{'area':area,'world':{'entities':[{'id':identity,'buildingJob':{'due':1987760000}}]},
                       'familyTree':{'root':identity},'inventory':{'coins':500 if c=='a' else 987}},
                      'unrecognized':{'deep': [1, 'Ñ', {'flag':True}]}}
                pp=old/(key+'.json'); sp=old/(key+'.tutorial.json')
                pp.write_text(json.dumps(profile,ensure_ascii=False),encoding='utf-8')
                sp.write_text(json.dumps(save,ensure_ascii=False),encoding='utf-8')
                source_hashes[key]=(hashlib.sha256(pp.read_bytes()).hexdigest(),hashlib.sha256(sp.read_bytes()).hexdigest())
                originals[key]=(profile,save)
            importer=LegacySaveImporter(repo)
            dry=importer.import_directory(old)
            self.assertEqual(len(dry),2)
            self.assertTrue(all(item.village_id is None for item in dry))
            self.assertEqual(repo.list_all_villages(),[])
            applied=importer.import_directory(old,apply=True)
            self.assertEqual(len({item.account_id for item in applied}),2)
            self.assertEqual(len({item.village_id for item in applied}),2)
            for item in applied:
                snap=repo.read_village(item.village_id)
                self.assertEqual(snap.payload['originalProfile'],originals[item.source][0])
                self.assertEqual(snap.payload['originalSave'],originals[item.source][1])
                self.assertEqual(snap.account_id,item.account_id)
                self.assertEqual(snap.format,'legacy.profile+tutorial.v1')
                exp=root/(item.source+'.vl-save.zip')
                PortableSaves(repo).export(item.village_id, exp)
                another=repo.create_account('new device '+item.source)
                new_id=PortableSaves(repo).import_as_new(exp,another)
                self.assertNotEqual(new_id,item.village_id)
                self.assertEqual(repo.read_village(new_id).payload,snap.payload)
            self.assertEqual(len(repo.list_all_villages()),4)
            self.assertTrue(all(x.status=='already-imported' for x in importer.import_directory(old,apply=True)))
            for key, hashes in source_hashes.items():
                self.assertEqual(hashes,(hashlib.sha256((old/(key+'.json')).read_bytes()).hexdigest(),
                                         hashlib.sha256((old/(key+'.tutorial.json')).read_bytes()).hexdigest()))

    def test_missing_save_detected_without_invention(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory); inp=path/'source'; inp.mkdir()
            (inp/('c'*64+'.json')).write_text('{"displayName":"Only profile"}',encoding='utf-8')
            repo=SqliteSaveRepository(path/'db.sqlite3')
            result=LegacySaveImporter(repo).import_directory(inp,apply=True)[0]
            self.assertFalse(result.has_save)
            self.assertIsNone(repo.read_village(result.village_id).payload['originalSave'])
