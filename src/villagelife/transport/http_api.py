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
import os
import re
import socket
import zlib
import secrets
from threading import Lock, BoundedSemaphore
from villagelife.core.validation import validate_json_tree
from villagelife.persistence.history import json_default
from villagelife.core.errors import (InvalidAction, NotFound, RevisionConflict,
                                       DuplicateActionConflict, NotImplementedRule)
from villagelife.core.model import empty_native_village
from villagelife.persistence.auth_store import AccountTokens
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.services.dispatcher import ActionDispatcher
from villagelife.services.jobs import WorldTickCoordinator
from villagelife.core.clock import SystemClock
from villagelife.support import begin_diagnostic_run, record_missing
from villagelife.protocol.legacy_codec import decode as original_decode, encode as original_encode

LOG = logging.getLogger(__name__)
MAX_REQUEST = 1 * 1024 * 1024
VILLAGE_PATH = re.compile(r'^/v1/villages/([0-9a-f-]{36})$')
ACTION_PATH = re.compile(r'^/v1/villages/([0-9a-f-]{36})/actions$')
TICK_PATH = re.compile(r'^/v1/villages/([0-9a-f-]{36})/tick$')


class ApiServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR can let a second listener take the same port.
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def __init__(self, address, repo: SqliteSaveRepository, original=None, assets=None, transport_key=None):
        super().__init__(address, ApiHandler)
        self.repo = repo
        self.original = original
        self.assets = assets
        self.tokens = AccountTokens(repo)
        self.dispatcher = ActionDispatcher.safe_default(repo)
        self.ticks = WorldTickCoordinator(repo, SystemClock())
        self.original_login_count = 0
        self.original_login_lock = Lock()
        self.transport_key = transport_key
        self._workers = BoundedSemaphore(32)

    def process_request(self, request, client_address):
        if not self._workers.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._workers.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._workers.release()


