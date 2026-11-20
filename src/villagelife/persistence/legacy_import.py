"""Non-destructive import of legacy profile + tutorial save pairs (including 2.11).

Original files are NEVER renamed, moved, rewritten or deleted. The imported
payload is tagged opaque and cannot accidentally be simulated as native.v1.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re
import time
import uuid
from villagelife.persistence.sqlite_store import SqliteSaveRepository, dumps
from villagelife.core.limits import bounded_read, checked_json, MAX_SAVE_BYTES, MAX_PROFILE_BYTES


PROFILE_PATTERN = re.compile(r'^[0-9a-f]{64}\.json$')


@dataclass(frozen=True)
class ImportResult:
    source: str
    status: str
    has_save: bool
    account_id: str | None = None
    village_id: str | None = None


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class LegacySaveImporter:
    def __init__(self, repository: SqliteSaveRepository):
        self.repository = repository

    def import_directory(self, source_dir: str | Path, *, apply: bool = False) -> list[ImportResult]:
        root = Path(source_dir).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError('Expected a directory of legacy private_state files')
        results = []
        for profile_path in sorted(root.iterdir()):
            if profile_path.is_symlink() or not profile_path.is_file() or not PROFILE_PATTERN.fullmatch(profile_path.name):
                continue
            legacy_key = profile_path.stem
            save_path = profile_path.with_suffix('.tutorial.json')
            if save_path.exists() and save_path.is_symlink():
                raise ValueError('Save file symlink not permitted')
            profile_raw = bounded_read(profile_path, MAX_PROFILE_BYTES)
            save_raw = bounded_read(save_path, MAX_SAVE_BYTES) if save_path.is_file() else b''
            profile = checked_json(profile_raw)
            saved = checked_json(save_raw) if save_raw else None
            if not isinstance(profile, dict) or (saved is not None and not isinstance(saved, dict)):
                raise ValueError(f'Invalid legacy record: {profile_path.name}')
            result = self._import_record(legacy_key, profile, saved, digest(profile_raw),
                                         digest(save_raw), bool(save_raw), apply)
            results.append(result)
        return results

    def _import_record(self, key: str, profile: dict, saved: dict | None,
                       profile_hash: str, save_hash: str, has_save: bool,
                       apply: bool, *, launch_copy: dict | None = None) -> ImportResult:
        access = self.repository.transaction if apply else self.repository.connect
        with access() as db:
            prior = db.execute('SELECT * FROM legacy_imports WHERE legacy_key=?', (key,)).fetchone()
            if prior:
                status = ('CONFLICT: changed since prior import; no overwrite'
                          if prior['profile_digest'] != profile_hash or prior['save_digest'] != save_hash
                          else 'already-imported')
                return ImportResult(key, status, has_save, prior['account_id'], prior['village_id'])
            if not apply:
                return ImportResult(key, 'ready-to-import (dry run)', has_save)

            account_id, village_id = str(uuid.uuid4()), str(uuid.uuid4())
            now = int(time.time())
            payload = {'originalProfile': profile, 'originalSave': saved,
                       'sourceFormat': 'legacy-profile+tutorial'}
            db.execute('INSERT INTO accounts VALUES (?,?,?)',
                       (account_id, now, str(profile.get('displayName', ''))[:100]))
            db.execute('INSERT INTO villages VALUES (?,?,?,?,?,?,?,?)',
                       (village_id, account_id, 'legacy.profile+tutorial.v1',
                        int(saved.get('version', 0)) if saved else 0,
                        0, dumps(payload), now, now))
            db.execute('INSERT INTO legacy_imports VALUES (?,?,?,?,?,?)',
                       (key, profile_hash, save_hash, account_id, village_id, now))
            if launch_copy is not None:
                db.execute("INSERT INTO metadata VALUES ('legacy_launch_copy', ?)", (dumps(launch_copy),))
        return ImportResult(key, 'imported (original untouched)', has_save, account_id, village_id)
