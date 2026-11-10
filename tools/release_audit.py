"""Check the NEW source tree before publication. Does not inspect or delete saves."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
forbidden = [ROOT/'legacy_reference',ROOT/'backend',ROOT/'windows/tools/play_local.py',
             ROOT/'windows/tools/setup_local.py',ROOT/'windows/launcher/LocalApkSigner.cs']
errors=[]
for path in forbidden:
    if path.exists(): errors.append('Old backend/runtime path remains: '+str(path.relative_to(ROOT)))
for file in ROOT.rglob('*'):
    if not file.is_file(): continue
    if any(part in {'.git','.venv','__pycache__','build','dist','private-assets'} for part in file.parts):continue
    if file.suffix.lower() in {'.apk','.xapk','.obb','.pfx','.p12','.sqlite','.sqlite3','.db'}:
        errors.append('Prohibited file: '+str(file.relative_to(ROOT)))
if errors:
    print('\n'.join(errors));sys.exit(2)
print('PASS: no old backend or runtime saves in distributable source; local Git-ignored private-assets/ is excluded from this scan and never staged.')
