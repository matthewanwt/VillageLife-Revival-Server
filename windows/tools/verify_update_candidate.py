"""Private disposable old-kit upgrade and historical-save validation; no game launch."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import update_local
import migrate_save

ROOT = Path(__file__).resolve().parents[1]


def run_candidate(candidate, out, production_guard=False):
    candidate = Path(candidate).resolve()
    update_local.verify_package(candidate)
    python = candidate / 'runtime/python/python.exe'
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    isolated = subprocess.run([str(python), '-c',
        'import sys,json;print(json.dumps({"isolated":sys.flags.isolated,"paths":sys.path}))'],
        capture_output=True, text=True, timeout=30, cwd=candidate, creationflags=flags)
    if isolated.returncode:
        raise RuntimeError(isolated.stderr)
    runtime = json.loads(isolated.stdout)
    if not runtime['isolated'] or any(not Path(path).resolve().is_relative_to(candidate) for path in runtime['paths']):
        raise AssertionError('Candidate runtime is not isolated')
    sources = sorted((ROOT / 'experiments').glob('fixture-*/state'))
    backups = sorted((ROOT / 'backups').glob('play-session-*'))
    sources += backups[:1] + backups[-1:]
    matrix = []
    for number, source in enumerate(sources):
        before = {p.relative_to(source).as_posix(): update_local.digest(p) for p in source.rglob('*') if p.is_file()}
        staged = out / 'save-matrix' / str(number)
        shutil.copytree(source, staged)
        result = subprocess.run([str(python), str(candidate / 'tools/migrate_save.py'), '--state', str(staged),
                                 '--database', str(ROOT / 'analysis/private/game_tables.sqlite'),
                                 '--report', str(staged.parent / (str(number) + '-report.json'))],
                                capture_output=True, text=True, timeout=90, cwd=candidate, creationflags=flags)
        unchanged = before == {p.relative_to(source).as_posix(): update_local.digest(p) for p in source.rglob('*') if p.is_file()}
        matrix.append({'fixture': source.parent.name if source.name == 'state' else source.name,
                       'passed': result.returncode == 0, 'source_unchanged': unchanged})
        if result.returncode:
            (staged.parent / (str(number) + '-error.txt')).write_text(result.stdout + result.stderr, encoding='utf-8')
    # Use an immutable old release as code/runtime source. Add only private copies
    # of local setup and a known existing village; never modify that distribution.
    previous = json.loads((ROOT / 'dist/latest-community-complete-package.json').read_text(encoding='utf-8'))
    previous_zip = Path(previous['zip'])
    previous_hash = update_local.digest(previous_zip)
    if previous_hash != previous['sha256']:
        raise ValueError('Previous community archive changed')
    old = out / 'old player with spaces & punctuation'
    shutil.copytree(Path(previous['folder']), old)
    for relative in update_local.PRESERVE:
        source, target = ROOT / relative, old / relative
        if not source.exists() or relative == 'backend/private_state':
            continue
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    saved_source = ROOT / 'experiments/fixture-community-native-20261105T212825Z/state'
    shutil.copytree(saved_source, old / 'backend/private_state')
    before = update_local.snapshot(old)
    guard_checked = False
    guard_error = None
    try:
        update_local.assert_stopped(old, update_local.read(old / 'play-settings.json'))
        guard_checked = True
    except RuntimeError as error:
        guard_error = str(error)
    # No game/service ever uses this disposable old folder. A no-op guard here
    # permits offline copying while the developer's VM is open; record that scope.
    def migrate(stage):
        update_local.migrate_stage(stage)
    guard = update_local.assert_stopped if production_guard else lambda *_: None
    target = update_local.update(old, candidate, guard=guard, migrate=migrate)
    if update_local.snapshot(old) != before:
        raise AssertionError('Old player data changed')
    repeated_rejected = False
    try:
        update_local.update(old, candidate, guard=guard)
    except ValueError:
        repeated_rejected = True
    if update_local.digest(previous_zip) != previous_hash:
        raise AssertionError('Old community ZIP changed')
    report = {'candidate': str(candidate), 'bundled_runtime_isolated': True,
              'save_matrix': matrix, 'all_saved_sources_unchanged': all(row['source_unchanged'] for row in matrix),
              'upgrade_completed_with_bundled_runtime': True, 'previous_archive_unchanged': True,
              'repeat_update_refused': repeated_rejected, 'old_installation_unchanged': True,
              'rollback_folder_retained': old.is_dir(), 'new_installation': str(target),
              'actual_stop_guard_checked': guard_checked, 'stop_guard_message': guard_error,
              'disposable_upgrade_used_noop_stop_guard': not production_guard,
              'windows_folder_picker_tested': False, 'native_restart_tested': False,
              'second_physical_pc_tested': False}
    (ROOT / 'analysis/update-candidate-validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    if not all(row['passed'] and row['source_unchanged'] for row in matrix):
        raise RuntimeError('Historical save matrix has failures; inspect private fixture errors')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--production-guard', action='store_true', help='Require the real stopped-game check for the disposable install')
    args = parser.parse_args()
    candidate = args.candidate or Path(json.loads((ROOT / 'dist/latest-community-candidate.json').read_text(encoding='utf-8'))['folder'])
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = ROOT / 'experiments' / ('updater-validation-' + stamp)
    out.mkdir(parents=True, exist_ok=False)
    run_candidate(candidate, out, args.production_guard)


if __name__ == '__main__':
    main()
