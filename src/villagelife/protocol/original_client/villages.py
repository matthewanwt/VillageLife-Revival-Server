"""Launcher-facing lifecycle for independent original-client villages.

A new village is stored with an uninitialized ``originalSave``. The existing
first-login path in :class:`OriginalClientGame` fills it with
``TutorialRules.fresh()``, so the launcher never duplicates tutorial or world
initialization logic. Each village receives its own account and device
identity, which keeps later migrations and progress independent.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import re
import secrets
import time
import uuid

from villagelife.core.errors import InvalidAction, NotFound, SaveBackupError
from villagelife.persistence.portable import PortableSaves
from villagelife.persistence.sqlite_store import SqliteSaveRepository, dumps
from villagelife.protocol.original_client.sessions import SESSION_SCHEMA

_IMPORTED_KEY = re.compile(r'[0-9a-f]{64}')


def _ensure_device_schema(repo: SqliteSaveRepository) -> None:
    with repo.connect() as db:
        db.executescript(SESSION_SCHEMA)


def _bind_device(db, account_id: str, village_id: str) -> None:
    """Give a village a local device identity so --local-village-id can open it."""
    now = int(time.time())
    for _ in range(20):
        try:
            db.execute('INSERT INTO original_client_devices VALUES (?,?,?,?,?,?)',
                       (hashlib.sha256(uuid.uuid4().bytes).hexdigest(), account_id,
                        village_id, str(secrets.randbelow(2**48 - 1) + 1),
                        secrets.token_hex(16), now))
            return
        except Exception as exc:  # numeric player IDs are unique across villages
            if 'UNIQUE constraint failed' not in str(exc):
                raise
    raise InvalidAction('Could not allocate a local player identity for the village.')


def create_local_village(repo: SqliteSaveRepository) -> dict:
    """Create a new independent village; its tutorial starts on first login."""
    _ensure_device_schema(repo)
    village_id, account_id = str(uuid.uuid4()), str(uuid.uuid4())
    now = int(time.time())
    payload = {'originalProfile': {}, 'originalSave': None,
               'sourceFormat': 'original.client.v1'}
    with repo.transaction() as db:
        db.execute('INSERT INTO accounts VALUES (?,?,?)', (account_id, now, ''))
        db.execute('INSERT INTO villages VALUES (?,?,?,?,?,?,?,?)',
                   (village_id, account_id, 'original.client.v1', 1, 0,
                    dumps(payload), now, now))
        _bind_device(db, account_id, village_id)
    return {'village_id': village_id, 'account_id': account_id,
            'name': 'New village ' + village_id[:8], 'stage': 'tutorial'}


def list_local_villages(repo: SqliteSaveRepository) -> list[dict]:
    """List local villages, including ones whose tutorial has not started."""
    with repo.connect() as db:
        rows = db.execute("""
            SELECT village_id,
                   COALESCE(json_extract(payload_json,
                       '$.originalSave.normal.user.name'), 'New village') AS name,
                   COALESCE(json_extract(payload_json,
                       '$.originalSave.normal.user.userLevelID'), 0) AS level,
                   COALESCE(json_extract(payload_json,
                       '$.originalSave.normal.inventory."323"'), 0) AS gems,
                   CASE WHEN json_type(payload_json,
                       '$.originalSave.normal') = 'object'
                        THEN 'woodland' ELSE 'tutorial' END AS stage,
                   created_at, updated_at AS last_saved
            FROM villages
            WHERE json_type(payload_json, '$.originalSave') IN ('object', 'null')
            ORDER BY updated_at DESC, village_id
        """).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        if item['stage'] == 'tutorial' and item['name'] == 'New village':
            item['name'] = 'New village ' + item['village_id'][:8]
        result.append(item)
    return result


def _export_before_delete(repo: SqliteSaveRepository, village_id: str,
                          backup: str | Path | None) -> str | None:
    if backup is None:
        return None
    target = Path(backup).expanduser().resolve()
    if target.exists():
        raise SaveBackupError('A recovery copy already exists at that path. '
                              'Choose another name or keep the existing copy.')
    try:
        PortableSaves(repo).export(village_id, target)
    except Exception as exc:
        raise SaveBackupError(
            'Could not create the recovery copy. The village was not deleted. '
            'Free disk space and check folder permissions, then retry.') from exc
    return str(target)


def delete_local_village(repo: SqliteSaveRepository, village_id: str, *,
                         backup: str | Path | None = None) -> dict:
    repo.read_village(village_id)  # validate before creating a backup
    backup_path = _export_before_delete(repo, village_id, backup)
    removed = repo.delete_village(village_id)
    removed['backup'] = backup_path
    return removed


def delete_imported_village(repo: SqliteSaveRepository, key: str, *,
                            storage: str | Path | None = None,
                            backup: str | Path | None = None) -> dict:
    """Delete one imported 0.2.6 copy, never its original source folder."""
    if not _IMPORTED_KEY.fullmatch(key):
        raise InvalidAction('Choose an imported village from the list.')
    folder = (Path(storage).expanduser().resolve() if storage
              else repo.path.parent / 'imported-villages')
    path = folder / (key + '.sqlite3')
    if not path.is_file():
        raise NotFound('The selected imported village is missing.')
    village_id = None
    backup_path = None
    if backup is not None:
        imported = SqliteSaveRepository(path)
        villages = imported.list_all_villages()
        if not villages:
            raise InvalidAction('The selected imported village is empty.')
        village_id = villages[0].village_id
        backup_path = _export_before_delete(imported, village_id, backup)
    # Windows requires every SQLite handle to be closed before removal.
    for suffix in ('', '-wal', '-shm'):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()
    return {'key': key, 'village_id': village_id, 'backup': backup_path}


def restore_portable_village(repo: SqliteSaveRepository,
                             archive: str | Path) -> dict:
    """Import a recovery archive as a new, independently selectable village."""
    _ensure_device_schema(repo)
    account_id = repo.create_account('Restored village')
    village_id = PortableSaves(repo).import_as_new(archive, account_id)
    with repo.transaction() as db:
        _bind_device(db, account_id, village_id)
    return {'village_id': village_id, 'account_id': account_id}
