"""Management command line. Keeps private databases outside version control."""
from __future__ import annotations
import argparse
import errno
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from pathlib import Path
from villagelife.core.errors import InvalidAction, SaveBackupError, SaveSchemaError
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
    a = sub.add_parser('compact-db'); a.add_argument('output', type=Path,
        help='Write a consistent compacted copy; never replaces the active database')
    a = sub.add_parser('add-local-gems'); a.add_argument('amount', type=int); a.add_argument('--village-id')
    sub.add_parser('list-gem-villages')
    sub.add_parser('list-local-villages')
    sub.add_parser('create-local-village')
    a = sub.add_parser('delete-local-village'); a.add_argument('village_id'); a.add_argument('--backup', type=Path)
    a = sub.add_parser('delete-imported-village'); a.add_argument('key'); a.add_argument('--backup', type=Path); a.add_argument('--storage', type=Path)
    a = sub.add_parser('restore-portable'); a.add_argument('archive', type=Path)
    a = sub.add_parser('serve'); a.add_argument('--port', type=int, default=8765)
    a.add_argument('--launcher-stdin', action='store_true', help=argparse.SUPPRESS)
    a.add_argument('--local-village-id', help='Open the explicitly selected local village for this server run')
    a.add_argument('--game-tables', type=Path, help='Enable original-client RPC using user-extracted game definitions')
    a.add_argument('--xapk', type=Path, help='User-supplied original XAPK to read the original manifest')
    a.add_argument('--obb', type=Path, help='User-supplied OBB for original resource responses')
    a.add_argument('--inventory', type=Path, help='Resource-offset inventory for the OBB')
    a.add_argument('--transport-key-file', type=Path, help=argparse.SUPPRESS)
    a = sub.add_parser('preview-legacy-villages'); a.add_argument('folder', type=Path)
    a = sub.add_parser('copy-legacy-village'); a.add_argument('folder', type=Path)
    a.add_argument('key'); a.add_argument('fingerprint')
    sub.add_parser('list-legacy-villages')
    sub.add_parser('stop-original-game')
    sub.add_parser('original-game-status')
    a = sub.add_parser('list-instances'); a.add_argument('--eligible', action='store_true')
    a = sub.add_parser('bind-instance'); a.add_argument('instance_id')
    a = sub.add_parser('verify-instance'); a.add_argument('--selection-only', action='store_true')
    sub.add_parser('start-instance')
    a = sub.add_parser('adb-check'); a.add_argument('--once', action='store_true')
    sub.add_parser('check-bluestacks')
    sub.add_parser('open-instance-manager')
    sub.add_parser('export-missing-requests')
    sub.add_parser('network-report')
    a = sub.add_parser('verify-network'); a.add_argument('--port', type=int, choices=range(1, 65536), metavar='PORT')
    a = sub.add_parser('export-support'); a.add_argument('output', type=Path)
    a.add_argument('--launcher-version', default='')
    a.add_argument('--build-manifest', type=Path)
    a.add_argument('--adb-check', action='store_true')
    a = sub.add_parser('install-prepared-client'); a.add_argument('--apk', type=Path, required=True); a.add_argument('--obb', type=Path, required=True); a.add_argument('--replace', action='store_true')
    a = sub.add_parser('repair-prepared-obb'); a.add_argument('--apk', type=Path, required=True); a.add_argument('--obb', type=Path, required=True)
    a = sub.add_parser('check-original-game'); a.add_argument('--prepared', action='store_true')
    a.add_argument('--apk', type=Path); a.add_argument('--obb', type=Path)
    a.add_argument('--verify-hash', action='store_true')
    a = sub.add_parser('probe-guest-backend'); a.add_argument('--port', type=int, default=80)
    a = sub.add_parser('launch-original-game')
    a.add_argument('--restart', action='store_true', help='Close only Village Life before launching it')
    a = sub.add_parser('prepare-original-client'); a.add_argument('--xapk', type=Path, required=True); a.add_argument('--output', type=Path, required=True); a.add_argument('--java-home', type=Path)
    a.add_argument('--prepare-data', action='store_true')

    args = parser.parse_args(argv)
    if args.command == 'serve' and args.launcher_stdin:
        from threading import Thread

        def stop_with_launcher() -> None:
            try:
                sys.stdin.buffer.read()
            finally:
                os._exit(0)  # Each completed save has already been committed.

        Thread(target=stop_with_launcher, daemon=True).start()
    binding = default_db().parent/'bluestacks-binding.json'
    if args.command in {'add-local-gems', 'list-gem-villages'} and not args.db.is_file():
        raise ValueError('Play through the tutorial to Woodland before adding gems.')
    legacy_storage = binding.parent / 'imported-villages'

    def protect_instance(ident: str) -> None:
        from villagelife.persistence.legacy_launcher import protect_original_instance
        try:
            protect_original_instance(legacy_storage, ident)
        except ValueError as exc:
            raise bs.InstanceError('VL-LEGACY-INSTANCE-PROTECTED', str(exc)) from exc

    if args.command in {'preview-legacy-villages', 'copy-legacy-village', 'list-legacy-villages'}:
        from villagelife.persistence import legacy_launcher
        if args.command == 'preview-legacy-villages':
            result = legacy_launcher.preview(args.folder)
        elif args.command == 'copy-legacy-village':
            result = legacy_launcher.import_copy(args.folder, legacy_storage, args.key, args.fingerprint)
        else:
            result = legacy_launcher.saved_copies(legacy_storage)
        print(json.dumps(result, ensure_ascii=True)); return 0
    if args.command == 'stop-original-game':
        from villagelife.platforms.original_client import stop_game
        stop_game(binding); return 0
    if args.command == 'original-game-status':
        from villagelife.platforms.original_client import game_status
        print(game_status(binding)); return 0
    if args.command == 'check-bluestacks':
        bs.installation(); return 0
    if args.command == 'list-instances':
        rows = bs.list_instances()
        if args.eligible:
            from villagelife.persistence.legacy_launcher import saved_copies
            protected = {village.get('source_instance') for village in saved_copies(legacy_storage)}
            rows = [row for row in rows if row.id not in protected]
        print(json.dumps([vars(x) for x in rows], ensure_ascii=False)); return 0
    if args.command == 'bind-instance':
        selected = bs.select_by_id(bs.list_instances(), args.instance_id, check_live_port=False)
        protect_instance(selected.id)
        print(json.dumps(bs.bind_instance(binding, selected, bs.installation()), ensure_ascii=False)); return 0
    if args.command == 'verify-instance':
        selected = bs.verify_binding(binding, bs.list_instances(), bs.installation(),
                                     check_live_port=not args.selection_only)
        protect_instance(selected.id)
        print('Verified:', selected.id); return 0
    if args.command == 'start-instance':
        print('Started:', bs.start_bound_instance(binding, protect=protect_instance)); return 0
    if args.command == 'adb-check':
        print(json.dumps(bs.adb_status(binding, once=args.once))); return 0
    if args.command == 'open-instance-manager':
        bs.open_manager(); print('Opened Multi-instance Manager'); return 0
    if args.command == 'network-report':
        from villagelife.platforms.network import report
        print(json.dumps(report(binding), indent=2)); return 0
    if args.command == 'verify-network':
        from villagelife.platforms.network import report
        print(json.dumps(report(binding, guest_checks=True, local_port=args.port), indent=2)); return 0
    if args.command == 'export-support':
        from villagelife.support import export_support
        report_repo = None
        database_note = ''
        if args.db.is_file():
            try:
                report_repo = SqliteSaveRepository(args.db)
            except SaveSchemaError as exc:
                database_note = str(exc)
            except OSError:
                database_note = 'The save database could not be opened.'
        print('Created:', export_support(args.output, binding,
            launcher_version=args.launcher_version, manifest=args.build_manifest,
            repo=report_repo, database_note=database_note, adb_check=args.adb_check))
        return 0
    if args.command == 'install-prepared-client':
        from villagelife.platforms.original_client import install_prepared
        install_prepared(binding, args.apk, args.obb, replace=args.replace); print('Prepared client installed in the explicitly bound instance'); return 0
    if args.command == 'repair-prepared-obb':
        from villagelife.platforms.original_client import repair_prepared_obb
        repair_prepared_obb(binding, args.apk, args.obb); print('Expansion verified in the explicitly bound instance'); return 0
    if args.command == 'check-original-game':
        from villagelife.platforms.original_client import (existing_installation, prepared_apk_installed,
                                                          prepared_installation_ready)
        if args.apk:
            installed = prepared_apk_installed(binding, args.apk)
        elif args.prepared:
            installed = prepared_installation_ready(binding, args.obb, verify_hash=args.verify_hash)
        else:
            installed = existing_installation(binding)
        print(json.dumps({'package': 'com.playdemic.villagelife.android', 'installed': installed})); return 0
    if args.command == 'probe-guest-backend':
        from villagelife.platforms.original_client import probe_local_server
        probe_local_server(binding, args.port); print('Guest can reach the local backend (isolation remains unverified)'); return 0
    if args.command == 'launch-original-game':
        from villagelife.platforms.original_client import launch
        launch(binding, restart=args.restart); print('Village Life launch requested'); return 0
    if args.command == 'prepare-original-client':
        # The preparation tool is deliberately a separate executable module so
        # signing code is never imported by the normal server process.
        if getattr(sys, 'frozen', False):
            script = Path(getattr(sys, '_MEIPASS')) / 'tools' / 'prepare_original_client.py'
        else:
            script = Path(__file__).resolve().parents[2] / 'tools' / 'prepare_original_client.py'
        if not script.is_file():
            raise FileNotFoundError('Client preparation component is unavailable in this build')
        import runpy
        saved = sys.argv
        try:
            sys.argv = [str(script), '--xapk', str(args.xapk), '--output', str(args.output)]
            if args.java_home:
                sys.argv += ['--java-home', str(args.java_home)]
            if args.prepare_data:
                sys.argv.append('--prepare-data')
            try:
                runpy.run_path(str(script), run_name='__main__')
            except SystemExit as exc:
                return int(exc.code or 0)
        finally:
            sys.argv = saved
        return 0
    repo = SqliteSaveRepository(args.db)
    if args.command == 'list-local-villages':
        from villagelife.protocol.original_client.villages import list_local_villages
        print(json.dumps(list_local_villages(repo))); return 0
    if args.command == 'create-local-village':
        from villagelife.protocol.original_client.villages import create_local_village
        print(json.dumps(create_local_village(repo))); return 0
    if args.command == 'delete-local-village':
        from villagelife.protocol.original_client.villages import delete_local_village
        print(json.dumps(delete_local_village(repo, args.village_id,
                                              backup=args.backup))); return 0
    if args.command == 'delete-imported-village':
        from villagelife.protocol.original_client.villages import delete_imported_village
        print(json.dumps(delete_imported_village(repo, args.key,
                                                 storage=args.storage,
                                                 backup=args.backup))); return 0
    if args.command == 'restore-portable':
        from villagelife.protocol.original_client.villages import restore_portable_village
        print(json.dumps(restore_portable_village(repo, args.archive))); return 0
    if args.command == 'export-missing-requests':
        from villagelife.support import export_missing
        print('Created:', export_missing(repo, current_run_only=True)); return 0
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
    elif args.command in {'backup-db', 'compact-db'}:
        if args.output.exists():
            raise SaveBackupError('A recovery copy already exists at that path. '
                                  'Choose another name or keep the existing copy.')
        try:
            repo.backup_to(args.output)
        except (OSError, sqlite3.Error) as exc:
            raise SaveBackupError(
                'Could not create the recovery copy. Free disk space and check folder '
                'permissions, then retry. Your active save was not changed.') from exc
        if args.command == 'compact-db':
            from contextlib import closing
            with closing(sqlite3.connect(args.output)) as db:
                db.execute('VACUUM')
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise SaveBackupError('The compacted copy did not pass integrity '
                                          'verification. Keep the original save and retry.')
        print('Verified copy written:', args.output)
    elif args.command in {'list-gem-villages', 'add-local-gems'}:
        with repo.connect() as db:
            villages = db.execute("""
                SELECT village_id,
                       COALESCE(json_extract(payload_json, '$.originalSave.normal.user.name'), 'Local Village') AS name,
                       COALESCE(json_extract(payload_json, '$.originalSave.normal.user.userLevelID'), 0) AS level,
                       COALESCE(json_extract(payload_json, '$.originalSave.normal.inventory."323"'), 0) AS gems,
                       updated_at AS last_saved
                FROM villages WHERE json_type(payload_json, '$.originalSave.normal') = 'object'
                ORDER BY updated_at DESC, village_id
            """).fetchall()
        if args.command == 'list-gem-villages':
            print(json.dumps([dict(row) for row in villages]))
            return 0
        if not 1 <= args.amount <= 2_000_000_000:
            raise ValueError('Enter a whole number from 1 to 2,000,000,000.')
        if not villages:
            raise ValueError('Play through the tutorial to Woodland before adding gems.')
        if args.village_id is None and len(villages) != 1:
            raise ValueError(f'Found {len(villages)} Woodland villages. Select a village to add gems.')
        village_id = args.village_id or villages[0]['village_id']
        if not any(row['village_id'] == village_id for row in villages):
            raise ValueError('The selected Woodland village was not found.')

        def add_gems(payload):
            world = payload['originalSave'].get('normal')
            if not isinstance(world, dict):
                raise ValueError('Play through the tutorial to Woodland before adding gems.')
            stock = world['inventory']
            total = stock.get('323', 0) + args.amount
            if total > 2_000_000_000:
                raise ValueError('The resulting balance would exceed 2,000,000,000 gems.')
            stock['323'] = total
            return {'balance': total}

        _, result, _ = repo.mutate(village_id, operation_key=f'launcher:gems:{uuid.uuid4()}',
                                   request={'amount': args.amount}, change=add_gems)
        print(json.dumps(result))
    elif args.command == 'serve':
        if not 1 <= args.port <= 65535:
            parser.error('Port must be between 1 and 65535')
        from villagelife.transport.http_api import serve
        transport_key = None
        if args.transport_key_file:
            transport_key = args.transport_key_file.read_text(encoding='ascii').strip()
            if len(transport_key) != 12 or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in transport_key):
                raise ValueError('Prepared client capability is invalid. Run setup again.')
        if args.game_tables and not transport_key:
            raise ValueError('Prepared client capability is missing. Run setup with this launcher before playing.')
        try:
            repo.enable_history_storage()
        except (OSError, sqlite3.Error) as exc:
            raise SaveBackupError(
                'Could not create the one-time recovery copy before upgrading this save. '
                'Free disk space and check folder permissions, then click Play again. '
                'The existing save was not changed.') from exc
        original = assets = None
        if args.game_tables:
            from villagelife.protocol.original_client.catalog import OriginalDefinitions
            from villagelife.protocol.original_client.services import OriginalClientGame
            from villagelife.protocol.original_client.assets import ClientAssets
            original = OriginalClientGame(repo, OriginalDefinitions(args.game_tables),
                                          selected_village=args.local_village_id)
            if args.xapk or args.obb or args.inventory:
                assets = ClientAssets(xapk=args.xapk, obb=args.obb, inventory=args.inventory)
        elif args.xapk or args.obb or args.inventory or args.local_village_id:
            parser.error('--game-tables is required with original game resources')
        try:
            serve(repo, args.port, original=original, assets=assets, transport_key=transport_key)
        except OSError as exc:
            if exc.errno in {errno.EADDRINUSE, 10048} or getattr(exc, 'winerror', None) == 10048:
                raise bs.InstanceError('VL-SERVER-PORT-IN-USE',
                    f'Port {args.port} is held by another process. Close the program using it and click Play again.') from exc
            raise
    return 0


