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
import sqlite3
import time
import uuid

from villagelife.core.errors import (
    DuplicateActionConflict, InvalidAction, NotFound, RevisionConflict,
)
from villagelife.core.model import VillageSnapshot


def dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


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
CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY, value TEXT NOT NULL
);
'''


class SqliteSaveRepository:
    """Local SQLite implementation of the save repository port.

    Multiple processes coordinate using SQLite's writer lock and a busy timeout.
    No save mutation occurs without an explicit transaction.
    """
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)
            row = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
            if row and row['value'] != '1':
                raise RuntimeError('Unsupported database schema version: '+row['value'])
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('schema_version','1')")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=30000')
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise

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
        return identifier

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> VillageSnapshot:
        return VillageSnapshot(
            village_id=row['village_id'], account_id=row['owner_id'],
            format=row['format'], schema_version=row['schema_version'],
            revision=row['revision'], payload=json.loads(row['payload_json']),
        )

    def read_village(self, village_id: str) -> VillageSnapshot:
        with self.connect() as db:
            row = db.execute('SELECT * FROM villages WHERE village_id=?', (village_id,)).fetchone()
        if row is None:
            raise NotFound(f'Unknown village: {village_id}')
        return self._snapshot(row)

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
        if not operation_key or len(operation_key) > 200:
            raise InvalidAction('A bounded operation idempotency key is required')
        from villagelife.core.validation import validate_json_tree
        validate_json_tree(request)
        digest = fingerprint(request)
        with self.transaction() as db:
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
            updated = json.loads(row['payload_json'])
            response = change(updated)
            if not isinstance(response, dict):
                raise TypeError('Game operation must return a response object')
            validate_json_tree(updated)
            updated_json = dumps(updated)  # Validates JSON and finite numbers before commit.
            next_revision = row['revision'] + 1
            db.execute(
                'UPDATE villages SET payload_json=?, revision=?, updated_at=? WHERE village_id=?',
                (updated_json, next_revision, int(time.time()), village_id),
            )
            db.execute('INSERT INTO receipts VALUES (?,?,?,?,?)',
                       (village_id, operation_key, digest, dumps(response), next_revision))
            new_row = db.execute('SELECT * FROM villages WHERE village_id=?', (village_id,)).fetchone()
            return self._snapshot(new_row), response, False

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
        already_existed = target.exists()
        if already_existed:
            raise FileExistsError(f'Backup already exists: {target}')
        try:
            with self.connect() as src, closing(sqlite3.connect(target)) as dst:
                src.backup(dst)
        except BaseException:
            # A partial backup must never look like a successful new save.
            if not already_existed:
                target.unlink(missing_ok=True)
            raise
