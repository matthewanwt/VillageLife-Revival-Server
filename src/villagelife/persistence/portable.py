"""Portable save export/import with checksums and explicit ownership decisions.

Export files contain private game data; they must NEVER be committed to Git.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
import hashlib
import json
import os
import zipfile
from villagelife.core.errors import InvalidAction
from villagelife.persistence.sqlite_store import SqliteSaveRepository, dumps
from villagelife.core.limits import MAX_SAVE_BYTES, checked_json


class PortableSaves:
    def __init__(self, repository: SqliteSaveRepository):
        self.repository = repository

    def export(self, village_id: str, output: str | Path) -> Path:
        with self.repository.read_snapshot():
            snapshot = self.repository.read_village(village_id)
            data = dumps({
                'format': snapshot.format,
                'schemaVersion': snapshot.schema_version,
                'revision': snapshot.revision,
                'payload': snapshot.payload,
            }).encode('utf-8')
        if len(data) > MAX_SAVE_BYTES:
            raise InvalidAction('Village history exceeds the portable JSON limit. Use a whole-database backup instead.')
        manifest = {
            'archiveVersion': 1,
            'sha256': hashlib.sha256(data).hexdigest(),
            'saveFile': 'village.json',
            'contents': 'Private gameplay data; do not publish',
        }
        target = Path(output).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise FileExistsError(f'Refusing to replace existing export: {target}')
        temporary = target.with_name(target.name+'.writing')
        try:
            with zipfile.ZipFile(temporary, 'x', compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr('manifest.json', dumps(manifest))
                zf.writestr('village.json', data)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def import_as_new(self, archive: str | Path, owner_id: str) -> str:
        """Never silently overwrite an existing online village.

        Caller must explicitly choose an owning account, which can be a newly
        created account for an offline import. Multi-device sync is NOT implied.
        """
        with zipfile.ZipFile(archive) as zf:
            if sorted(zf.namelist()) != ['manifest.json', 'village.json']:
                raise InvalidAction('Unexpected save archive contents')
            info = zf.getinfo('village.json')
            if zf.getinfo('manifest.json').file_size > 128 * 1024:
                raise InvalidAction('Save manifest exceeds supported size')
            if info.file_size > MAX_SAVE_BYTES:
                raise InvalidAction('Save exceeds supported size')
            meta = json.loads(zf.read('manifest.json'))
            raw = zf.read('village.json')
            if not isinstance(meta, dict) or meta.get('archiveVersion') != 1 or hashlib.sha256(raw).hexdigest() != meta.get('sha256'):
                raise InvalidAction('Save checksum or archive format invalid')
            item = checked_json(raw)
        if (not isinstance(item, dict) or not isinstance(item.get('payload'), dict)
                or type(item.get('schemaVersion')) is not int or not isinstance(item.get('format'), str)):
            raise InvalidAction('Invalid portable save')
        return self.repository.create_village(owner_id, item['payload'],
                        format=item['format'], schema_version=item['schemaVersion'])
