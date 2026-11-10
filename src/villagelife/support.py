"""Privacy-minimised diagnostics: JSON key/type shapes only, no values or identifiers."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import tempfile
import zipfile
from villagelife.persistence.sqlite_store import SqliteSaveRepository

ALLOWED = {'/web/ClientService/Login', '/web/ClientService/Process', '/health'}


def endpoint_shape(path: str) -> str:
    """Keep only a fixed allowlist or a structural count, never user-supplied text."""
    if path in ALLOWED:
        return path
    if re.fullmatch(r'(?:Client|Friend|Community)[A-Za-z0-9]{0,60}/[A-Za-z0-9]{1,90}',path):
        return path
    return '/unrecognised/' + str(min(10, len([p for p in path.split('/') if p])))


def record_missing(repo: SqliteSaveRepository, method: str, path: str, status: int) -> None:
    if method not in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'RPC') or status not in (404, 501):
        return
    shape = endpoint_shape(path)
    with repo.transaction() as db:
        db.execute('''INSERT INTO missing_requests (method, endpoint_shape, response_status, count, last_seen)
                      VALUES (?,?,?,?,?)
                      ON CONFLICT(method, endpoint_shape, response_status) DO UPDATE SET
                      count=count+1, last_seen=excluded.last_seen''',
                   (method, shape, status, 1, int(datetime.now(timezone.utc).timestamp())))


def _response_shape(value, depth: int = 0) -> str:
    """Summarize JSON structure without retaining any response values."""
    if isinstance(value, dict):
        if depth >= 3:
            return 'object'
        fields = []
        for key in sorted(value)[:32]:
            name = str(key)
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,80}', name):
                name = 'other'
            fields.append(name + ':' + _response_shape(value[key], depth + 1))
        return 'object{' + ','.join(fields) + ('…' if len(value) > 32 else '') + '}'
    if isinstance(value, list):
        if not value:
            return 'array'
        forms = sorted({_response_shape(item, depth + 1) for item in value[:4]})
        return 'array<' + '|'.join(forms[:4]) + ('|…' if len(forms) > 4 else '') + '>'
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, (int, float)):
        return 'number'
    if isinstance(value, str):
        return 'string'
    return 'other'


def record_original_call(repo: SqliteSaveRepository, service: str, status: int,
                         response: dict | None = None, request: dict | None = None) -> None:
    """Aggregate RPC outcome and JSON structures, never IDs or values."""
    if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
        return
    shape = endpoint_shape(service)
    result_shape = _response_shape(response if response is not None else {})[:4000]
    request_shape = _response_shape(request if request is not None else {})[:4000]
    with repo.transaction() as db:
        db.execute('''INSERT INTO original_call_outcomes
                      (service_shape, response_code, response_shape, count, last_seen)
                      VALUES (?,?,?,?,?)
                      ON CONFLICT(service_shape, response_code, response_shape) DO UPDATE SET
                      count=count+1, last_seen=excluded.last_seen''',
                   (shape, status, result_shape, 1, int(datetime.now(timezone.utc).timestamp())))
        db.execute('''INSERT INTO original_call_request_outcomes
                      (service_shape, response_code, request_shape, response_shape, count, last_seen)
                      VALUES (?,?,?,?,?,?)
                      ON CONFLICT(service_shape, response_code, request_shape, response_shape) DO UPDATE SET
                      count=count+1, last_seen=excluded.last_seen''',
                   (shape, status, request_shape, result_shape, 1, int(datetime.now(timezone.utc).timestamp())))
        if status == 200:
            # A later success resolves an older unsupported-operation marker;
            # leave the current response shape in call_outcomes for debugging.
            db.execute("DELETE FROM missing_requests WHERE method='RPC' AND endpoint_shape=? AND response_status=501",
                       (shape,))


def export_missing(repo: SqliteSaveRepository, target: Path | None = None) -> Path:
    if target is None:
        target = repo.path.parent / 'reports' / ('missing-requests-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.zip')
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    with repo.connect() as db:
        rows = [dict(r) for r in db.execute('SELECT method, endpoint_shape, response_status, count, last_seen FROM missing_requests ORDER BY count DESC LIMIT 2000')]
        calls = [dict(r) for r in db.execute('SELECT service_shape, response_code, request_shape, response_shape, count, last_seen FROM original_call_request_outcomes ORDER BY count DESC LIMIT 2000')]
    data = {'format': 'VillageLifeMissingRequestsV1', 'contains_saves': False,
            'note': 'Aggregated RPC request/response object keys and JSON types only; no request bodies, values, call IDs, session tokens or player identifiers.',
            'records': rows, 'call_outcomes': calls}
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('missing-requests.json', json.dumps(data, indent=2))
    return target


def export_support(target: Path, binding: Path) -> Path:
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    receipt = {'format': 'VillageLifeSupportV1', 'has_instance_binding': binding.is_file(),
               'os_family': os.name, 'no_save_contents': True,
               'warning': 'Read report before sending. A network policy has NOT been verified.'}
    if binding.is_file():
        try:
            data = json.loads(binding.read_text(encoding='utf-8'))
            receipt['instance_id'] = data.get('id')
            receipt['adb_port'] = data.get('adb_port')
            receipt['name_changed_hint'] = 'Compare against BlueStacks Manager if setup fails.'
        except (ValueError, OSError):
            receipt['binding_error'] = 'unreadable'
    with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('diagnostics.json', json.dumps(receipt, indent=2))
    return target
