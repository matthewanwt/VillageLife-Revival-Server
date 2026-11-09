"""Allowlisted private BlueStacks kit. No user saves, keys, logs or independent runtime."""
from pathlib import Path
import sys,shutil,datetime,json,hashlib,zipfile,struct
ROOT=Path(__file__).resolve().parents[1]
def digest(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def copy(src,dst):dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
def main():
 assert struct.calcsize('P')==8,'Use64-bit Python'
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'dist'/('VillageLife-Windows-PrivateTest-'+stamp);out.mkdir(parents=True)
 original=next(ROOT.glob('*.xapk'));assert digest(original)=='8d25823b824ba766b38e53aedb74b270a0254e6bf3fbbcf1a858b090a66b5c08'
 apk=ROOT/'analysis/local-client/local-service-client.apk';assert digest(apk)=='fe069e9d4236e5812b84574bd9a578cb861e7aa92183973e3142021e43c9225b'
 for file in (ROOT/'backend').glob('*.py'):copy(file,out/'backend'/file.name)
 for relative in ['analysis/private/game_tables.sqlite','analysis/obb_tcf.inventory.csv','analysis/local-client/local-service-client.apk','tools/play_local.py','tools/network_check.py','tools/make_test_village.py','tools/setup_local.py','tools/prepare_host.py','tools/feature_audit.py','tools/audit_dashboard.py','Check Game Features.cmd','analysis/libpdandroid.so.symbols.csv','analysis/server_contracts.json','notes/FEATURE_TEST_SYSTEM.md','notes/FIRE_SHELTER_BATCH.md','notes/FUN_NEEDS_BATCH.md','notes/STARTER_TOOL_RECOVERY.md','notes/FAMILY_BATCH.md','notes/NPC_DATING_BATCH.md','VERSION.json','tools/hosted_connection.py','tools/online_relay.py','tools/manage_host.py','tools/manage_friends.py','notes/BLUESTACKS_AND_HOSTING.md','Village Life.exe']:
  copy(ROOT/relative,out/relative)
 for file in (ROOT/'tools').glob('test_*.py'):copy(file,out/'tools'/file.name)
 copy(original,out/original.name)
 for file in (ROOT/'launcher/release').iterdir():
  if file.suffix.lower() in {'.exe','.dll','.json'}:copy(file,out/'StartVillageLife'/file.name)
 (out/'StartVillageLife/launcher.json').write_text(json.dumps({'python':'runtime/python/python.exe'},indent=2),encoding='utf-8')
 python=Path(sys.executable).parent;pdst=out/'runtime/python';pdst.mkdir(parents=True)
 for file in python.iterdir():
  if file.is_file() and (file.suffix in {'.exe','.dll'} or file.name.startswith('LICENSE')):copy(file,pdst/file.name)
 shutil.copytree(python/'DLLs',pdst/'DLLs',ignore=shutil.ignore_patterns('__pycache__'))
 shutil.copytree(python/'Lib',pdst/'Lib',ignore=shutil.ignore_patterns('site-packages','__pycache__','test','tests','idlelib','tkinter','turtledemo'))
 dotnet=Path(r'C:\Program Files\dotnet');ndst=out/'runtime/dotnet'
 for relative in ['dotnet.exe','LICENSE.txt','ThirdPartyNotices.txt']:
  if (dotnet/relative).is_file():copy(dotnet/relative,ndst/relative)
 for relative in ['host/fxr/10.0.11','shared/Microsoft.NETCore.App/10.0.11','shared/Microsoft.WindowsDesktop.App/10.0.11']:shutil.copytree(dotnet/relative,ndst/relative)
 (out/'START HERE.txt').write_text("""VILLAGE LIFE - PRIVATE WINDOWS TEST KIT
Extract the complete ZIP to a writable folder. Open Village Life.exe.

FIRST USE
1. Install BlueStacks5 from https://www.bluestacks.com/ if needed.
2. Create a NEW Pie64-bit instance named Village Life Preservation.
3. Enable Android Debug Bridge in that instance's Settings > Advanced.
4. Close that instance, then click Set Up Game in the Village Life launcher.
5. When setup finishes, click Play / Restart. No Google/Facebook login is required.
If Google shows an offline sign-in error, dismiss it yourself with Back.

DAILY PLAY
Open Village Life.exe and keep the launcher open. Stop closes the game and server.
BlueStacks itself stays open. There is no fixed play-time limit.
Python and .NET are included; BlueStacks is installed separately. Windows x64 only.
There are no independent Android runtime downloads in this kit.

SAVES AND CONNECTION
This kit starts a new village. The sender's progress, identifiers, logs and keys are
excluded. Backups are saved before play. Keep detailed logs and join codes private.
Offline is the default. Connection accepts an invited HTTPS server and join code.
Local and online villages are separate; switching modes does not merge them.
A host and two-computer multiplayer test are still required. See the included notes.

FEATURE CHECKS
Check Game Features.cmd runs disposable server tests and opens a searchable local
coverage checklist. It does not operate the game or change your village.
A recipe pass does not prove in-game UI or progression. See FEATURE_TEST_SYSTEM.md
in notes/. Original compiled script names and task rows include unused content.

FIXES AND LIMITS
The recurring five-minute KeepActive error is fixed and verified in BlueStacks.
Direct food/water wishes, creche finishing and dance happiness fixes are included.
Fire/oil persistence, shelter building/occupancy and shared fractional gem prices
are implemented. See notes/FIRE_SHELTER_BATCH.md for verified scope and limits.
Owned-building wishes and current-age client projection are corrected.
CrÃ¨che entry is not yet reliably verified in ordinary play; see FUN_NEEDS_BATCH.md
in notes/. The completion matrix does not prove every native activity works.
An explicit local fallback replaces exhausted uncraftable starter tools when
loading or collecting a task; partial tools are preserved. See STARTER_TOOL_RECOVERY.md.
VERSION.json identifies this restoration build. Stop/close the launcher before
upgrading an existing kit; retain its saves and settings. Backups occur before play.
Other missing server operations can still produce a connection error.
The gem + purchase screen is a known crash; do not use it. Building shop is separate.
Friends/read-only visits have tested server support, not full live multiplayer.
Pregnancy/birth, family profiles and naming have server support and live checks.
Disposable test-village creation is included; see notes/FAMILY_BATCH.md.
Local NPC dating works through the original Community tab and Relationships inbox.
Replies are ready after20 seconds but the original inbox refreshes every2 minutes.
Marriage/move-in, breakup, human-player dating, chat and gifts remain incomplete.
See notes/NPC_DATING_BATCH.md for numeric identity projection and tested scope.
This package contains proprietary game inputs. Keep it private; do not publish it.
""",encoding='utf-8')
 entries={}
 for file in sorted(out.rglob('*')):
  if not file.is_file():continue
  relative=file.relative_to(out).as_posix()
  if any(part in relative for part in ['private_state/','retired-independent','runtime-lab','IndependentPlay','key-password','local-test-only.p12','requests.jsonl','play-settings.json','player-access.json','invite.json','.tutorial.json']):raise RuntimeError('Private or retired file in package: '+relative)
  entries[relative]={'sha256':digest(file),'bytes':file.stat().st_size}
 manifest={'restoration_version':json.loads((ROOT/'VERSION.json').read_text(encoding='utf-8'))['restoration_version'],'buildUtc':stamp,'personal_save_included':False,'keys_included':False,'independent_runtime_included':False,'second_pc_tested':False,'full_multiplayer_verified':False,'files':entries}
 (out/'PACKAGE-MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
 archive=out.with_suffix('.zip')
 with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
  for relative in [*sorted(entries),'PACKAGE-MANIFEST.json']:
   file=out/relative;z.write(file,relative,compress_type=zipfile.ZIP_STORED if file.suffix=='.xapk' else zipfile.ZIP_DEFLATED)
 with zipfile.ZipFile(archive) as z:assert z.testzip() is None
 sha=digest(archive);archive.with_suffix('.zip.sha256.txt').write_text(sha+'  '+archive.name+'\n',encoding='utf-8')
 result={'folder':str(out),'zip':str(archive),'bytes':archive.stat().st_size,'sha256':sha,'files':len(entries)}
 (ROOT/'dist/latest-package.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
