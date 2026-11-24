"""SQLite-backed transactional saves, independent of the legacy client format.

One BEGIN IMMEDIATE transaction covers all game state and idempotency receipts.
The database is stored OUTSIDE the Git repository, on a local filesystem.
"""
from __future__ import annotations
from contextlib import contextmanager, closing
from pathlib import Path
from typing import Any, Callable, Iterator
import hashlib
import json
import os
import sqlite3
import tempfile
import time
import uuid
import threading
from .history import History, COLLECTIONS, json_default

from villagelife.core.errors import (
    DuplicateActionConflict, InvalidAction, NotFound, RevisionConflict, SaveSchemaError,
)
from villagelife.core.model import VillageSnapshot


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False,
                      default=json_default)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(dumps(value).encode('utf-8')).hexdigest()


SCHEMA = '''
CREATE TABLE IF NOT EXISTS accounts (
  account_id TEXT PRIMARY KEY, created_at INTEGER NOT NULL,
  display_name TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS villages (
  village_id TEXT PRIMARY KEY,
  owner_id TEXT NOT NULL REFERENCES accounts(account_id),
  format TEXT NOT NULL, schema_version INTEGER NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL,
  created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_village_owner ON villages(owner_id);
CREATE TABLE IF NOT EXISTS receipts (
  village_id TEXT NOT NULL REFERENCES villages(village_id),
  operation_key TEXT NOT NULL, request_digest TEXT NOT NULL,
  response_json TEXT NOT NULL, revision INTEGER NOT NULL,
  PRIMARY KEY(village_id, operation_key)
);
CREATE TABLE IF NOT EXISTS legacy_imports (
  legacy_key TEXT PRIMARY KEY,
  profile_digest TEXT NOT NULL, save_digest TEXT NOT NULL,
  account_id TEXT NOT NULL REFERENCES accounts(account_id),
  village_id TEXT NOT NULL REFERENCES villages(village_id),
  imported_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS friendships (
  left_account TEXT NOT NULL REFERENCES accounts(account_id),
  right_account TEXT NOT NULL REFERENCES accounts(account_id),
  created_at INTEGER NOT NULL,
  PRIMARY KEY(left_account, right_account),
  CHECK(left_account < right_account)
);
CREATE TABLE IF NOT EXISTS missing_requests (
  method TEXT NOT NULL, endpoint_shape TEXT NOT NULL, response_status INTEGER NOT NULL,
  count INTEGER NOT NULL, last_seen INTEGER NOT NULL,
  PRIMARY KEY(method, endpoint_shape, response_status)
);
CREATE TABLE IF NOT EXISTS original_call_outcomes (
  service_shape TEXT NOT NULL, response_code INTEGER NOT NULL, response_shape TEXT NOT NULL,
  count INTEGER NOT NULL, last_seen INTEGER NOT NULL,
  PRIMARY KEY(service_shape, response_code, response_shape)
);
CREATE TABLE IF NOT EXISTS original_call_request_outcomes (
  service_shape TEXT NOT NULL, response_code INTEGER NOT NULL,
  request_shape TEXT NOT NULL, response_shape TEXT NOT NULL,
  count INTEGER NOT NULL, last_seen INTEGER NOT NULL,
  PRIMARY KEY(service_shape, response_code, request_shape, response_shape)
);
CREATE TABLE IF NOT EXISTS diagnostic_run_outcomes (
  run_id TEXT NOT NULL, method TEXT NOT NULL, endpoint_shape TEXT NOT NULL,
  response_code INTEGER NOT NULL, request_shape TEXT NOT NULL, response_shape TEXT NOT NULL,
  count INTEGER NOT NULL, last_seen INTEGER NOT NULL,
  PRIMARY KEY(run_id, method, endpoint_shape, response_code, request_shape, response_shape)
);
CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history_collections (
 village_id TEXT NOT NULL REFERENCES villages(village_id), collection TEXT NOT NULL,
 PRIMARY KEY(village_id,collection)
);
CREATE TABLE IF NOT EXISTS action_history (
 village_id TEXT NOT NULL REFERENCES villages(village_id), collection TEXT NOT NULL,
 item_key TEXT NOT NULL, payload_json TEXT NOT NULL,
 PRIMARY KEY(village_id,collection,item_key)
);
CREATE TABLE IF NOT EXISTS due_jobs (
 village_id TEXT NOT NULL REFERENCES villages(village_id), job_id TEXT NOT NULL,
 due_at INTEGER NOT NULL, PRIMARY KEY(village_id,job_id)
);
CREATE INDEX IF NOT EXISTS idx_due_jobs_at ON due_jobs(due_at,village_id);
CREATE TABLE IF NOT EXISTS request_timings (
 run_id TEXT NOT NULL, phase TEXT NOT NULL, count INTEGER NOT NULL,
 total_ms REAL NOT NULL, max_ms REAL NOT NULL, PRIMARY KEY(run_id,phase)
);
'''


