"""Copy a 0.2.6 village into a dedicated database for the Windows launcher."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import json
import re
import sqlite3

from villagelife.core.errors import InvalidAction
from villagelife.core.validation import validate_json_tree
from .legacy_import import LegacySaveImporter, PROFILE_PATTERN, digest
from .sqlite_store import SqliteSaveRepository

# Active 0.2.6 villages retain gameplay history in the save JSON.
MAX_SAVE_BYTES = 128 * 1024 * 1024
MAX_PROFILE_BYTES = 1024 * 1024
SLOT_KEY = re.compile(r'[0-9a-f]{64}')
INSTANCE_ID = re.compile(r'Pie64(?:_\d+)?')


def _read(path: Path, *, limit: int = MAX_PROFILE_BYTES) -> bytes:
    if path.is_symlink():
        raise ValueError('Symbolic links are unsupported for legacy save files.')
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f'File exceeds the {limit // (1024 * 1024)} MiB import limit.')
    return data


def _legacy_folder(folder: Path) -> tuple[Path, str]:
    folder = folder.resolve(strict=True)
    root = folder / 'backend' / 'private_state'
    if not root.is_dir():
        backup = folder / 'private_state'
        root = backup if backup.is_dir() else folder
    if root.parent.name == 'backend':
        install = root.parent.parent
    else:
        install = root.parent if root.name == 'private_state' else folder
    settings = install / 'play-settings.json'
    instance = ''
    if settings.is_file():
        try:
            candidate = json.loads(_read(settings)).get('instance', '')
            if isinstance(candidate, str) and INSTANCE_ID.fullmatch(candidate):
                instance = candidate
        except (ValueError, AttributeError):
            pass
    return root, instance


def _summary(saved: dict) -> dict:
    user_hash = saved.get('userHash')
    if saved.get('version') != 1 or not isinstance(user_hash, dict):
        raise ValueError('Unsupported 0.2.6 save structure.')
    tutorial = user_hash.get('data')
    if not isinstance(tutorial, dict) or not isinstance(tutorial.get('villagers'), list):
        raise ValueError('The tutorial villager records are missing.')
    world = saved.get('normal')
    if world is None:
        return {'name': 'Tutorial village', 'level': 0, 'gems': None,
                'villagers': len(tutorial['villagers'])}
    if not isinstance(world, dict) or world.get('schemaVersion') not in (2, 3):
        raise ValueError('Unsupported 0.2.6 village structure.')
    user, inventory, scene = (world.get(key) for key in ('user', 'inventory', 'world'))
    if not all(isinstance(section, dict) for section in (user, inventory, scene)):
        raise ValueError('Village progress, inventory or scene is missing.')
    entities = scene.get('entities')
    if not isinstance(entities, list) or any(not isinstance(row, dict) for row in entities):
        raise ValueError('The village scene has invalid entity records.')
    people = [row for row in entities if row.get('templateType') == 'villager_type']
    return {'name': str(user.get('name') or 'Local Village')[:80],
            'level': int(user['userLevelID']), 'gems': int(inventory.get('323', 0)),
            'villagers': len(people),
            'examples': [str(row['name'])[:30] for row in people if row.get('name')][:2]}


def _candidate(root: Path, key: str, instance: str) -> tuple[dict, dict, dict, str, str]:
    profile_raw = _read(root / (key + '.json'))
    save_raw = _read(root / (key + '.tutorial.json'), limit=MAX_SAVE_BYTES)
    profile, saved = json.loads(profile_raw), json.loads(save_raw)
    if not isinstance(profile, dict) or not isinstance(saved, dict):
        raise ValueError('Legacy profile and save must be JSON objects.')
    device, player = profile.get('deviceId'), str(profile.get('pId', ''))
    if (not isinstance(device, str) or not device or len(device) > 512
            or digest(device.encode('utf-8')) != key
            or not re.fullmatch(r'[0-9]{1,20}', player)):
        raise ValueError('The legacy save does not match its player profile.')
    validate_json_tree(saved)
    validate_json_tree(profile)
    profile_hash, save_hash = digest(profile_raw), digest(save_raw)
    summary = _summary(saved)
    summary.update(key=key, fingerprint=digest((profile_hash + save_hash).encode('ascii')),
                   source_instance=instance)
    return summary, profile, saved, profile_hash, save_hash


def preview(folder: Path) -> dict:
    root, instance = _legacy_folder(folder)
    villages, skipped = [], 0
    errors = set()
    for path in sorted(root.iterdir()):
        if not PROFILE_PATTERN.fullmatch(path.name) or not path.with_suffix('.tutorial.json').is_file():
            continue
        try:
            villages.append(_candidate(root, path.stem, instance)[0])
        except (ValueError, KeyError, TypeError, OSError, InvalidAction, RecursionError) as exc:
            skipped += 1
            if isinstance(exc, (ValueError, InvalidAction)) and not isinstance(exc, json.JSONDecodeError):
                errors.add(str(exc) if str(exc).startswith(('File exceeds', 'Unsupported', 'The legacy save')) else
                           'A save or profile contains invalid data.')
            else:
                errors.add('A save or profile could not be read.')
    return {'villages': villages, 'skipped': skipped, 'errors': sorted(errors)}


def import_copy(folder: Path, storage: Path, key: str, fingerprint: str) -> dict:
    if not SLOT_KEY.fullmatch(key):
        raise ValueError('Choose a village from the import preview.')
    root, instance = _legacy_folder(folder)
    try:
        summary, profile, saved, profile_hash, save_hash = _candidate(root, key, instance)
    except (ValueError, KeyError, TypeError, OSError, InvalidAction, RecursionError) as exc:
        raise ValueError('The save could not be read. Close 0.2.6 and preview the folder again.') from exc
    if summary['fingerprint'] != fingerprint:
        raise ValueError('The 0.2.6 save changed after preview. Close 0.2.6 and preview it again.')
    repo = SqliteSaveRepository(storage / (key + '.sqlite3'))
    result = LegacySaveImporter(repo)._import_record(
        key, profile, saved, profile_hash, save_hash, True, True, launch_copy=summary)
    if result.status.startswith('CONFLICT'):
        raise ValueError('This village was imported before. Its playable copy has been kept.')
    return {'key': key, 'status': result.status}


def saved_copies(storage: Path) -> list[dict]:
    result = []
    for path in sorted(storage.glob('*.sqlite3')):
        if not SLOT_KEY.fullmatch(path.stem) or not path.is_file():
            continue
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata'").fetchone():
                continue
            row = db.execute("SELECT value FROM metadata WHERE key='legacy_launch_copy'").fetchone()
        if row is not None:
            result.append(json.loads(row[0]))
    return result


def protect_original_instance(storage: Path, selected: str) -> None:
    if any(village.get('source_instance') == selected for village in saved_copies(storage)):
        raise ValueError('This is the original 0.2.6 instance. Choose a separate Pie 64-bit instance.')

