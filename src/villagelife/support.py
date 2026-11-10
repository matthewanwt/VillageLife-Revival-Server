"""Privacy-minimised diagnostics: no request bodies, save contents or identifiers."""
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
    return '/unrecognised/' + str(min(10, len([p for p in path.split('/') if p])))


def record_missing(repo: SqliteSaveRepository, method: str, path: str, status: int) -> None:
    if method not in ('GET', 'POST', 'PUT', 'DELETE', 'PATCH') or status not in (404, 501):
        return
    shape = endpoint_shape(path)
    with repo.transaction() as db:
        db.execute('''INSERT INTO missing_requests (method, endpoint_shape, response_status, count, last_seen)
                      VALUES (?,?,?,?,?)
                      ON CONFLICT(method, endpoint_shape, response_status) DO UPDATE SET
                      count=count+1, last_seen=excluded.last_seen''',
                   (method, shape, status, 1, int(datetime.now(timezone.utc).timestamp())))


def export_missing(repo: SqliteSaveRepository, target: Path | None = None) -> Path:
    if target is None:
        target = repo.path.parent / 'reports' / ('missing-requests-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.zip')
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    with repo.connect() as db:
        rows = [dict(r) for r in db.execute('SELECT method, endpoint_shape, response_status, count, last_seen FROM missing_requests ORDER BY count DESC LIMIT 2000')]
    data = {'format': 'VillageLifeMissingRequestsV1', 'contains_saves': False,
            'note': 'Unknown operation names inside binary client requests are not decoded yet.',
            'records': rows}
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
