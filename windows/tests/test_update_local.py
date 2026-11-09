import copy
import io
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import update_local as updater
import migrate_save
import session
import world


class SaveMigrationTests(unittest.TestCase):
    def setUp(self):
        self.saved = session.fresh_tutorial()
        self.saved['normal'] = world.build_bridge_world(self.saved, 1000)

    def test_existing_progress_names_birth_dates_and_inventory_are_preserved(self):
        state = self.saved['normal']
        world.migrate_authored_area(state)
        person = next(v for v in state['world']['entities'] if v['templateType'] == 'villager_type')
        person.update(name='My custom name', bornAt=123, startAge=42)
        state['inventory']['323'] = 17
        state['inventory']['325'] = 91
        state['charmReceipts'] = {'earned': {'selected': 151}}
        original = copy.deepcopy(self.saved)
        result, _ = migrate_save.migrate_document(self.saved, '12')
        self.assertEqual(self.saved, original)
        after = next(v for v in result['normal']['world']['entities'] if v['id'] == person['id'])
        self.assertEqual(after, person)
        self.assertEqual(result['normal']['inventory'], state['inventory'])
        self.assertEqual(result['normal']['charmReceipts'], state['charmReceipts'])
        self.assertEqual(migrate_save.migrate_document(result, '12'), (result, []))

    def test_legacy_area_migration_does_not_deage_an_existing_starter(self):
        actor = next(v for v in self.saved['normal']['world']['entities'] if v['templateType'] == 'villager_type')
        actor.update(startAge=51, bornAt=77, energyLevel=4)
        result, _ = migrate_save.migrate_document(self.saved, '12')
        after = next(v for v in result['normal']['world']['entities'] if v['id'] == actor['id'])
        self.assertEqual(after, actor)

    def test_bad_references_and_newer_versions_are_not_guessed_away(self):
        bad = copy.deepcopy(self.saved)
        actor = next(v for v in bad['normal']['world']['entities'] if v['templateType'] == 'villager_type')
        actor['shelterBedId'] = 'missing-bed'
        with self.assertRaises(ValueError):
            migrate_save.migrate_document(bad, '12')
        bad = copy.deepcopy(self.saved)
        bad['normal']['schemaVersion'] = 99
        with self.assertRaises(ValueError):
            migrate_save.migrate_document(bad, '12')

    def test_tutorial_only_save_is_preserved_and_identity_repaired_once(self):
        saved = session.fresh_tutorial()
        saved['userHash']['data']['villagers'][0].pop('id')
        result, repairs = migrate_save.migrate_document(saved, '12')
        self.assertTrue(repairs)
        self.assertNotIn('normal', result)
        self.assertEqual(migrate_save.migrate_document(result, '12'), (result, []))

    def test_all_villages_validated_before_any_staged_file_is_written(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for device, invalid in [('a', False), ('b', True)]:
                ident = hashlib.sha256(device.encode()).hexdigest()
                (root / (ident + '.json')).write_text(json.dumps({'deviceId': device, 'pId': device}))
                saved = copy.deepcopy(self.saved)
                if invalid:
                    saved['normal']['inventory']['323'] = -1
                (root / (ident + '.tutorial.json')).write_text(json.dumps(saved))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            with self.assertRaises(ValueError):
                migrate_save.migrate_directory(root)
            self.assertEqual(before, {p.name: p.read_bytes() for p in root.iterdir()})


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = self.root / 'old village & spaces café村'
        self.package = self.root / 'update kit'
        self.old.mkdir()
        self.package.mkdir()
        self.write(self.old, 'Village Life.exe', 'old')
        self.write(self.old, 'VERSION.json', json.dumps({'restoration_version': '0.2.4-community-test'}))
        self.write(self.old, 'play-settings.json', json.dumps({'instance': 'Pie64_1', 'server_mode': 'local'}))
        self.write(self.old, 'backend/private_state/player.json', '{"untouched":true}')
        self.write(self.old, 'Original.xapk', 'fake archive for isolated test')
        self.write(self.old, 'analysis/local-client/local-signing.pfx', 'private key fixture')
        self.archive_sha = updater.digest(self.old / 'Original.xapk')
        self.addCleanup(patch.stopall)
        patch.object(updater, 'ARCHIVE_SHA', self.archive_sha).start()
        for relative in ('Village Life.exe', 'runtime/python/python.exe', 'tools/migrate_save.py',
                         'tools/update_local.py', 'backend/world.py'):
            self.write(self.package, relative, 'new')
        self.write(self.package, 'VERSION.json', json.dumps({'restoration_version': '0.2.5-community-test'}))
        self.manifest()

    def write(self, root, relative, value):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding='utf-8')

    def manifest(self):
        files = {p.relative_to(self.package).as_posix(): {'bytes': p.stat().st_size, 'sha256': updater.digest(p)}
                 for p in self.package.rglob('*') if p.is_file() and p.name != 'PACKAGE-MANIFEST.json'}
        self.write(self.package, 'PACKAGE-MANIFEST.json', json.dumps(
            {'version': '0.2.5-community-test', 'personal_data_included': False, 'files': files}))

    def run_update(self, **kwargs):
        return updater.update(self.old, self.package, guard=lambda *_: None,
                              migrate=kwargs.pop('migrate', lambda stage: None), **kwargs)

    def test_success_preserves_source_settings_keys_and_backed_up_save(self):
        before = updater.snapshot(self.old)
        def migrate(stage):
            self.write(stage, 'backend/private_state/player.json', '{"upgraded":true}')
        target = self.run_update(migrate=migrate)
        self.assertEqual(before, updater.snapshot(self.old))
        self.assertEqual((target / 'analysis/local-client/local-signing.pfx').read_bytes(),
                         (self.old / 'analysis/local-client/local-signing.pfx').read_bytes())
        self.assertEqual(json.loads((target / 'UPDATE-RECEIPT.json').read_text())['status'], 'ready')
        self.assertTrue(list((self.old / 'backups').glob('*/backend/private_state/player.json')))
        self.assertTrue((target / 'ROLLBACK.txt').is_file())
        with self.assertRaises(ValueError):
            self.run_update()

    def test_failed_migration_and_interruption_leave_old_save_and_no_active_update(self):
        before = updater.snapshot(self.old)
        def broken(stage):
            self.write(stage, 'backend/private_state/player.json', 'broken migration')
            raise RuntimeError('simulated interrupted migration')
        with self.assertRaises(RuntimeError):
            self.run_update(migrate=broken)
        self.assertEqual(before, updater.snapshot(self.old))
        self.assertFalse(self.old.with_name(self.old.name + '-0.2.5-community-test').exists())
        stage = next(self.root.glob('*.staging-*'))
        self.assertEqual(json.loads((stage / 'UPDATE-RECEIPT.json').read_text())['status'], 'failed-original-retained')
        # An abandoned stage does not prevent a clean retry.
        self.assertTrue(self.run_update().is_dir())

    def test_bad_package_is_rejected_before_backup_or_copy(self):
        self.write(self.package, 'backend/world.py', 'damaged')
        with self.assertRaises(ValueError):
            self.run_update()
        self.assertFalse((self.old / 'backups').exists())

    def test_path_traversal_windows_aliases_and_private_payload_are_rejected(self):
        for name in ('../escape', 'C:/escape', 'tools/../escape', 'CON.txt', 'tools/a.',
                     'tools/a:stream', 'tools\\escape', 'tools//duplicate', 'tools/./duplicate'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                updater.safe_path(self.root, name)
        self.write(self.package, 'backend/private_state/leak.json', '{}')
        self.manifest()
        with self.assertRaises(ValueError):
            self.run_update()

    def test_concurrent_save_change_is_detected_before_activation(self):
        def changed(stage):
            self.write(self.old, 'backend/private_state/player.json', '{"new_player_progress":true}')
        with self.assertRaises(RuntimeError):
            self.run_update(migrate=changed)
        self.assertFalse(self.old.with_name(self.old.name + '-0.2.5-community-test').exists())
        self.assertIn('new_player_progress', (self.old / 'backend/private_state/player.json').read_text())

    def test_running_game_no_space_and_hosted_mode_do_not_start_update(self):
        with patch.object(updater.shutil, 'disk_usage', return_value=type('Disk', (), {'free': 0})()):
            with self.assertRaises(RuntimeError):
                self.run_update()
        self.write(self.old, 'play-settings.json', '{"server_mode":"online"}')
        with self.assertRaises(ValueError):
            self.run_update()
        self.assertFalse((self.old / 'backups').exists())

    def test_nan_and_duplicate_save_keys_are_rejected(self):
        for contents in ('{"balance":NaN}', '{"balance":1,"balance":2}'):
            path = self.root / 'bad.json'
            path.write_text(contents)
            with self.assertRaises(ValueError):
                migrate_save.load_json(path)

    def test_legacy_console_encoding_does_not_fail_after_a_successful_unicode_update(self):
        stream = io.TextIOWrapper(io.BytesIO(), encoding='cp1252')
        with patch.object(updater.sys, 'stdout', stream):
            target = self.run_update()
        self.assertTrue(target.is_dir())
        stream.close()


if __name__ == '__main__':
    unittest.main()
