"""Read original extracted game-data tables without importing them into Git.

Tables provide data, not automatic proof that a game rule behaves as assumed.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
import re
import sqlite3
from typing import Any
from urllib.parse import quote
from villagelife.core.errors import NotFound

_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z_0-9]*$')


class OriginalGameCatalog:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve(strict=True)
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        with self.connect() as db:
            self.tables = frozenset(row['name'] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))

    def connect(self) -> sqlite3.Connection:
        uri = 'file:'+quote(str(self.path), safe='/')+'?mode=ro&immutable=1'
        db = sqlite3.connect(uri, uri=True)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        return db

    def _table(self, table: str) -> str:
        if not _IDENTIFIER.fullmatch(table) or table not in self.tables:
            raise NotFound(f'Unknown source table: {table}')
        return table

    def rows(self, table: str, limit: int = 100_000) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100_000:
            raise ValueError('Invalid row limit')
        with self.connect() as db:
            result = db.execute(f'SELECT * FROM "{self._table(table)}" LIMIT ?', (limit,)).fetchall()
        return [dict(row) for row in result]

    def row_by_id(self, table: str, identifier: Any) -> dict[str, Any]:
        with self.connect() as db:
            table = self._table(table)
            column_names = {r['name'] for r in db.execute(f'PRAGMA table_info("{table}")')}
            if 'id' not in column_names:
                raise NotFound(f'Table lacks id column: {table}')
            value = db.execute(f'SELECT * FROM "{table}" WHERE id=? LIMIT 1',
                               (identifier,)).fetchone()
        if value is None:
            raise NotFound(f'Unknown original {table} ID: {identifier}')
        return dict(value)

    def file_sha256(self) -> str:
        digest = hashlib.sha256()
        with self.path.open('rb') as fh:
            for block in iter(lambda: fh.read(1024*1024), b''):
                digest.update(block)
        return digest.hexdigest()
