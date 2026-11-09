"""Manual, offline, side-by-side community update. Never replaces an installed save."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import socket
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SHA = '8d25823b824ba766b38e53aedb74b270a0254e6bf3fbbcf1a858b090a66b5c08'
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
PRESERVE = ('backend/private_state', 'play-settings.json', 'analysis/private',
            'analysis/runtime_inputs', 'analysis/local-client', 'analysis/obb_tcf.inventory.csv')


def say(value):
    # Redirected Windows consoles can use a legacy encoding. A success message
    # must not turn a completed update into an exception for a Unicode path.
    encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    print(str(value).encode(encoding, errors='backslashreplace').decode(encoding), flush=True)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    # Same strict parser as migrations; no game database is opened here.
    from migrate_save import load_json
    return load_json(path)


def safe_path(root, relative):
    if not isinstance(relative, str):
        raise ValueError('Unsafe update path')
    value = PureWindowsPath(relative)
    if (not relative or value.as_posix() != relative or '\\' in relative or ':' in relative
            or value.is_absolute() or '..' in value.parts
            or any(part.endswith((' ', '.')) or part.split('.')[0].upper() in
                   {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1, 10)),
                    *('LPT'+str(i) for i in range(1, 10))} for part in value.parts)):
        raise ValueError('Unsafe update path')
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Update path escapes its folder')
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink() or getattr(parent, 'is_junction', lambda: False)():
            raise ValueError('Linked update paths are not supported')
    return path


def reject_links(path):
    paths = [path]
    while paths:
        item = paths.pop()
        if item.is_symlink() or getattr(item, 'is_junction', lambda: False)():
            raise ValueError('Linked folders/files are not supported for an update')
        if item.is_dir():
            paths.extend(item.iterdir())


def verify_package(package):
    manifest = read(package / 'PACKAGE-MANIFEST.json')
    version = manifest['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+-community-test', version):
        raise ValueError('Expected a versioned community release package')
    if manifest.get('personal_data_included') is not False:
        raise ValueError('Update package is not marked clean')
    if read(package / 'VERSION.json')['restoration_version'] != version:
        raise ValueError('Package versions disagree')
    seen = set()
    for name, record in manifest['files'].items():
        path = safe_path(package, name)
        if name.casefold() in seen:
            raise ValueError('Duplicate Windows update path')
        seen.add(name.casefold())
        lower = name.casefold()
        if (any(lower == prefix or lower.startswith(prefix + '/') for prefix in PRESERVE)
                or lower.startswith(('backups/', 'experiments/'))):
            raise ValueError('Update package contains private player data')
        reject_links(path)
        if not path.is_file() or path.stat().st_size != record['bytes'] or digest(path) != record['sha256']:
            raise ValueError('Update package integrity check failed: ' + name)
    required = {'Village Life.exe', 'VERSION.json', 'runtime/python/python.exe',
                'tools/migrate_save.py', 'tools/update_local.py', 'backend/world.py'}
    if not required.issubset(manifest['files']):
        raise ValueError('Incomplete update package')
    return manifest


def assert_stopped(old, settings):
    # Be conservative: refuse if any local service owns the game's port.
    with socket.socket() as sock:
        sock.settimeout(1)
        if sock.connect_ex(('127.0.0.1', 80)) == 0:
            raise RuntimeError('Close the game and launcher using Stop before updating.')
    if os.name != 'nt':
        return
    script = ("[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
              "Get-CimInstance Win32_Process | Select-Object ProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Compress")
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                            capture_output=True, text=True, encoding='utf-8', timeout=30, creationflags=FLAGS)
    if result.returncode:
        raise RuntimeError('Unable to check running game processes. No update performed.')
    processes = json.loads(result.stdout or '[]')
    if isinstance(processes, dict):
        processes = [processes]
    instance = settings.get('instance')
    if not isinstance(instance, str) or not re.fullmatch(r'[A-Za-z0-9_]+', instance):
        raise ValueError('Existing game instance setting is missing or invalid')
    for process in processes:
        if process.get('ProcessId') == os.getpid():
            continue
        command = process.get('CommandLine') or ''
        exe = process.get('ExecutablePath') or ''
        name = (process.get('Name') or '').lower()
        in_old = str(old).casefold() in command.casefold() or str(old).casefold() in exe.casefold()
        vm = name == 'hd-player.exe' and re.search(r'--instance\s+"?' + re.escape(instance) + r'(?:"|\s|$)', command, re.I)
        # A hidden command line cannot establish that the VM is a different one.
        if vm or (name == 'hd-player.exe' and not command) or (in_old and name in
                {'python.exe', 'pythonw.exe', 'village life.exe', 'dotnet.exe', 'villagelifelauncher.exe'}):
            raise RuntimeError('Close the Village Life launcher and its BlueStacks instance before updating.')


def snapshot(old):
    result = {}
    for relative in PRESERVE:
        source = safe_path(old, relative)
        if not source.exists():
            continue
        reject_links(source)
        for path in sorted(source.rglob('*')) if source.is_dir() else [source]:
            if path.is_file():
                result[path.relative_to(old).as_posix()] = {'bytes': path.stat().st_size, 'sha256': digest(path)}
    for path in old.glob('*.xapk'):
        reject_links(path)
        if digest(path) != ARCHIVE_SHA:
            raise ValueError('Existing original game archive failed verification')
        result[path.name] = {'bytes': path.stat().st_size, 'sha256': ARCHIVE_SHA}
    if sum(name.lower().endswith('.xapk') for name in result) != 1:
        raise ValueError('Expected exactly one verified original game archive in the player folder')
    return result


def migrate_stage(stage):
    python = stage / 'runtime/python/python.exe'
    result = subprocess.run([str(python), str(stage / 'tools/migrate_save.py'),
                             '--state', str(stage / 'backend/private_state'),
                             '--report', str(stage / 'UPDATE-SAVE-REPORT.json')],
                            cwd=stage, capture_output=True, text=True, timeout=180, creationflags=FLAGS)
    if result.returncode:
        # Detailed errors remain local. Never include save contents in a public report.
        (stage / 'update-error.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
        raise RuntimeError('Save validation failed. Original village unchanged; details are in the staging folder.')


def update(old, package=ROOT, destination=None, guard=assert_stopped, migrate=migrate_stage):
    for chosen in (Path(old).absolute(), Path(package).absolute()):
        if chosen.is_symlink() or getattr(chosen, 'is_junction', lambda: False)():
            raise ValueError('Select an ordinary player/update folder, not a link')
    old, package = Path(old).resolve(), Path(package).resolve()
    manifest = verify_package(package)
    version = manifest['version']
    if not (old / 'Village Life.exe').is_file() or not (old / 'VERSION.json').is_file():
        raise ValueError('Choose the existing player folder containing Village Life.exe')
    old_version = read(old / 'VERSION.json')['restoration_version']
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)-community-test', old_version)
    if not match or tuple(map(int, match.groups())) >= tuple(map(int, version.split('-')[0].split('.'))):
        raise ValueError('Only an older community version can be upgraded; no downgrade or repeat overwrite performed')
    if any((old / name).exists() for name in ('DEVELOPMENT.md', 'tools/feature_audit.py')):
        raise ValueError('Choose a community player installation, not a development/private test folder')
    settings = read(old / 'play-settings.json')
    if settings.get('server_mode', 'local') != 'local':
        raise ValueError('This updater supports local villages. Hosted villages need a separate server upgrade.')
    if not (old / 'backend/private_state').is_dir():
        raise ValueError('Existing save folder is missing; no fresh village was substituted')
    destination = Path(destination).resolve() if destination else old.with_name(old.name + '-' + version)
    if destination.parent != old.parent or destination in {old, package} or old.is_relative_to(package) or package.is_relative_to(old):
        raise ValueError('The update kit and new player folder must be separate from the old installation')
    if destination.exists():
        raise ValueError('The upgraded player folder already exists. Open it to continue; it will not be overwritten.')
    guard(old, settings)
    say('Checking the existing installation and update files...')
    before = snapshot(old)
    required_bytes = (sum(record['bytes'] for record in manifest['files'].values())
                      + sum(record['bytes'] for record in before.values())
                      + sum(record['bytes'] for name, record in before.items()
                            if name.startswith('backend/private_state/') or name == 'play-settings.json'))
    if shutil.disk_usage(old.parent).free < required_bytes + 128 * 1024 * 1024:
        raise RuntimeError('Not enough free space for the new installation and save backup')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup = old / 'backups' / ('before-update-' + stamp)
    backup.mkdir(parents=True, exist_ok=False)
    for relative, record in before.items():
        # The complete old installation remains the rollback. Save + settings
        # also receive an independent, checksummed backup without duplicating OBB.
        if relative.startswith('backend/private_state/') or relative == 'play-settings.json':
            target = safe_path(backup, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(safe_path(old, relative), target)
            if digest(target) != record['sha256']:
                raise RuntimeError('Save backup verification failed')
    (backup / 'BACKUP-MANIFEST.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
    stage = destination.with_name(destination.name + '.staging-' + uuid.uuid4().hex[:8])
    stage.mkdir(exist_ok=False)
    journal = {'status': 'preparing', 'from_version': old_version, 'to_version': version,
               'previous_installation': str(old), 'new_installation': str(destination),
               'save_backup': str(backup), 'prepared_utc': stamp}
    def record():
        (stage / 'UPDATE-RECEIPT.json').write_text(json.dumps(journal, indent=2), encoding='utf-8')
    record()
    try:
        say('Preparing the new version and copying your village...')
        for relative, expected in manifest['files'].items():
            target = safe_path(stage, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(safe_path(package, relative), target)
            if digest(target) != expected['sha256']:
                raise RuntimeError('Copied update file failed verification')
        shutil.copy2(package / 'PACKAGE-MANIFEST.json', stage / 'PACKAGE-MANIFEST.json')
        # Complete kits may contain the same original archive under another name.
        # Keep exactly one local copy, preserving the old installation's name.
        archive_names = [name for name in manifest['files'] if name.lower().endswith('.xapk')]
        old_archive = next(name for name in before if name.lower().endswith('.xapk'))
        for name in archive_names:
            if digest(stage / name) != ARCHIVE_SHA:
                raise ValueError('Update contains an unexpected game archive')
            if name != old_archive:
                (stage / name).unlink()
        for relative, expected in before.items():
            target = safe_path(stage, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(safe_path(old, relative), target)
            if digest(target) != expected['sha256']:
                raise RuntimeError('Player data changed while copying; no update activated')
        say('Checking and repairing the copied save...')
        migrate(stage)
        guard(old, settings)
        if snapshot(old) != before:
            raise RuntimeError('Existing player data changed during update; no update activated')
        journal['status'] = 'ready'
        record()
        (stage / 'ROLLBACK.txt').write_text(
            'Close the new game and launcher, then open Village Life.exe in:\n' + str(old) +
            '\n\nThat folder retains your pre-update village. Keep the new folder too.\n'
            'Progress made in the new version is separate; rollback does not merge it backwards.\n', encoding='utf-8')
        # Rename only our freshly created staging folder, after all checks pass.
        stage.rename(destination)
    except Exception:
        journal['status'] = 'failed-original-retained'
        record()
        raise
    say('Update ready. From now on, open: ' + str(destination / 'Village Life.exe'))
    say('Your old folder and a separate save backup have been retained.')
    return destination


def choose_folder():
    if os.name != 'nt':
        raise ValueError('Use --from with the existing installation folder')
    script = ("[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new(); "
              "Add-Type -AssemblyName System.Windows.Forms; "
              "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
              "$dialog.Description = 'Select your OLD Village Life player folder'; "
              "$dialog.ShowNewFolderButton = $false; "
              "if ($dialog.ShowDialog() -eq 'OK') { [Console]::Write($dialog.SelectedPath) }")
    result = subprocess.run(['powershell.exe', '-NoProfile', '-STA', '-Command', script],
                            capture_output=True, text=True, encoding='utf-8', creationflags=FLAGS)
    if result.returncode or not result.stdout.strip():
        raise ValueError('No player folder selected; nothing changed')
    return Path(result.stdout.strip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from', dest='old', type=Path)
    parser.add_argument('--choose', action='store_true')
    args = parser.parse_args()
    try:
        old = args.old or (choose_folder() if args.choose else None)
        if old is None:
            parser.error('Choose a player folder or supply --from')
        destination = update(old)
        if os.name == 'nt':
            os.startfile(destination)
        return 0
    except Exception as error:
        say('UPDATE STOPPED: ' + str(error))
        say('Your existing installation was not replaced. Keep all folders for recovery.')
        return 1


if __name__ == '__main__':
    sys.exit(main())
