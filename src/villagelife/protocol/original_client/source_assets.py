"""Derive runtime tables and resource offsets from a player's local expansion."""
from __future__ import annotations

from contextlib import closing
import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import xml.etree.ElementTree as ET

ENGLISH_TABLES = {f'files/xml/{group}{index}_en.xml'
                  for group, indexes in (('newxmlloc', (1, 2, 3)), ('newxmlsam', (0, 1, 2)))
                  for index in indexes}
REQUIRED_TABLES = {'global', 'villager_type', 'material_type', 'scenario', 'seq_state_tablet_ftue'}
MAX_XML = 64_000_000


def _read_exact(stream, size):
    data = stream.read(size)
    if len(data) != size:
        raise ValueError('Truncated original game expansion')
    return data


def _expansion_entries(stream, size):
    magic, count, name_bytes, data_bytes = struct.unpack('<4sIII', _read_exact(stream, 16))
    if magic != b'TCF1' or not 0 < count <= 200_000 or not 0 < name_bytes <= 32_000_000:
        raise ValueError('Unsupported original game expansion index')
    base = 16 + 16 * count + name_bytes
    if base + data_bytes != size:
        raise ValueError('Original game expansion size does not match its index')
    records = _read_exact(stream, 16 * count)
    names = _read_exact(stream, name_bytes)
    entries = {}
    for start, offset, length, _ in struct.iter_unpack('<4I', records):
        end = names.find(b'\0', start)
        if end == -1 or offset + length > data_bytes:
            raise ValueError('Invalid original game expansion entry')
        path = names[start:end].decode('utf-8')
        if not path.startswith('files/') or '..' in path.split('/') or '\\' in path or path in entries:
            raise ValueError('Invalid or duplicate original resource name')
        entries[path] = base + offset, length
    return entries


def _unpack_xml(raw):
    if len(raw) < 9 or raw[:4] != b'SPK1':
        raise ValueError('Unsupported original game table compression')
    expected, = struct.unpack_from('<I', raw, 4)
    if not 0 < expected <= MAX_XML:
        raise ValueError('Original game table exceeds the supported size')
    source = memoryview(raw)[8:]
    pos = 0
    out = bytearray()
    while pos < len(source):
        control = source[pos]
        pos += 1
        if control == 0:
            if len(out) != expected:
                raise ValueError('Original game table length mismatch')
            return bytes(out)
        mode = control >> 6
        if mode == 0:
            if pos + control > len(source) or len(out) + control > expected:
                raise ValueError('Invalid game table literal')
            out.extend(source[pos:pos + control])
            pos += control
            continue
        if pos + mode > len(source):
            raise ValueError('Truncated game table copy instruction')
        first = source[pos]
        if mode == 1:
            back = ((control & 3) << 8) + first + 1
            length = ((control >> 2) & 15) + 3
        elif mode == 2:
            back = ((first & 63) << 8) + source[pos + 1] + 1
            length = ((control & 63) << 2) + (first >> 6) + 4
        else:
            back = ((first & 1) << 16) + (source[pos + 1] << 8) + source[pos + 2] + 1
            length = ((control & 63) << 7) + (first >> 1) + 5
        pos += mode
        if back > len(out) or len(out) + length > expected:
            raise ValueError('Invalid game table copy range')
        # Overlapping references repeat the already decoded suffix.
        start = len(out) - back
        chunk = bytes(out[start:start + min(back, length)])
        times, remainder = divmod(length, len(chunk))
        out.extend(chunk * times + chunk[:remainder])
    raise ValueError('Missing game table end marker')


def _fields(row):
    result = {}
    for field in row:
        value = ET.tostring(field, encoding='unicode') if len(field) or field.attrib else (field.text or '')
        if field.tag not in result:
            result[field.tag] = value
        elif isinstance(result[field.tag], list):
            result[field.tag].append(value)
        else:
            result[field.tag] = [result[field.tag], value]
    return json.dumps(result, ensure_ascii=True)


def _write_tables(stream, entries, destination):
    with closing(sqlite3.connect(destination)) as db, db:
        db.executescript("""
            CREATE TABLE source_files(id INTEGER PRIMARY KEY,path TEXT UNIQUE,sha256 TEXT);
            CREATE TABLE game_tables(id INTEGER PRIMARY KEY,source_id INTEGER,name TEXT,declared_rows INTEGER,actual_rows INTEGER);
            CREATE TABLE game_rows(table_id INTEGER,ordinal INTEGER,row_id TEXT,fields_json TEXT,PRIMARY KEY(table_id,ordinal));
            CREATE INDEX table_name ON game_tables(name);
            CREATE INDEX row_key ON game_rows(table_id,row_id);
        """)
        found = set()
        for path in sorted(ENGLISH_TABLES):
            offset, size = entries[path]
            if size > MAX_XML:
                raise ValueError('Packed game table exceeds the supported size')
            stream.seek(offset)
            decoded = _unpack_xml(_read_exact(stream, size))
            root = ET.fromstring(decoded.rstrip(b'\0'))
            source_id = db.execute('INSERT INTO source_files(path,sha256) VALUES (?,?)',
                                   (Path(path).name, hashlib.sha256(decoded).hexdigest())).lastrowid
            for table in root.iter('table'):
                name = table.attrib['name']
                rows = table.findall('./rows/row')
                declared = int(table.attrib['numrows'])
                if len(rows) != declared:
                    raise ValueError('Original game table row count mismatch')
                found.add(name)
                table_id = db.execute('INSERT INTO game_tables(source_id,name,declared_rows,actual_rows) VALUES (?,?,?,?)',
                                      (source_id, name, declared, len(rows))).lastrowid
                db.executemany('INSERT INTO game_rows VALUES (?,?,?,?)',
                               ((table_id, i, row.findtext('id'), _fields(row)) for i, row in enumerate(rows)))
        if not REQUIRED_TABLES <= found:
            raise ValueError('Original game tables are incomplete')


def derive_runtime_assets(obb: Path, output: Path) -> None:
    tables = output / 'game_tables.sqlite'
    inventory = output / 'obb_tcf.inventory.csv'
    temporary_tables = tables.with_suffix('.incomplete')
    temporary_inventory = inventory.with_suffix('.incomplete')
    temporary_tables.unlink(missing_ok=True)
    try:
        with obb.open('rb') as stream:
            entries = _expansion_entries(stream, obb.stat().st_size)
            if not ENGLISH_TABLES <= entries.keys():
                raise ValueError('This expansion is missing the supported English game tables')
            _write_tables(stream, entries, temporary_tables)
        with temporary_inventory.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(('path', 'offset_in_tcf', 'stored_bytes'))
            writer.writerows((path, *span) for path, span in entries.items())
        temporary_tables.replace(tables)
        temporary_inventory.replace(inventory)
    finally:
        temporary_tables.unlink(missing_ok=True)
        temporary_inventory.unlink(missing_ok=True)

