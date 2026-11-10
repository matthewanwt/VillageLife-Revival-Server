"""Small stdlib HTTP transport for the NEW documented API.

Not a replacement for the original APK's endpoints. Loopback only. Host online
with a TLS reverse proxy and account authentication, not by binding 0.0.0.0.
"""
from __future__ import annotations
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit
import json
import logging
import re
from villagelife.core.errors import (InvalidAction, NotFound, RevisionConflict,
                                       DuplicateActionConflict, NotImplementedRule)
from villagelife.core.model import empty_native_village
from villagelife.persistence.auth_store import AccountTokens
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.services.dispatcher import ActionDispatcher
from villagelife.services.jobs import WorldTickCoordinator
from villagelife.core.clock import SystemClock
from villagelife.support import record_missing

LOG = logging.getLogger(__name__)
MAX_REQUEST = 1 * 1024 * 1024
VILLAGE_PATH = re.compile(r'^/v1/villages/([0-9a-f-]{36})$')
ACTION_PATH = re.compile(r'^/v1/villages/([0-9a-f-]{36})/actions$')
TICK_PATH = re.compile(r'^/v1/villages/([0-9a-f-]{36})/tick$')


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, repo: SqliteSaveRepository):
        super().__init__(address, ApiHandler)
        self.repo = repo
        self.tokens = AccountTokens(repo)
        self.dispatcher = ActionDispatcher.safe_default(repo)
        self.ticks = WorldTickCoordinator(repo, SystemClock())


class ApiHandler(BaseHTTPRequestHandler):
    server: ApiServer
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt: str, *args) -> None:
        # Never include bearer tokens, body contents or private account data.
        LOG.info('%s %s', self.client_address[0], fmt % args)

    def _json(self, status: int, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(payload)

    def _read_json(self) -> dict[str, Any]:
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            raise InvalidAction('Content-Type must be application/json')
        raw_length = self.headers.get('Content-Length', '')
        if not raw_length.isdecimal() or not 0 < int(raw_length) <= MAX_REQUEST:
            raise InvalidAction('Invalid request length')
        raw = self.rfile.read(int(raw_length))
        payload = json.loads(raw.decode('utf-8'))
        if not isinstance(payload, dict):
            raise InvalidAction('JSON object required')
        return payload

    def _auth(self) -> str:
        account_id = self.server.tokens.authenticate(self.headers.get('Authorization'))
        if not account_id:
            raise PermissionError('Invalid or missing account token')
        return account_id

    def _owner(self, account_id: str, village_id: str):
        snapshot = self.server.repo.read_village(village_id)
        if snapshot.account_id != account_id:
            # Avoid disclosing whether other users' villages exist.
            raise NotFound('Village not found')
        return snapshot

    def _record_missing(self, method: str, path: str, status: int) -> None:
        # Diagnostics must NEVER change the original HTTP response if storage fails.
        try:
            record_missing(self.server.repo, method, path, status)
        except Exception:
            LOG.warning('Could not record missing request; HTTP response is unchanged')

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if path == '/health':
                return self._json(200, {'ok': True, 'service': 'villagelife-revival-server', 'api': 1})
            if path.startswith('/web/'):
                self._record_missing('GET', path, 404)
                return self._json(404, {'error': 'Original-client protocol is not implemented by this NEW backend'})
            owner = self._auth()
            if path == '/v1/villages':
                return self._json(200, {'villages': [self._meta(s) for s in self.server.repo.list_villages(owner)]})
            match = VILLAGE_PATH.fullmatch(path)
            if match:
                snap = self._owner(owner, match.group(1))
                return self._json(200, {'village': self._meta(snap), 'payload': snap.payload})
            self._record_missing(self.command, path, 404)
            return self._json(404, {'error': 'Unknown endpoint'})
        except Exception as exc:
            self._fail(exc)

    def do_POST(self):
        try:
            path = urlsplit(self.path).path
            if path.startswith('/web/'):
                self._record_missing('POST', path, 501)
                # The unimplemented binary client may have sent an unread body.
                self.close_connection = True
                return self._json(501, {'error': 'Original-client protocol is not implemented by this NEW backend'})
            owner = self._auth()
            if path == '/v1/villages':
                request = self._read_json()
                if request and request != {'initialAreaId': 1}:
                    raise InvalidAction('Only empty development villages can be created yet')
                village_id = self.server.repo.create_village(owner, empty_native_village())
                return self._json(201, {'villageId': village_id, 'developmentOnly': True})
            action = ACTION_PATH.fullmatch(path)
            if action:
                snap = self._owner(owner, action.group(1))
                request = self._read_json()
                key = request.get('operationKey')
                if not isinstance(key, str) or not key:
                    raise InvalidAction('operationKey is required')
                revision = request.get('expectedRevision')
                if revision is not None and (type(revision) is not int or revision < 0):
                    raise InvalidAction('expectedRevision must be a nonnegative integer')
                _, response, repeated = self.server.dispatcher.execute(
                    snap.village_id, name=request.get('action', ''),
                    payload=request.get('data', {}), operation_key=key, expected_revision=revision)
                return self._json(200, {'response': response, 'replayed': repeated})
            tick = TICK_PATH.fullmatch(path)
            if tick:
                self._owner(owner, tick.group(1))
                request = self._read_json()
                if request:
                    raise InvalidAction('Tick request must be an empty object')
                ready = self.server.ticks.advance_village(tick.group(1))
                return self._json(200, {'readyJobIds': ready})
            self._record_missing(self.command, path, 404)
            return self._json(404, {'error': 'Unknown endpoint'})
        except Exception as exc:
            self._fail(exc)

    @staticmethod
    def _meta(snap) -> dict[str, Any]:
        return {'id': snap.village_id, 'format': snap.format,
                'schemaVersion': snap.schema_version, 'revision': snap.revision}

    def _fail(self, error: Exception) -> None:
        if isinstance(error, PermissionError):
            return self._json(401, {'error': str(error)})
        if isinstance(error, NotFound):
            return self._json(404, {'error': str(error)})
        if isinstance(error, RevisionConflict):
            return self._json(409, {'error': str(error)})
        if isinstance(error, DuplicateActionConflict):
            return self._json(409, {'error': str(error)})
        if isinstance(error, NotImplementedRule):
            self._record_missing(self.command, urlsplit(self.path).path, 501)
            return self._json(501, {'error': str(error)})
        if isinstance(error, (InvalidAction, ValueError, UnicodeError, json.JSONDecodeError)):
            return self._json(400, {'error': str(error)})
        LOG.exception('Unexpected API failure')
        return self._json(500, {'error': 'Internal server error'})


def serve(repo: SqliteSaveRepository, port: int = 8765) -> None:
    with ApiServer(('127.0.0.1', port), repo) as server:
        LOG.info('Village Life new API listening on 127.0.0.1:%d', port)
        server.serve_forever(poll_interval=0.2)
