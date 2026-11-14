"""Read authored client definitions from a user-provided extraction.

This module never ships or modifies the original database. All connections
are read-only and are closed before returning, including on Windows.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import json
import sqlite3
from contextlib import closing

class OriginalDefinitions:
    def __init__(self, db_path: Path):
        self.path = Path(db_path).resolve(strict=True)
        if not self.path.is_file():
            raise FileNotFoundError('Original game tables database not found')

    @lru_cache(maxsize=160)
    def _cached(self, table: str) -> tuple[str,...]:
        if not table or len(table)>120:
            raise ValueError('Invalid table name')
        with closing(sqlite3.connect(f'file:{self.path.as_posix()}?mode=ro', uri=True)) as connection:
            return tuple(r[0] for r in connection.execute(
                'SELECT r.fields_json FROM game_rows r JOIN game_tables t ON t.id=r.table_id '
                'WHERE t.name=? ORDER BY r.ordinal', (table,)))

    def rows(self, table: str) -> list[dict]:
        return [json.loads(s) for s in self._cached(table)]

    @lru_cache(maxsize=160)
    def _indexed(self, table: str) -> dict[str, str]:
        index = {}
        for row in self.rows(table):
            index.setdefault(str(row.get('id')), json.dumps(row))
        return index

    def item(self, table: str, key: str | int) -> dict:
        serialized = self._indexed(table).get(str(key))
        return json.loads(serialized) if serialized is not None else self._missing(table,key)

    @staticmethod
    def _missing(table, key):
        raise KeyError(f'Missing original definition {table}/{key}')

    def scenario_for_area(self, area_id: int) -> tuple[dict,dict]:
        area=self.item('area',area_id)
        return area,self.item('scenario',area['scenario'])
