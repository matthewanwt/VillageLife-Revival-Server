"""Read-only recipient diagnostics for the selected setup instance; never installs a game."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
MARKER = '__VL_DIAG_EXIT='


def parse_remote_status(output):
    matches = re.findall(r'^' + MARKER + r'(\d+)\s*$', output, re.MULTILINE)
    return int(matches[0]) if len(matches) == 1 and 0 <= int(matches[0]) <= 255 else None


def capture(argv, timeout=20):
    try:
        result = subprocess.run([str(v) for v in argv], capture_output=True,
                                text=True, errors='replace', timeout=timeout, creationflags=FLAGS)
        return {'transport_exit_code': result.returncode,
                'stdout': result.stdout[:8000], 'stderr': result.stderr[:8000]}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'error': str(error)}


def main():
    from setup_local import available_instances, select_instance
    from platforms.bluestacks.discovery import discover_bluestacks
    installation=discover_bluestacks()
    ADB=installation.adb;PROGRAM=installation.directory
    from network_check import inspect_network
    parser = argparse.ArgumentParser()
    parser.add_argument('--instance')
    args = parser.parse_args()
    previous = {}
    for name in ('play-settings.json', 'setup-network-check.json'):
        path = ROOT / name
        if path.exists():
            previous.update(json.loads(path.read_text(encoding='utf-8')))
    selected = select_instance(available_instances(), args.instance or previous.get('instance'))
    serial = '127.0.0.1:' + str(selected['adb_port'])
    prefix = [ADB, '-s', serial]
    report = {'generated_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'instance': selected, 'configuration': inspect_network(selected['id']),
              'adb_version': capture([ADB, 'version']),
              'bluestacks_version': capture(['powershell.exe', '-NoProfile', '-Command',
                  "(Get-Item -LiteralPath '" + str(PROGRAM / 'HD-Player.exe').replace("'", "''") + "').VersionInfo.FileVersion"]),
              'connect': capture([ADB, 'connect', serial]),
              'device_state': capture(prefix + ['get-state']),
              'boot_completed': capture(prefix + ['shell', 'getprop sys.boot_completed']),
              'android_version': capture(prefix + ['shell', 'getprop ro.build.version.release']),
              'shell_exit_control': capture(prefix + ['shell',
                  'false; vl_rc=$?; printf "\\n__VL_DIAG_EXIT=%s\\n" "$vl_rc"']),
              'external_probe': capture(prefix + ['shell',
                  'toybox nc -w 3 1.1.1.1 443 </dev/null; vl_rc=$?; printf "\\n__VL_DIAG_EXIT=%s\\n" "$vl_rc"'])}
    for key in ('shell_exit_control', 'external_probe'):
        report[key]['android_exit_code'] = parse_remote_status(report[key].get('stdout', ''))
    path = ROOT / 'SETUP DIAGNOSTICS.json'
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Diagnostic saved: SETUP DIAGNOSTICS.json')
    print('No game was installed, no village was changed, and no network settings were changed.')
    print('Please send this file privately to the developer.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('DIAGNOSTIC STOPPED: ' + ascii(str(error)))
        raise SystemExit(1)
