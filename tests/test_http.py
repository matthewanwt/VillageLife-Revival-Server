import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from villagelife.transport.http_api import ApiServer
from villagelife.persistence.sqlite_store import SqliteSaveRepository


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        repo = SqliteSaveRepository(Path(self.temp.name) / 'state.sqlite3')
        self.account = repo.create_account('Test')
        self.other = repo.create_account('Other')
        self.server = ApiServer(('127.0.0.1', 0), repo)
        self.token = self.server.tokens.issue(self.account)
        self.other_token = self.server.tokens.issue(self.other)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.thread.join, 2)

    def request(self, method, path, data=None, token=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        headers = {'Accept': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer '+token
        raw = None
        if data is not None:
            headers['Content-Type'] = 'application/json'
            raw = json.dumps(data)
        conn.request(method, path, raw, headers)
        res = conn.getresponse()
        status, body = res.status, json.loads(res.read())
        conn.close()
        return status, body

    def test_auth_ownership_and_unimplemented_actions(self):
        self.assertEqual(self.request('GET', '/health')[0], 200)
        self.assertEqual(self.request('GET', '/v1/villages')[0], 401)
        status, data = self.request('POST', '/v1/villages', {}, self.token)
        self.assertEqual(status, 201)
        vid = data['villageId']
        self.assertEqual(self.request('GET', '/v1/villages/'+vid, token=self.token)[0], 200)
        self.assertEqual(self.request('GET', '/v1/villages/'+vid, token=self.other_token)[0], 404)
        status, data = self.request('POST', f'/v1/villages/{vid}/actions',
                                    {'action': 'building.work.start', 'data': {},
                                     'operationKey': 'one'}, self.token)
        self.assertEqual(status, 501)
        self.assertEqual(self.request('GET', '/web/ClientService/Login', token=self.token)[0], 404)


if __name__ == '__main__':
    unittest.main()
