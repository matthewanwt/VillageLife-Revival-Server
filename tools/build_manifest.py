"""Write exact source/payload hashes and a build-tool bill of materials."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from source_stamp import source_stamp

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--gate', type=Path, required=True)
    parser.add_argument('--signed', action='store_true')
    args = parser.parse_args()
    source = source_stamp(ROOT)
    gate = json.loads(args.gate.read_text(encoding='utf-8'))
    if not gate.get('passed') or gate.get('source_sha256') != source:
        raise SystemExit('Source differs from the successful release gate; refusing to label this build verified.')
    components = [{'type': 'application', 'name': 'Python', 'version': sys.version.split()[0]},
                  {'type': 'library', 'name': 'SQLite', 'version': sqlite3.sqlite_version}]
    for deps in (args.payload / 'StartVillageLife').glob('*.deps.json'):
        document=json.loads(deps.read_text(encoding='utf-8'))
        for name in document.get('libraries', {}):
            if name.startswith(('Microsoft.NETCore.App.Runtime.', 'Microsoft.WindowsDesktop.App.Runtime.')):
                package, version=name.rsplit('/',1)
                components.append({'type':'framework','name':package,'version':version})
    for name in ('pyinstaller', 'setuptools', 'packaging', 'pyinstaller-hooks-contrib', 'altgraph', 'pefile', 'pywin32-ctypes'):
        try: components.append({'type': 'library', 'name': name, 'version': importlib.metadata.version(name)})
        except importlib.metadata.PackageNotFoundError: pass
    for name, command in (('.NET SDK', ['dotnet', '--version']),
                          ('Java', [str(args.java_home / 'bin/java.exe'), '-version'])):
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        components.append({'type': 'application', 'name': name,
                           'version': (result.stdout or result.stderr).splitlines()[0].strip()})
    (args.payload / 'BUILD-SBOM.cdx.json').write_text(json.dumps({'bomFormat': 'CycloneDX', 'specVersion': '1.6',
        'version': 1, 'components': components}, indent=2), encoding='utf-8')
    payload = {path.relative_to(args.payload).as_posix(): digest(path)
               for path in sorted(args.payload.rglob('*')) if path.is_file() and path.name != 'BUILD-MANIFEST.json'}
    manifest = {'format': 'VillageLifeBuildManifestV1', 'validation': gate,
                'authenticode_signed': args.signed, 'source_sha256': source, 'payload_sha256': payload,
                'components': components}
    (args.payload / 'BUILD-MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
