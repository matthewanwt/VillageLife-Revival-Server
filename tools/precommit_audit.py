"""Read-only check for accidentally staged private or oversized files.

Use Git status, not just .gitignore, as a final safeguard. This script never
removes files or runs subprocesses against source files.
"""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BAD_COMPONENTS = {'private_state', 'secrets', 'backups', 'experiments', 'originals', '__pycache__'}
BAD_SUFFIXES = {'.apk', '.xapk', '.obb', '.sqlite', '.sqlite3', '.db', '.tcf', '.swf', '.t3g'}


def main():
    process = subprocess.run(['git', '-C', str(ROOT), 'diff', '--cached', '--name-only', '-z'],
                             capture_output=True, check=False)
    if process.returncode:
        print('No Git index detected. Run this after staging in GitHub Desktop.')
        return 0
    candidates = [name.decode('utf-8') for name in process.stdout.split(b'\x00') if name]
    issues = []
    for relative in candidates:
        target = ROOT / relative
        if any(part.lower() in BAD_COMPONENTS for part in Path(relative).parts):
            issues.append(relative+' : forbidden private/generated directory')
        if target.suffix.lower() in BAD_SUFFIXES:
            issues.append(relative+' : original binary or database extension')
        if target.exists() and target.is_file() and target.stat().st_size > 10 * 1024 * 1024:
            issues.append(relative+' : unusually large staged file')
    if issues:
        print('WARNING: Review these staged files before committing:')
        for line in issues: print(' - '+line)
        return 2
    print(f'Staged-file structural audit passed ({len(candidates)} files). Inspect content for secrets as well.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
