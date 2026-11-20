"""Verify the exact source selected for a build; never writes a player save."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import re
from source_stamp import source_stamp

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--private-candidate', action='store_true')
    args = parser.parse_args()
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    status = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, capture_output=True, text=True)
    dirty = revision.returncode != 0 or status.returncode != 0 or bool(status.stdout.strip())
    if dirty and not args.private_candidate:
        raise SystemExit('Public builds require a committed, clean source tree. Use --private-candidate for local tests.')
    result = {'format': 'VillageLifeReleaseGateV1', 'revision': revision.stdout.strip() if revision.returncode == 0 else None,
              'private_candidate': args.private_candidate, 'dirty_source': dirty, 'checks': []}
    stamp = source_stamp(ROOT)
    with tempfile.TemporaryDirectory() as directory:
        env = {**os.environ, 'PYTHONPATH': str(ROOT / 'src'), 'TEMP': directory, 'TMP': directory}
        commands = [[sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                    [sys.executable, 'tools/benchmark_save_requests.py']]
        if revision.returncode == 0:
            commands.append([sys.executable, 'tools/release_audit.py'])
        if not args.private_candidate:
            commands.append([sys.executable, '-m', 'pip_audit', '-r', 'requirements-build.txt', '--format', 'json'])
        for command in commands:
            completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
            result['checks'].append({'command': command[1:], 'exit_code': completed.returncode})
            if command[1:3] == ['-m', 'unittest']:
                match = re.search(r'Ran (\d+) tests', completed.stderr)
                if match:
                    result['tests_run'] = int(match.group(1))
            if 'tools/benchmark_save_requests.py' in command and completed.returncode == 0:
                result['performance'] = json.loads(completed.stdout)
            print(completed.stdout)
            print(completed.stderr, file=sys.stderr)
            if completed.returncode:
                result['passed'] = False
                args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
                return 2
    if source_stamp(ROOT) != stamp:
        raise SystemExit('Source changed during release validation. Run the gate again after edits are complete.')
    result['source_sha256'] = stamp
    result['passed'] = True
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