class ApiHandler(BaseHTTPRequestHandler):
    server: ApiServer
    protocol_version = 'HTTP/1.1'
    timeout = 15

    def parse_request(self):
        if not super().parse_request():
            return False
        host = self.headers.get('Host', '').split(':', 1)[0].lower()
        if (host not in {'127.0.0.1', 'localhost', '10.0.2.2'}
                or len(self.headers.get_all('Host', [])) != 1
                or self.headers.get('Origin') is not None
                or self.headers.get('Sec-Fetch-Site') is not None):
            self.send_error(403, 'Native local client required')
            self.close_connection = True
            return False
        if (self.headers.get('Transfer-Encoding') is not None
                or len(self.headers.get_all('Content-Length', [])) > 1):
            self.send_error(400, 'Unsupported request framing')
            self.close_connection = True
            return False
        path = urlsplit(self.path).path
        if self.server.transport_key and path != '/health' and not path.startswith('/v1/'):
            prefix = '/' + self.server.transport_key + '/'
            supplied = self.path[:len(prefix)]
            if not secrets.compare_digest(supplied.encode('utf-8'), prefix.encode('ascii')):
                self.send_error(403, 'Local client capability required')
                self.close_connection = True
                return False
            self.path = '/' + self.path[len(prefix):]
        return True

    def log_message(self, fmt: str, *args) -> None:
        # BaseHTTPRequestHandler's default request log includes the FULL URL,
        # including any secret query parameters. Log only method and HTTP status;
        # no device IDs, tokens, IPs, paths, request bodies or response contents.
        status = str(args[1]) if fmt.startswith('\"%s\" %s') and len(args) > 1 else 'unknown'
        if not status.isdecimal():
            status = 'unknown'
        LOG.info('client_http method=%s status=%s', self.command, status)

    def _json(self, status: int, data: dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False, default=json_default).encode('utf-8')
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
        validate_json_tree(payload, max_depth=48, max_nodes=100000)
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
            if self.server.original and path != '/health' and not path.startswith('/v1/'):
                return self._original_get(path)
            if path == '/health':
                return self._json(200, {'ok': True, 'service': 'villagelife-revival-server', 'api': 1,
                                        'originalClientLogins': self.server.original_login_count,
                                        'pid': os.getpid()})
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
            if self.server.original and path.rstrip('/') in {
                '/web/ClientService/Login', '/web/ClientService/Process',
                '/Playdemic.Community.Web/Client/Home', '/web/Playdemic.Community.Web/Client/Home',
            }:
                path = path.rstrip('/')
                return self._original_post(path)
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


    def _binary(self, status: int, body: bytes, mime: str = 'application/octet-stream') -> None:
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.end_headers()
        self.wfile.write(body)

    def _original_get(self, path: str) -> None:
        # Original resources are never fetched from external servers.
        from urllib.parse import unquote
        path=unquote(path)
        if '..' in path.split('/') or '\\' in path:
            return self._binary(400,b'Invalid path','text/plain')
        if path.endswith('/envvars.txt'):
            return self._binary(200,b'preservation_local=1\r\n','text/plain')
        if path.endswith('/foldername.txt'):
            return self._binary(200,b'foldernamea=local/\r\nfoldernamek=local/\r\n','text/plain')
        assets=self.server.assets
        if path.endswith('/origmanifest.xml') and assets and assets.manifest:
            return self._binary(200,assets.manifest,'application/xml')
        if path.endswith('/quikmanifest.xml') and assets and assets.manifest:
            return self._binary(200,assets.manifest.split(b'>',1)[0]+b'></manifest>','application/xml')
        if assets:
            payload=assets.content(path)
            if payload is not None:return self._binary(200,payload)
        self._record_missing('GET',path,404)
        return self._binary(404,b'<HTML>Not implemented</HTML>','text/html')

    def _original_post(self, path: str) -> None:
        n=self.headers.get('Content-Length','')
        if not n.isdecimal() or not 0<int(n)<=8*1024*1024:
            self.close_connection=True
            return self._binary(400,b'Invalid request length','text/plain')
        try:
            request,mode=original_decode(self.rfile.read(int(n)))
            validate_json_tree(request, max_depth=48, max_nodes=100000)
        except (ValueError,UnicodeError,TypeError,zlib.error,RecursionError,InvalidAction):
            self.close_connection=True
            return self._binary(400,b'Unrecognised original request encoding','text/plain')
        try:
            if path.endswith('/Login'):
                response=self.server.original.login(request)
            elif path.endswith('/Client/Home'):
                response=self.server.original.community.process(request)
            else:
                response=self.server.original.process(request)
            self._binary(200,original_encode(response,compressed=mode=='zlib-xor'))
            if path.endswith('/Login') and response.get('code') == 200:
                with self.server.original_login_lock:
                    self.server.original_login_count += 1
            return
        except (ValueError, KeyError, TypeError) as exc:
            LOG.info('Rejected original-client request: %s',type(exc).__name__)
            return self._binary(400,b'Invalid original-client request','text/plain')
        except Exception:
            if path.endswith('/Process') and isinstance(request, dict):
                calls = request.get('data', {}).get('calls', []) if isinstance(request.get('data'), dict) else []
                if isinstance(calls, list):
                    for call in calls:
                        service = call.get('service') if isinstance(call, dict) else None
                        if isinstance(service, str):
                            try:
                                from villagelife.support import record_original_call
                                record_original_call(self.server.repo, service, 500)
                            except Exception:
                                pass
            LOG.exception('Original-client service failed')
            return self._binary(500,b'Original-client service error','text/plain')

    def _fail(self, error: Exception) -> None:
        if self.command == 'POST':
            self.close_connection = True
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
        if isinstance(error, (InvalidAction, ValueError, UnicodeError, json.JSONDecodeError, RecursionError)):
            return self._json(400, {'error': str(error)})
        LOG.exception('Unexpected API failure')
        return self._json(500, {'error': 'Internal server error'})


def serve(repo: SqliteSaveRepository, port: int = 8765, *, original=None, assets=None, transport_key=None) -> None:
    with ApiServer(('127.0.0.1', port), repo, original, assets, transport_key=transport_key) as server:
        begin_diagnostic_run(repo)
        LOG.info('Village Life new API listening on 127.0.0.1:%d', port)
        server.serve_forever(poll_interval=0.2)
