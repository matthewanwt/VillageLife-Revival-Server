"""Shared import limits; gameplay history is preserved, not truncated."""
import json
from .validation import validate_json_tree

MAX_SAVE_BYTES = 128 * 1024 * 1024
MAX_PROFILE_BYTES = 1024 * 1024
MAX_APK_BYTES = 300 * 1024 * 1024
MAX_APK_EXPANDED = 600 * 1024 * 1024
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10000


def bounded_read(path, limit):
    if path.is_symlink():
        raise ValueError('Linked save files are unsupported')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError(f'File exceeds the {limit // (1024 * 1024)} MiB import limit.')
    return raw


def checked_json(raw):
    try:
        value = json.loads(raw)
        validate_json_tree(value)
    except RecursionError as error:
        raise ValueError('Save nesting exceeds the supported limit') from error
    return value


def validate_apk_archive(archive):
    entries = archive.infolist()
    if len(entries) > MAX_ARCHIVE_ENTRIES:
        raise ValueError('APK contains too many entries')
    if any(entry.file_size > MAX_APK_BYTES for entry in entries) or sum(entry.file_size for entry in entries) > MAX_APK_EXPANDED:
        raise ValueError('Expanded APK exceeds the supported size')
    names = [entry.filename for entry in entries]
    if len(names) != len(set(names)):
        raise ValueError('APK contains duplicate entries')
