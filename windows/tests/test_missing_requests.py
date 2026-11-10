"""New observability tests: never need actual player saves or original game files."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
import zipfile

_BACKEND = Path(__file__).resolve().parents[2] / 'legacy_reference' / 'backend'
sys.path.insert(0, str(_BACKEND))

from missing_requests import MissingRequestRecorder, safe_operation, safe_route
from export_missing_requests import build_summary, export_missing, _safe_entry


class FakeClock:
    now = 0.0
    def __call__(self): return self.now


class MissingRequestRecorderTests(unittest.TestCase):
    def test_process_501_is_logged_without_request_payload_or_identifiers(self):
        with tempfile.TemporaryDirectory() as tmp:
            location = Path(tmp) / 'backend/private_state/diagnostics/missing_requests.jsonl'
            clock = FakeClock()
            monitor = MissingRequestRecorder(location, clock=clock)
            doc = {'pId': 'SECRET-ID', 'data': {'calls': [
                {'id': '998', 'service': 'ClientBuildingService/UndocumentedTask',
                 'data': {'email': 'sensitive@example.org', 'name': 'Alice', 'deviceId': 'SAVEID'}},
                {'id': '999', 'service': 'ClientTaskService/HarvestTask', 'data': {}}]}}
            reply = {'data': {'calls': [
                {'id': '998', 'code': 501, 'message': 'Unimplemented: sensitive@example.org'},
                {'id': '999', 'code': 200, 'message': ''}]}}
            monitor.rpc_failures('/web/ClientService/Process?key=SHOULD-NOT-LEAK', doc, reply)
            raw = location.read_text('utf-8')
            self.assertIn('ClientBuildingService/UndocumentedTask', raw)
            for secret in ('sensitive@example.org', 'Alice', 'SECRET-ID', 'SAVEID', '998', '999', 'SHOULD-NOT-LEAK'):
                self.assertNotIn(secret, raw)
            result = export_missing(tmp)
            with zipfile.ZipFile(result) as archive:
                data = json.loads(archive.read('missing-requests-summary.json'))
                self.assertEqual(len(data['entries']), 1)
                self.assertFalse(data['contains_raw_game_requests'])

    def test_throttling_is_bounded_and_counts_appear(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            dest = Path(tmp) / 'requests.jsonl'
            recorder = MissingRequestRecorder(dest, clock=clock)
            for _ in range(150):
                recorder.record(method='POST', route='/web/ClientService/Process',
                                operation='ClientVillager/Undocumented', status=501)
            lines = dest.read_text('utf-8').splitlines()
            self.assertEqual(len(lines), 2)  # first and hundredth hits
            self.assertEqual(json.loads(lines[-1])['observed_this_session'], 100)
            clock.now = 65.0
            recorder.record(method='POST', route='/web/ClientService/Process',
                            operation='ClientVillager/Undocumented', status=501)
            self.assertEqual(len(dest.read_text('utf-8').splitlines()), 3)

    def test_unknown_route_and_bad_service_are_hashed(self):
        self.assertNotIn('Alice', safe_route('/private/Alice/orders'))
        self.assertNotIn('alice@example', safe_operation('alice@example.org'))
        self.assertTrue(safe_route('/private/Alice/orders').startswith('unrecognised-route-sha256-'))

    def test_export_filters_malicious_or_unexpected_json_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'backend/private_state/diagnostics/missing_requests.jsonl'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({'format': 'VillageLifeMissingRequestV1',
                                        'method': 'POST', 'route': '/alice/private', 'operation': 'Alice',
                                        'status': 501, 'category': 'not_implemented',
                                        'secret': 'password'}) + '\n')
            summary = build_summary(path)
            self.assertEqual(summary['entries'], [])
            self.assertEqual(summary['rejected_entries'], 1)
            self.assertNotIn('password', json.dumps(summary))

    def test_400_implemented_validation_is_not_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'requests.jsonl'
            monitor = MissingRequestRecorder(dest)
            req = {'data': {'calls': [{'id': 42, 'service': 'ClientArea/UnlockArea', 'data': {'id': 1}}]}}
            reply = {'data': {'calls': [{'id': '42', 'code': 400, 'message': 'Invalid input'}]}}
            monitor.rpc_failures('/web/ClientService/Process', req, reply)
            self.assertFalse(dest.exists())

    def test_actual_legacy_http_unknown_routes_recorded_without_raw_data(self):
        from http.client import HTTPConnection
        from threading import Lock, Thread
        import server as legacy_server
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            server = legacy_server.Server(('127.0.0.1', 0), legacy_server.Handler)
            server.missing = MissingRequestRecorder(root / 'backend/private_state/diagnostics/missing_requests.jsonl')
            server.summary_logs = False
            server.access_file = None
            server.log = root / 'private-http.jsonl'
            server.log_lock = Lock()
            server.assets = {}
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                conn = HTTPConnection('127.0.0.1', server.server_port, timeout=2)
                conn.request('GET', '/private/Alice/avatar.jpg?token=SECRET')
                response = conn.getresponse()
                self.assertEqual(response.status, 404)
                response.read()
                conn.close()
                conn = HTTPConnection('127.0.0.1', server.server_port, timeout=2)
                conn.request('POST', '/private/Alice/API?token=SECRET',
                             body=b'{"data":{"calls":[]},"deviceId":"SAVEID"}',
                             headers={'Content-Type':'application/json'})
                response = conn.getresponse()
                self.assertEqual(response.status, 501)
                self.assertEqual(json.loads(response.read())['code'], 501)
                conn.close()
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)
            summary = build_summary(root / 'backend/private_state/diagnostics/missing_requests.jsonl')
            self.assertEqual({e['status'] for e in summary['entries']}, {404, 501})
            exported = json.dumps(summary)
            for sensitive in ('Alice', 'SECRET', 'SAVEID'):
                self.assertNotIn(sensitive, exported)

    def test_server_code_has_report_hooks_without_changing_response_codec(self):
        source = (_BACKEND / 'server.py').read_text('utf-8')
        self.assertIn('self.server.missing.rpc_failures(self.path,document,response)', source)
        self.assertIn('self.server.missing.rpc_failures(self.path,document,response,community=True)', source)
        self.assertIn('encode(response,compressed=mode==\'zlib-xor\')', source)


if __name__ == '__main__': unittest.main()
