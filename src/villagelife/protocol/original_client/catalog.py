"""Read authored client definitions from a user-provided extraction.

This module never ships or modifies the original database. All connections
are read-only and are closed before returning, including on Windows.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import json
import sqlite3
import copy
from contextlib import closing


def matching(definitions, table, field, value):
    if hasattr(definitions, 'matching'):
        return definitions.matching(table, field, value)
    return [row for row in definitions.rows(table) if str(row.get(field)) == str(value)]

class OriginalDefinitions:
    def __init__(self, db_path: Path):
        self.path = Path(db_path).resolve(strict=True)
        if not self.path.is_file():
            raise FileNotFoundError('Original game tables database not found')

    @lru_cache(maxsize=160)
    def _cached(self, table: str) -> tuple[dict,...]:
        if not table or len(table)>120:
            raise ValueError('Invalid table name')
        with closing(sqlite3.connect(f'file:{self.path.as_posix()}?mode=ro', uri=True)) as connection:
            return tuple(json.loads(r[0]) for r in connection.execute(
                'SELECT r.fields_json FROM game_rows r JOIN game_tables t ON t.id=r.table_id '
                'WHERE t.name=? ORDER BY r.ordinal', (table,)))

    def rows(self, table: str) -> list[dict]:
        return [self._copy(row) for row in self._cached(table)]

    @staticmethod
    def _copy(row):
        return {key: copy.deepcopy(value) if isinstance(value, (dict, list)) else value
                for key, value in row.items()}

    @lru_cache(maxsize=160)
    def _indexed(self, table: str) -> dict[str, dict]:
        index = {}
        for row in self.rows(table):
            index.setdefault(str(row.get('id')), row)
        return index

    def item(self, table: str, key: str | int) -> dict:
        row = self._indexed(table).get(str(key))
        return self._copy(row) if row is not None else self._missing(table,key)

    @lru_cache(maxsize=160)
    def _groups(self, table, field):
        groups = {}
        for row in self.rows(table):
            groups.setdefault(str(row.get(field)), []).append(row)
        return groups

    def matching(self, table, field, value):
        return [self._copy(row) for row in self._groups(table, field).get(str(value), ())]

    @staticmethod
    def _missing(table, key):
        raise KeyError(f'Missing original definition {table}/{key}')

    def scenario_for_area(self, area_id: int) -> tuple[dict,dict]:
        area=self.item('area',area_id)
        return area,self.item('scenario',area['scenario'])