class SqliteSaveRepository:
    """Local SQLite implementation of the save repository port.

    Multiple processes coordinate using SQLite's writer lock and a busy timeout.
    No save mutation occurs without an explicit transaction.
    """
    def __init__(self, path: str | Path):
        self.diagnostic_run: str | None = None
        self._local = threading.local()
        self.history_enabled = False
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)
            db.execute('''INSERT OR IGNORE INTO original_call_request_outcomes
                          (service_shape,response_code,request_shape,response_shape,count,last_seen)
                          SELECT service_shape,response_code,'object{}',response_shape,count,last_seen
                          FROM original_call_outcomes''')
            row = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
            if row and row['value'] not in {'1', '2'}:
                raise SaveSchemaError(
                    'This save database uses schema version '+row['value']+', which this '
                    'server cannot read. Open it with the launcher that created it, or '
                    'restore a backup made before the upgrade. Do not open an upgraded '
                    'save with an older server.')
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('schema_version','1')")
            self.history_enabled = db.execute("SELECT 1 FROM metadata WHERE key='history_storage_v1'").fetchone() is not None
            if not db.execute("SELECT 1 FROM metadata WHERE key='due_index_v1'").fetchone():
                db.execute("""INSERT OR IGNORE INTO due_jobs
                    SELECT v.village_id,j.key,json_extract(j.value,'$.dueAt')
                    FROM villages v,json_each(v.payload_json,'$.jobs') j
                    WHERE v.format='native.v1' AND json_extract(j.value,'$.status')='working'
                      AND json_type(j.value,'$.dueAt')='integer'""")
                db.execute("INSERT OR IGNORE INTO metadata VALUES ('due_index_v1','1')")

    def enable_history_storage(self):
        """Make a recovery copy before the first versioned history migration."""
        if self.history_enabled:
            return
        backup = self.path.parent / 'backups' / (self.path.stem + '-before-history-v1-' + uuid.uuid4().hex + '.sqlite3')
        self.backup_to(backup)
        with self.transaction() as db:
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('history_storage_v1','1')")
            # Old launchers must refuse this layout rather than silently ignore
            # archived reward protection. The recovery copy remains version 1.
            db.execute("UPDATE metadata SET value='2' WHERE key='schema_version'")
        self.history_enabled = True

    @contextmanager
    def request_scope(self):
        """Reuse one thread-owned connection, keeping each mutation a FULL commit."""
        if getattr(self._local, 'connection', None) is not None:
            yield
            return
        with self.connect() as db:
            self._local.connection = db
            self._local.latest = {}
            self._local.timings = {}
            try:
                yield
            finally:
                del self._local.connection
                del self._local.latest
                del self._local.timings

    @contextmanager
    def read_snapshot(self):
        """Keep hot rows and lazily loaded history at one export revision."""
        with self.request_scope(), self.connect() as db:
            owned = not db.in_transaction
            if owned:
                db.execute('BEGIN')
            try:
                yield
            finally:
                if owned and db.in_transaction:
                    db.execute('ROLLBACK')

    def observe(self, phase, duration):
        timings = getattr(self._local, 'timings', None)
        if timings is not None:
            count, total, maximum = timings.get(phase, (0, 0.0, 0.0))
            timings[phase] = (count + 1, total + duration, max(maximum, duration))

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        borrowed = getattr(self._local, 'connection', None)
        if borrowed is not None:
            yield borrowed
            return
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=30000')
        db.execute('PRAGMA foreign_keys=ON')
        # WAL commits must reach durable storage before gameplay acknowledges them.
        db.execute('PRAGMA synchronous=FULL')
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as db:
            started = time.perf_counter()
            db.execute('BEGIN IMMEDIATE')
            self.observe('write_lock_wait', (time.perf_counter() - started) * 1000)
            previous = getattr(self._local, 'connection', None)
            self._local.connection = db
            try:
                yield db
                started = time.perf_counter()
                db.execute('COMMIT')
                self.observe('commit', (time.perf_counter() - started) * 1000)
            except BaseException:
                if db.in_transaction:
                    db.execute('ROLLBACK')
                raise
            finally:
                if previous is None:
                    del self._local.connection
                else:
                    self._local.connection = previous

    def create_account(self, name: str = '', account_id: str | None = None) -> str:
        identifier = account_id or str(uuid.uuid4())
        with self.transaction() as db:
            db.execute('INSERT INTO accounts(account_id,created_at,display_name) VALUES (?,?,?)',
                       (identifier, int(time.time()), name))
        return identifier

    def create_village(self, owner_id: str, payload: dict[str, Any], *,
                       format: str = 'native.v1', schema_version: int = 1,
                       village_id: str | None = None) -> str:
        from villagelife.core.validation import validate_json_tree
        validate_json_tree(payload)
        identifier = village_id or str(uuid.uuid4())
        now = int(time.time())
        with self.transaction() as db:
            db.execute('INSERT INTO villages VALUES (?,?,?,?,?,?,?,?)',
                       (identifier, owner_id, format, schema_version, 0,
                        dumps(payload), now, now))
            self._sync_due(db, identifier, payload, format)
        return identifier

    def _payload(self, row):
        started = time.perf_counter()
        payload = json.loads(row['payload_json'])
        self.observe('parse', (time.perf_counter() - started) * 1000)
        normal = (payload.get('originalSave') or {}).get('normal')
        if isinstance(normal, dict):
            with self.connect() as db:
                names = [value[0] for value in db.execute('SELECT collection FROM history_collections WHERE village_id=?',
                                                        (row['village_id'],))]
            for name in names:
                if name not in COLLECTIONS:
                    raise ValueError('Unsupported history collection')
                normal[name] = History(self, row['village_id'], name, normal.get(name, {}))
        return payload

    def _snapshot(self, row: sqlite3.Row) -> VillageSnapshot:
        return VillageSnapshot(
            village_id=row['village_id'], account_id=row['owner_id'],
            format=row['format'], schema_version=row['schema_version'],
            revision=row['revision'], payload=self._payload(row),
        )

    def read_village(self, village_id: str) -> VillageSnapshot:
        with self.connect() as db:
            row = db.execute('SELECT * FROM villages WHERE village_id=?', (village_id,)).fetchone()
        if row is None:
            raise NotFound(f'Unknown village: {village_id}')
        return self._snapshot(row)

    def refresh_snapshot(self, snapshot):
        with self.connect() as db:
            row = db.execute('SELECT revision FROM villages WHERE village_id=?', (snapshot.village_id,)).fetchone()
        if row is None:
            raise NotFound('Village not found')
        if row[0] == snapshot.revision:
            return snapshot
        cached = getattr(self._local, 'latest', {}).get(snapshot.village_id)
        if cached is not None and cached.revision == row[0]:
            return cached
        return self.read_village(snapshot.village_id)

    def list_villages(self, account_id: str) -> list[VillageSnapshot]:
        with self.connect() as db:
            rows = db.execute('SELECT * FROM villages WHERE owner_id=? ORDER BY created_at',
                              (account_id,)).fetchall()
        return [self._snapshot(row) for row in rows]

    def list_all_villages(self) -> list[VillageSnapshot]:
        """Administrative scan for a prototype scheduler; replace with indexed due queue at scale."""
        with self.connect() as db:
            rows = db.execute("SELECT * FROM villages ORDER BY village_id").fetchall()
        return [self._snapshot(row) for row in rows]

    def mutate(self, village_id: str, *, operation_key: str, request: dict[str, Any],
               change: Callable[[dict[str, Any]], dict[str, Any]],
               expected_revision: int | None = None
               ) -> tuple[VillageSnapshot, dict[str, Any], bool]:
        with self.transaction() as db:
            return self._mutate(db, village_id, operation_key, request, change, expected_revision)

    def mutate_group(self, village_id, operations):
        """Commit related operations and their individual replay receipts together."""
        with self.transaction() as db:
            return [self._mutate(db, village_id, key, request, change)
                    for key, request, change in operations]

    def _mutate(self, db, village_id, operation_key, request, change, expected_revision=None):
        if not self.history_enabled:
            self.history_enabled = db.execute("SELECT 1 FROM metadata WHERE key='history_storage_v1'").fetchone() is not None
        if not operation_key or len(operation_key) > 200:
            raise InvalidAction('A bounded operation idempotency key is required')
        from villagelife.core.validation import validate_json_tree
        validate_json_tree(request)
        digest = fingerprint(request)
        row = db.execute('SELECT * FROM villages WHERE village_id=?', (village_id,)).fetchone()
        if row is None:
            raise NotFound(f'Unknown village: {village_id}')
        recorded = db.execute(
            'SELECT * FROM receipts WHERE village_id=? AND operation_key=?',
            (village_id, operation_key),
        ).fetchone()
        if recorded is not None:
            if recorded['request_digest'] != digest:
                raise DuplicateActionConflict('Operation key reused with different inputs')
            return self._snapshot(row), json.loads(recorded['response_json']), True
        if expected_revision is not None and row['revision'] != expected_revision:
            raise RevisionConflict(f'Expected revision {expected_revision}, got {row["revision"]}')
        # Reuse the transaction connection for lazy history lookups as well.
        previous = getattr(self._local, 'connection', None)
        self._local.connection = db
        try:
            updated = self._payload(row)
            response = change(updated)
            stored = dict(updated)
            original = stored.get('originalSave')
            normal = (original or {}).get('normal')
            if self.history_enabled and isinstance(normal, dict):
                stored['originalSave'] = dict(original)
                stored_normal = stored['originalSave']['normal'] = dict(normal)
                for name in COLLECTIONS:
                    values = normal.get(name)
                    if not isinstance(values, (dict, History)):
                        continue
                    history = values if isinstance(values, History) else History(self, village_id, name, values)
                    db.execute('INSERT OR IGNORE INTO history_collections VALUES (?,?)', (village_id, name))
                    stored_normal[name] = history.persist(db, dumps, validate_json_tree)
            started = time.perf_counter()
            validate_json_tree(stored)
            self.observe('validate', (time.perf_counter() - started) * 1000)
            started = time.perf_counter()
            updated_json = dumps(stored)
            self.observe('serialize', (time.perf_counter() - started) * 1000)
            self._sync_due(db, village_id, stored, row['format'])
        finally:
            if previous is None:
                del self._local.connection
            else:
                self._local.connection = previous
        if not isinstance(response, dict):
            raise TypeError('Game operation must return a response object')
        next_revision = row['revision'] + 1
        if updated_json == row['payload_json']:
            # Acknowledge/replay bookkeeping still commits durably, without
            # rewriting all overflow pages of an unchanged large village.
            db.execute('UPDATE villages SET revision=?, updated_at=? WHERE village_id=?',
                       (next_revision, int(time.time()), village_id))
        else:
            db.execute(
                'UPDATE villages SET payload_json=?, revision=?, updated_at=? WHERE village_id=?',
                (updated_json, next_revision, int(time.time()), village_id),
            )
        db.execute('INSERT INTO receipts VALUES (?,?,?,?,?)',
                   (village_id, operation_key, digest, dumps(response), next_revision))
        snapshot = VillageSnapshot(village_id=village_id, account_id=row['owner_id'], format=row['format'],
                                   schema_version=row['schema_version'], revision=next_revision, payload=updated)
        if hasattr(self._local, 'latest'):
            self._local.latest[village_id] = snapshot
        return snapshot, response, False

    @staticmethod
    def _sync_due(db, village, payload, format):
        if format != 'native.v1':
            return
        old = dict(db.execute('SELECT job_id,due_at FROM due_jobs WHERE village_id=?', (village,)))
        current = {key: job['dueAt'] for key, job in payload.get('jobs', {}).items()
                   if job.get('status') == 'working' and type(job.get('dueAt')) is int}
        for key in old.keys() - current.keys():
            db.execute('DELETE FROM due_jobs WHERE village_id=? AND job_id=?', (village, key))
        for key, due in current.items():
            if old.get(key) != due:
                db.execute('INSERT INTO due_jobs VALUES (?,?,?) ON CONFLICT(village_id,job_id) '
                           'DO UPDATE SET due_at=excluded.due_at', (village, key, due))

    def due_villages(self, now):
        with self.connect() as db:
            return [row[0] for row in db.execute('SELECT DISTINCT village_id FROM due_jobs WHERE due_at<=?', (now,))]

    def checkpoint(self) -> None:
        """Checkpoint active WAL before producing a file-level backup."""
        with self.connect() as db:
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')

    def backup_to(self, path: str | Path) -> None:
        """Make a consistent SQLite backup (never copy a live WAL database)."""
        target = Path(path).expanduser().resolve()
        if target == self.path:
            raise ValueError('Backup path must differ from active database')
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f'Backup already exists: {target}')
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.backup-', suffix='.pending',
                                         delete=False) as file:
            pending = Path(file.name)
        try:
            with self.connect() as src, closing(sqlite3.connect(pending)) as dst:
                dst.execute('PRAGMA synchronous=FULL')
                src.backup(dst)
                dst.execute('PRAGMA journal_mode=DELETE')
                if dst.execute('PRAGMA quick_check').fetchone() != ('ok',):
                    raise sqlite3.DatabaseError('Backup did not pass its integrity check')
            with pending.open('r+b') as file:
                os.fsync(file.fileno())
            if os.name == 'nt':
                pending.rename(target)  # Windows rename fails if the target exists.
            else:
                os.link(pending, target)
        finally:
            pending.unlink(missing_ok=True)