def run(argv: list[str] | None = None) -> int:
    # Preserve clear, supportable error codes without printing private paths or
    # raw player data when a Windows user triggers a diagnostic failure.
    try:
        return main(argv)
    except SaveSchemaError as exc:
        print('[VL-SAVE-SCHEMA-UNSUPPORTED] '+str(exc)[:500], file=sys.stderr)
        return 3
    except SaveBackupError as exc:
        print('[VL-SAVE-BACKUP-FAILED] '+str(exc)[:500], file=sys.stderr)
        return 3
    except bs.InstanceError as exc:
        print(str(exc), file=__import__('sys').stderr)
        return 2
    except (FileNotFoundError, FileExistsError, ValueError, InvalidAction) as exc:
        print('[VL-USER-ACTION] '+type(exc).__name__+': '+str(exc)[:300], file=__import__('sys').stderr)
        return 2
    except OSError as exc:
        print('[VL-IO-ERROR] Could not access a required file or service ('+type(exc).__name__+').', file=__import__('sys').stderr)
        return 3
    except subprocess.CalledProcessError:
        print('[VL-CLIENT-SIGNING-FAILED] The local Android signing tool rejected the prepared client. Check the selected JDK and retry.', file=__import__('sys').stderr)
        return 3


if __name__ == '__main__':
    raise SystemExit(run())
