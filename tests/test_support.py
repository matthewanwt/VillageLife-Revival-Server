"""Missing requests must remain diagnostic-only and privacy-minimised."""
from pathlib import Path
import tempfile
import unittest
import zipfile
import json
import re
from unittest.mock import patch
from datetime import datetime, timezone
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.support import (endpoint_shape, record_missing, export_missing,
                                 export_support, record_original_call, begin_diagnostic_run)


class SupportTests(unittest.TestCase):
    def test_endpoint_does_not_leak_path_values(self):
        secret='/web/players/PRIVATE_PERSON_SECRET/long-token-6789'
        self.assertNotIn('PRIVATE',endpoint_shape(secret))
        self.assertEqual(endpoint_shape('/web/ClientService/Process'),'/web/ClientService/Process')

    def test_aggregate_no_private_request(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder); repo=SqliteSaveRepository(path/'db.sqlite3')
            record_missing(repo,'GET','/web/people/secret123',404)
            record_missing(repo,'GET','/web/people/secret456',404)
            record_missing(repo,'POST','/web/ClientService/Process',501)
            record_missing(repo,'POST','/health',200)
            dest=export_missing(repo)
            with zipfile.ZipFile(dest) as z: text=z.read('missing-requests.json').decode()
            self.assertNotIn('secret123',text)
            self.assertNotIn('secret456',text)
            self.assertIn('ClientService/Process',text)
            self.assertEqual(sum(r['count'] for r in json.loads(text)['records']),3)

    def test_support_bundle_does_not_contain_private_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder); bind=path/'binding.json'
            bind.write_text(json.dumps({'id':'Pie64_4','adb_port':5595,'install_dir':'PRIVATE_FULL_PATH'}))
            out=export_support(path/'export.zip', bind)
            with zipfile.ZipFile(out) as z: text=z.read('diagnostics.json').decode()
            self.assertNotIn('PRIVATE_FULL_PATH',text)
            self.assertIn('Pie64_4',text)

    def test_support_bundle_includes_version_provenance_and_run_summary(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder); repo=SqliteSaveRepository(path/'db.sqlite3')
            begin_diagnostic_run(repo)
            record_original_call(repo, 'ClientMaterialService/GetUserMaterialTypes', 200, {})
            bind=path/'binding.json'
            bind.write_text(json.dumps({'id':'Pie64_4','adb_port':5595,
                                        'install_dir':'PRIVATE_FULL_PATH'}))
            manifest=path/'BUILD-MANIFEST.json'
            manifest.write_text(json.dumps({
                'format':'VillageLifeBuildManifestV1',
                'validation':{'revision':'abc123','passed':True,'dirty_source':False},
                'source_sha256':'deadbeef','authenticode_signed':False,
                'payload_sha256':{'private/file':'secret'}}))
            out=export_support(path/'support.zip', bind, launcher_version='0.4.1',
                               manifest=manifest, repo=repo)
            with zipfile.ZipFile(out) as z:
                diagnostics=json.loads(z.read('diagnostics.json'))
                missing=json.loads(z.read('missing-requests.json'))
            self.assertEqual(diagnostics['server_version'], '0.4.1')
            self.assertEqual(diagnostics['launcher_version'], '0.4.1')
            self.assertEqual(diagnostics['build']['revision'], 'abc123')
            self.assertTrue(diagnostics['build']['validation_passed'])
            self.assertEqual(diagnostics['instance_id'], 'Pie64_4')
            self.assertNotIn('PRIVATE_FULL_PATH', json.dumps(diagnostics))
            self.assertNotIn('private/file', json.dumps(diagnostics))
            self.assertEqual(missing['scope'], 'latest_server_run')
            self.assertEqual(missing['call_outcomes'][0]['service_shape'],
                             'ClientMaterialService/GetUserMaterialTypes')

    def test_large_shape_markers_are_plain_text(self):
        with tempfile.TemporaryDirectory() as folder:
            repo=SqliteSaveRepository(Path(folder)/'db.sqlite3')
            record_original_call(repo, 'ClientExample/Truncated', 200,
                                 {f'field{i}': i for i in range(40)})
            with repo.connect() as db:
                shape=db.execute('SELECT response_shape FROM original_call_outcomes').fetchone()[0]
            self.assertIn('...', shape)
            self.assertNotIn('Ã', shape)

    def test_reported_version_matches_project_and_launcher(self):
        from villagelife import __version__
        root = Path(__file__).resolve().parents[1]
        project = (root / 'pyproject.toml').read_text(encoding='utf-8')
        launcher = (root / 'windows/launcher/Program.cs').read_text(encoding='utf-8')
        self.assertEqual(__version__,
                         re.search(r'^version = "([^"]+)"', project, re.MULTILINE).group(1))
        self.assertIn(f'const string ReleaseVersion = "{__version__}";', launcher)

    def test_habitat_failures_get_useful_private_value_free_categories(self):
        with tempfile.TemporaryDirectory() as folder:
            repo=SqliteSaveRepository(Path(folder)/'db.sqlite3')
            record_original_call(repo,'ClientUserShelterService/AssignBedToVillager',400,
                response={},request={'villagerId':'PRIVATE_VILLAGER',
                                     'shelterBedId':'PRIVATE_BED'},
                failure_message='Unknown bed in this village')
            with repo.connect() as db:
                row=db.execute('SELECT request_shape,response_shape FROM original_call_request_outcomes').fetchone()
            self.assertIn('shelter_bed_unknown',row['response_shape'])
            self.assertNotIn('PRIVATE_VILLAGER',row['request_shape'])
            self.assertNotIn('PRIVATE_BED',row['request_shape'])

    def test_run_export_excludes_legacy_and_previous_run_even_in_same_second(self):
        with tempfile.TemporaryDirectory() as folder, patch('villagelife.support.datetime') as clock:
            clock.now.return_value = datetime(2026, 11, 12, tzinfo=timezone.utc)
            path = Path(folder)
            repo = SqliteSaveRepository(path / 'db.sqlite3')
            service = 'ClientMaterialService/StartLearningMaterial'
            record_missing(repo, 'RPC', 'ClientUser/CompleteTutorial', 501)
            empty = export_missing(repo, path / 'empty.zip', current_run_only=True)
            with zipfile.ZipFile(empty) as archive:
                self.assertEqual(json.loads(archive.read('missing-requests.json'))['records'], [])

            begin_diagnostic_run(repo)
            record_missing(repo, 'RPC', service, 501)
            record_original_call(repo, service, 501, request={'materialTypeId': 178})
            new_server = SqliteSaveRepository(repo.path)
            begin_diagnostic_run(new_server)
            # A process from the old run finishing a request cannot contaminate the export.
            record_missing(repo, 'RPC', service, 501)
            record_original_call(repo, service, 501, request={'materialTypeId': 178})
            record_original_call(new_server, service, 200, request={'materialTypeId': 178})
            fresh_reader = SqliteSaveRepository(repo.path)
            report = export_missing(fresh_reader, path / 'latest.zip', current_run_only=True)
            with zipfile.ZipFile(report) as archive:
                capture = json.loads(archive.read('missing-requests.json'))
            self.assertEqual(capture['scope'], 'latest_server_run')
            self.assertEqual(capture['records'], [])
            outcome, = capture['call_outcomes']
            self.assertEqual((outcome['service_shape'], outcome['response_code'], outcome['count']),
                             (service, 200, 1))
            self.assertEqual(outcome['request_shape'], 'object{materialTypeId:number}')

    def test_wish_outcomes_show_categories_without_private_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = SqliteSaveRepository(Path(folder) / 'db.sqlite3')
            begin_diagnostic_run(repo)
            record_original_call(repo, 'ClientWant/GenerateWaterWants', 200, {
                'result': [
                    {'wantableCategoryType': 1, 'VillagerStringID': 'PRIVATE_ACTOR',
                     'WantId': 'PRIVATE_WISH', 'MaterialID': 2458},
                    {'wantableCategoryType': 8, 'VillagerStringID': 'PRIVATE_ACTOR'},
                ],
            })
            record_original_call(repo, 'ClientVillager/Consume', 200,
                                 {'SatisfiedWantModels': [{'WantId': 'PRIVATE_WISH'}]})
            result = export_missing(repo, current_run_only=True)
            with zipfile.ZipFile(result) as archive:
                report = archive.read('missing-requests.json').decode()
            self.assertIn('pending_wishes={caregiver:1,water:1}', report)
            self.assertIn('wishes_cleared=1', report)
            self.assertNotIn('PRIVATE_ACTOR', report)
            self.assertNotIn('PRIVATE_WISH', report)
            self.assertNotIn('2458', report)
