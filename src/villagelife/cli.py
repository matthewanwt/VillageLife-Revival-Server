"""Management command line. Keeps private databases outside version control."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from villagelife.core.model import empty_native_village
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.persistence.auth_store import AccountTokens
from villagelife.persistence.legacy_import import LegacySaveImporter
from villagelife.persistence.portable import PortableSaves
from villagelife.platforms import bluestacks as bs


def default_db() -> Path:
    override = os.environ.get('VILLAGELIFE_DB')
    if override:
        return Path(override).expanduser()
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    else:
        base = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
    return base / 'VillageLifeRevivalNext' / 'worlds.sqlite3'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Village Life new backend administrative CLI')
    parser.add_argument('--db', type=Path, default=default_db(), help='New SQLite DB path outside Git')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init-db')
    a = sub.add_parser('create-account'); a.add_argument('--name', default='')
    a = sub.add_parser('issue-token'); a.add_argument('account_id')
    a = sub.add_parser('create-village'); a.add_argument('account_id')
    a = sub.add_parser('list-villages'); a.add_argument('account_id')
    a = sub.add_parser('import-legacy'); a.add_argument('private_state', type=Path)
    a.add_argument('--apply', action='store_true', help='Import copies; originals remain untouched')
    a = sub.add_parser('export'); a.add_argument('village_id'); a.add_argument('output', type=Path)
    a = sub.add_parser('import-portable'); a.add_argument('owner_id'); a.add_argument('archive', type=Path)
    a = sub.add_parser('backup-db'); a.add_argument('output', type=Path)
    a = sub.add_parser('serve'); a.add_argument('--port', type=int, default=8765)
    sub.add_parser('list-instances')
    a = sub.add_parser('bind-instance'); a.add_argument('instance_id')
    sub.add_parser('verify-instance')
    sub.add_parser('start-instance')
    sub.add_parser('adb-check')
    sub.add_parser('open-instance-manager')
    sub.add_parser('export-missing-requests')
    sub.add_parser('network-report')
    a = sub.add_parser('export-support'); a.add_argument('output', type=Path)

    args = parser.parse_args(argv)
    binding = default_db().parent/'bluestacks-binding.json'
    if args.command == 'list-instances':
        print(json.dumps([vars(x) for x in bs.list_instances()], ensure_ascii=False)); return 0
    if args.command == 'bind-instance':
        selected = bs.select_by_id(bs.list_instances(), args.instance_id)
        print(json.dumps(bs.bind_instance(binding, selected, bs.installation()), ensure_ascii=False)); return 0
    if args.command == 'verify-instance':
        print('Verified:', bs.verify_binding(binding, bs.list_instances(), bs.installation()).id); return 0
    if args.command == 'start-instance':
        print('Started:', bs.start_bound_instance(binding)); return 0
    if args.command == 'adb-check':
        print(json.dumps(bs.adb_status(binding))); return 0
    if args.command == 'open-instance-manager':
        bs.open_manager(); print('Opened Multi-instance Manager'); return 0
    if args.command == 'network-report':
        from villagelife.platforms.network import report
        print(json.dumps(report(binding), indent=2)); return 0
    if args.command == 'export-support':
        from villagelife.support import export_support
        print('Created:', export_support(args.output, binding)); return 0
    repo = SqliteSaveRepository(args.db)
    if args.command == 'export-missing-requests':
        from villagelife.support import export_missing
        print('Created:', export_missing(repo)); return 0
    if args.command == 'init-db':
        print('Database initialised:', repo.path)
    elif args.command == 'create-account':
        print('Account ID:', repo.create_account(args.name))
    elif args.command == 'issue-token':
        print('TOKEN (only shown once; store securely):', AccountTokens(repo).issue(args.account_id))
    elif args.command == 'create-village':
        print('Village ID:', repo.create_village(args.account_id, empty_native_village()))
        print('NOTE: This is a development fixture, not a playable original-client village.')
    elif args.command == 'list-villages':
        for v in repo.list_villages(args.account_id):
            print(v.village_id, v.format, v.revision)
    elif args.command == 'import-legacy':
        entries = LegacySaveImporter(repo).import_directory(args.private_state, apply=args.apply)
        for item in entries:
            print(json.dumps(item.__dict__, ensure_ascii=False))
        print(f'{len(entries)} profile(s) checked; originals were not changed.')
        if not args.apply:
            print('Dry run only. Pass --apply to copy validated saves into the new database.')
    elif args.command == 'export':
        print(PortableSaves(repo).export(args.village_id, args.output))
    elif args.command == 'import-portable':
        print('New village:', PortableSaves(repo).import_as_new(args.archive, args.owner_id))
    elif args.command == 'backup-db':
        if args.output.exists():
            parser.error('Backup already exists; refusing to overwrite')
        repo.backup_to(args.output); print('Backup written:', args.output)
    elif args.command == 'serve':
        if not 1 <= args.port <= 65535:
            parser.error('Port must be between 1 and 65535')
        from villagelife.transport.http_api import serve
        serve(repo, args.port)
    return 0


def run(argv: list[str] | None = None) -> int:
    # Preserve clear, supportable error codes without printing private paths or
    # raw player data when a Windows user triggers a diagnostic failure.
    try:
        return main(argv)
    except bs.InstanceError as exc:
        print(str(exc), file=__import__('sys').stderr)
        return 2
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print('[VL-USER-ACTION] '+type(exc).__name__+': '+str(exc)[:300], file=__import__('sys').stderr)
        return 2
    except OSError as exc:
        print('[VL-IO-ERROR] Could not access a required file or service ('+type(exc).__name__+').', file=__import__('sys').stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(run())
