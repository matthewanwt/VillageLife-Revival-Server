"""Missing requests must remain diagnostic-only and privacy-minimised."""
from pathlib import Path
import tempfile
import unittest
import zipfile
import json
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.support import endpoint_shape, record_missing, export_missing, export_support


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
