"""Allowlisted player distribution; optionally include the user-authorized original archive."""
from pathlib import Path
import datetime,hashlib,json,shutil,zipfile,re,argparse
ROOT=Path(__file__).resolve().parents[1]

def digest(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def copy(src,dst):dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--include-game',action='store_true');mode=parser.add_mutually_exclusive_group();mode.add_argument('--candidate',action='store_true',help='Build an unreleased validation candidate; never update shared release pointers');mode.add_argument('--field-test',action='store_true',help='Explicit second-PC test build; technical review required, native acceptance remains pending');args=parser.parse_args();include_game=args.include_game
 if args.field_test:
  from release_review import check_release
  blockers=check_release(ROOT,field_test=True)
  if blockers:raise RuntimeError('Field test technical checks failed: '+ '; '.join(blockers))
 elif not args.candidate:
  from release_review import assert_release
  assert_release(ROOT)
 version=json.loads((ROOT/'VERSION.json').read_text(encoding='utf-8'));base_version=version['restoration_version'].removesuffix('-dev');release_version=base_version+'-community-test'
 if not re.fullmatch(r'\d+\.\d+\.\d+-community-test',release_version):raise RuntimeError('Invalid source release version')
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'dist'/((('FIELD-TEST-' if args.field_test else 'CANDIDATE-' if args.candidate else '')+('VillageLife-Community-Complete-' if include_game else 'VillageLife-Community-Player-'))+stamp);out.mkdir(parents=True,exist_ok=False)
 private=json.loads((ROOT/'dist/latest-package.json').read_text(encoding='utf-8'));runtime=Path(private['folder'])/'runtime'
 if not runtime.is_dir():raise RuntimeError('Verified bundled runtime source missing')
 shutil.copytree(runtime,out/'runtime',ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pyo'))
 # Windows Python otherwise may discover the developer installation through the registry.
 dlls=[p for p in (out/'runtime/python').glob('python*.dll') if re.fullmatch(r'python[0-9]{2,3}\.dll',p.name)]
 if len(dlls)!=1:raise RuntimeError('Expected one versioned bundled Python runtime')
 (out/'runtime/python'/(dlls[0].stem+'._pth')).write_text('Lib\nDLLs\n.\n../../tools\n../../backend\nimport site\n',encoding='utf-8')
 for file in (ROOT/'backend').glob('*.py'):
  if not file.name.startswith('test_'):copy(file,out/'backend'/file.name)
 for name in ['play_local.py','network_check.py','setup_local.py','prepare_host.py','import_game.py','hosted_connection.py','online_relay.py','update_local.py','migrate_save.py']:copy(ROOT/'tools'/name,out/'tools'/name)
 copy(ROOT/'Update Village Life.cmd',out/'Update Village Life.cmd')
 copy(ROOT/'notes/REPORT_A_BUG.md',out/'REPORT A BUG.md')
 copy(ROOT/'Village Life.exe',out/'Village Life.exe')
 for file in (ROOT/'launcher/community-release').iterdir():
  if file.suffix.lower() in {'.dll','.exe','.json'}:copy(file,out/'StartVillageLife'/file.name)
 (out/'StartVillageLife/launcher.json').write_text(json.dumps({'python':'runtime/python/python.exe'},indent=2),encoding='utf-8')
 bundled_archive=None
 if include_game:
  from import_game import ARCHIVE_SHA
  original=next(ROOT.glob('*.xapk'))
  if digest(original)!=ARCHIVE_SHA:raise RuntimeError('Original game archive hash mismatch')
  bundled_archive=original.name;copy(original,out/bundled_archive)
 version.update(restoration_version=release_version,release_scope='Community field test; second-PC acceptance pending' if args.field_test else 'Community test; see START HERE.txt for limits',release_candidate=args.candidate,field_test=args.field_test,distribution=('complete player kit; original game archive included' if include_game else 'player-only; original game supplied by recipient'));(out/'VERSION.json').write_text(json.dumps(version,indent=2),encoding='utf-8')
 (out/'COMMUNITY-PACKAGE.json').write_text(json.dumps({'version':version['restoration_version'],'game_files_included':include_game,'personal_saves_included':False,'downloads_automatically':False,'setup_uses_recipients_original_xapk':not include_game,'included_game_archive':bundled_archive},indent=2),encoding='utf-8')
 instructions="""VILLAGE LIFE - START HERE

1. Extract the entire ZIP to a writable folder. Keep its support folders together.
2. Install BlueStacks5 from https://www.bluestacks.com/ if you do not have it.
3. In BlueStacks Multi-instance Manager, create a NEW dedicated Pie64-bit instance.
   Any display name works. Enable Android Debug Bridge in that instance's
   Settings > Advanced, then close that instance.
4. Open Village Life.exe and click Set Up Game. Choose your dedicated instance
   from the list. Select your own original Village
   Life241.0.5.270.0 XAPK when asked. The launcher checks its hash and prepares the
   required game files locally. The original XAPK is not modified.
5. When setup finishes, click Play / Restart. Keep the launcher open while playing.
   Stop ends the game/server. Future sessions use the same saved village.

Python and .NET are included. No Java, SDK, compiler or account login is needed.
Use a normal Windows account; do not run as administrator. Windows x64 only.
No Google/Facebook login is needed. Dismiss any offline sign-in error yourself.

THIS ZIP DOES NOT INCLUDE THE ORIGINAL GAME
Supply your own original XAPK. Supported archive SHA-256:
8d25823b824ba766b38e53aedb74b270a0254e6bf3fbbcf1a858b090a66b5c08
Do not share an installed/prepared player folder: it contains your local game copy,
save, signing files and connection details. Share this clean ZIP instead.

CURRENT TEST SCOPE
Offline play is the default. Online joining requires a host address and private
join code; public multiplayer and human-player relationships are not ready.
NPC dating uses the existing Community tab and Relationships inbox. A reply is
ready after20 seconds, but the original inbox checks about every2 minutes.
NPC wedding/move-in has development restart evidence; background replies,
breakup UI and later family flows still have incomplete native verification.
The gem-purchase + button remains a known crash. Use the building shop separately.
A missing action can still cause Connection Lost. Reopen through Play / Restart.

SETUP CONNECTIVITY
This build includes Setup Fix1: Android's network-test result is read explicitly,
and setup prints readiness progress and the last connection response.
On the reported BlueStacks5.22.288.1014 laptop, the external TCP probe succeeded
despite configured loopback NAT. If this happens, for a disconnected local test:
turn off this PC's Wi-Fi, unplug Ethernet, close the dedicated instance and retry
Set Up Game. Keep this PC disconnected throughout play. The local server runs on
this PC; an online host cannot be used with this workaround. This is a temporary
workaround; keeping the PC online while isolating this instance remains unresolved.
The runtime connection check remains enabled. Send any new error and the private
setup-network-check.json to the developer. No separate Setup Fix1 ZIP is needed.

SAVES AND UPDATES
EXISTING PLAYER: close the launcher/game and the Village Life BlueStacks instance.
Extract the new ZIP into a separate folder, then double-click Update Village Life.cmd.
Choose your OLD player folder. The updater creates a NEW upgraded player folder
beside the old one, copies your village/settings/local game files, checks save
repairs, and opens the new folder when ready. Use Village Life.exe THERE from now on.
The old installation and an independent save backup are retained. ROLLBACK.txt
explains recovery. Progress after updating is not merged backwards on rollback.
An interrupted or failed update never replaces your old installation. Keep any
staging folder for diagnosis; retry from the extracted update kit after fixing the
reported problem. An already completed new installation will not be overwritten.
The updater supports local villages; hosted villages require a separate host update.
Unrecorded past losses cannot be reconstructed. New players can use Set Up Game.
No developer save/settings are included. Automatic internet downloads are disabled.
Logs may contain local identifiers or join codes. Do not post them publicly;
report the action, exact error, build version and steps needed to reproduce it.
"""
 if include_game:
  instructions=instructions.replace("4. Open Village Life.exe and click Set Up Game. Choose your dedicated instance\n   from the list. Select your own original Village\n   Life241.0.5.270.0 XAPK when asked. The launcher checks its hash and prepares the\n   required game files locally. The original XAPK is not modified.","4. Open Village Life.exe and click Set Up Game. Choose your dedicated instance\n   from the list. The original game archive is included; no separate file selection\n   is needed. Setup verifies it and prepares the local copy. Allow time for setup.")
  instructions=instructions.replace("THIS ZIP DOES NOT INCLUDE THE ORIGINAL GAME\nSupply your own original XAPK. Supported archive SHA-256:","ORIGINAL GAME ARCHIVE INCLUDED\nThe included original archive is verified against SHA-256:")
  instructions=instructions.replace("Do not share an installed/prepared player folder: it contains your local game copy,\nsave, signing files and connection details. Share this clean ZIP instead.","Share this clean ZIP. A folder used for playing also contains that player's save,\nprivate signing files and any connection details; keep those files private.")
 if args.candidate:instructions='UNRELEASED VALIDATION CANDIDATE - DO NOT SHARE AS A FINISHED UPDATE\n\n'+instructions
 (out/'START HERE.txt').write_text(instructions,encoding='utf-8')

 entries={}
 for file in sorted(out.rglob('*')):
  if not file.is_file():continue
  relative=file.relative_to(out).as_posix();lower=relative.lower()
  permitted_archive=include_game and relative==bundled_archive and digest(file)==ARCHIVE_SHA
  if not permitted_archive and (file.suffix.lower() in {'.xapk','.apk','.obb','.sqlite','.pfx','.p12','.private','.so'} or any(x in lower for x in ['private_state/','experiments/','backups/','analysis/','test_','__pycache__','play-settings.json','requests.jsonl','key-password','signing-password'])):raise RuntimeError('Non-player or private content in community distribution: '+relative)
  entries[relative]={'sha256':digest(file),'bytes':file.stat().st_size}
 manifest={'version':version['restoration_version'],'builtUtc':stamp,'files':entries,'game_assets_included':include_game,'personal_data_included':False,'development_tools_included':False,'second_computer_tested':False}
 (out/'PACKAGE-MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');archive=out.with_suffix('.zip')
 with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as package:
  for relative in [*sorted(entries),'PACKAGE-MANIFEST.json']:package.write(out/relative,relative,compress_type=zipfile.ZIP_STORED if relative==bundled_archive else zipfile.ZIP_DEFLATED)
 with zipfile.ZipFile(archive) as package:
  if package.testzip() is not None:raise RuntimeError('Community archive integrity failure')
 record={'folder':str(out),'zip':str(archive),'sha256':digest(archive),'bytes':archive.stat().st_size,'files':len(entries),'game_files_included':include_game,'personal_data_included':False}
 if include_game:record['original_xapk_sha256']=ARCHIVE_SHA
 record['release_candidate']=args.candidate
 record['field_test']=args.field_test
 archive.with_suffix('.zip.sha256.txt').write_text(record['sha256']+'  '+archive.name+'\n',encoding='utf-8');(ROOT/'dist'/('latest-community-field-test.json' if args.field_test else 'latest-community-candidate.json' if args.candidate else 'latest-community-complete-package.json' if include_game else 'latest-community-package.json')).write_text(json.dumps(record,indent=2),encoding='utf-8');print(json.dumps(record),flush=True)
if __name__=='__main__':main()
