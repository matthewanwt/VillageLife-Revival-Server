"""Check the NEW source tree before publication. Does not inspect or delete saves."""
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
forbidden = [ROOT/'legacy_reference',ROOT/'backend',ROOT/'windows/tools/play_local.py',
             ROOT/'windows/tools/setup_local.py',ROOT/'windows/launcher/LocalApkSigner.cs']
errors=[]
# Check Git's index so ignored local assets cannot fail a source-only audit.
MAX_GITHUB_BYTES = 100 * 1024 * 1024
tracked = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=ROOT)
blobs = {}
for entry in tracked.split(b'\0'):
    if not entry:
        continue
    metadata, path = entry.split(b'\t', 1)
    mode, oid, stage = metadata.split()
    if mode != b'160000':
        blobs.setdefault(oid, []).append(path.decode('utf-8', 'replace'))
sizes = subprocess.check_output(
    ['git', 'cat-file', '--batch-check=%(objectname) %(objecttype) %(objectsize)'],
    cwd=ROOT, input=b''.join(oid + b'\n' for oid in blobs),
)
for line in sizes.splitlines():
    oid, kind, size = line.split()
    if kind == b'blob' and int(size) > MAX_GITHUB_BYTES:
        errors.extend(f'GitHub 100 MiB limit exceeded: {path}' for path in blobs[oid])
for path in forbidden:
    if path.exists(): errors.append('Old backend/runtime path remains: '+str(path.relative_to(ROOT)))
paths = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others',
                                 '--exclude-standard'], cwd=ROOT)
for path in set(paths.split(b'\0')) - {b''}:
    file = ROOT / path.decode('utf-8', 'replace')
    if file.is_file() and (file.suffix.lower() in {'.apk','.xapk','.obb','.pfx','.p12','.sqlite','.sqlite3','.db'}
                          or file.name in {'transport-key.txt','private-password.txt','bluestacks-binding.json',
                                           'launcher-settings.json','prepared-client.json'}):
        errors.append('Prohibited file: '+str(file.relative_to(ROOT)))
if errors:
    print('\n'.join(errors));sys.exit(2)
print('PASS: no old backend or runtime saves in distributable source; local Git-ignored private-assets/ is excluded from this scan and never staged.')
