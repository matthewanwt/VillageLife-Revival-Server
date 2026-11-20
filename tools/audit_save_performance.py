"""Read-only, value-free save size and serialization audit. No game assets needed."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import statistics
import time


def audit(path: Path) -> dict:
    path = path.expanduser().resolve(strict=True)
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')  # One coherent view even if gameplay is saving.
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        report = {
            'format': 'VillageLifeSavePerformanceV1',
            'database_bytes': path.stat().st_size,
            'wal_bytes': Path(str(path) + '-wal').stat().st_size if Path(str(path) + '-wal').exists() else 0,
            'page_bytes': db.execute('PRAGMA page_size').fetchone()[0],
            'free_pages': db.execute('PRAGMA freelist_count').fetchone()[0],
            'tables': {}, 'villages': [],
        }
        for name in ('villages', 'receipts', 'original_client_devices', 'diagnostic_run_outcomes'):
            if name in tables:
                report['tables'][name] = {'rows': db.execute('SELECT count(*) FROM ' + name).fetchone()[0]}
        if 'receipts' in tables:
            report['tables']['receipts']['response_bytes'] = db.execute(
                'SELECT coalesce(sum(length(CAST(response_json AS BLOB))),0) FROM receipts').fetchone()[0]
        if 'action_history' in tables:
            count, stored = db.execute('SELECT count(*),coalesce(sum(length(CAST(payload_json AS BLOB))),0) FROM action_history').fetchone()
            report['archived_history'] = {'records': count, 'stored_bytes': stored}
        # Never export village IDs, names, device hashes, or actual save content.
        for (raw,) in db.execute('SELECT payload_json FROM villages ORDER BY length(payload_json) DESC'):
            parse_ms, encode_ms = [], []
            for _ in range(3):
                started = time.perf_counter()
                payload = json.loads(raw)
                parse_ms.append((time.perf_counter() - started) * 1000)
                started = time.perf_counter()
                json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
                encode_ms.append((time.perf_counter() - started) * 1000)
            save = payload.get('originalSave') or {}
            normal = save.get('normal') or {}
            sections = []
            # Fixed allowlist avoids exporting unknown/user-controlled field names.
            for name in ('world', 'workAreas', 'consumptionReceipts', 'directConsumptionReceipts',
                         'completedQuests', 'habitatReceipts', 'funReceipts', 'wants', 'inventory'):
                value = normal.get(name)
                if value is not None:
                    sections.append({'section': name, 'json_bytes': len(json.dumps(value, separators=(',', ':'),
                        ensure_ascii=False).encode('utf-8')), 'entries': len(value) if isinstance(value, (dict, list)) else None})
            report['villages'].append({'payload_bytes': len(raw.encode('utf-8')),
                'parse_ms_median': round(statistics.median(parse_ms), 3),
                'encode_ms_median': round(statistics.median(encode_ms), 3),
                'sections': sorted(sections, key=lambda row: row['json_bytes'], reverse=True)})
        return report
    finally:
        db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.database), indent=2))
