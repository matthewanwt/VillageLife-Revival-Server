"""Prepare a user-created, dedicated BlueStacks test instance from a private package."""
from pathlib import Path
import sys,os,re,json,subprocess,time,zipfile,hashlib,ctypes,argparse
from prepare_host import prepare
from network_check import inspect_network,assess_adb_probe,EXTERNAL_PROBE_COMMAND
from platforms.bluestacks.discovery import discover_bluestacks
from platforms.bluestacks.instances import available_instances as _available_instances, select_instance as _select_instance, make_binding
from platforms.bluestacks.adb import ADBClient
from platforms.bluestacks.net_assurance import verify_guest_network
from runtime_errors import VillageRuntimeError, initialize_utf8, report_error
ROOT=Path(__file__).resolve().parents[1];PROGRAM=Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'BlueStacks_nxt';ADB=PROGRAM/'HD-Adb.exe';MANAGER=PROGRAM/'BstkVMMgr.exe'
ARCHIVE_SHA='8d25823b824ba766b38e53aedb74b270a0254e6bf3fbbcf1a858b090a66b5c08';APK_SHA='fe069e9d4236e5812b84574bd9a578cb861e7aa92183973e3142021e43c9225b'
PACKAGE='com.playdemic.villagelife.android';OBB='main.241.'+PACKAGE+'.obb';FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)
def digest(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(args):
 p=subprocess.run([str(v) for v in args],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=180,creationflags=FLAGS)
 if p.returncode:raise RuntimeError((p.stdout+p.stderr).strip())
 return p.stdout

def package_installed(serial):
 p=subprocess.run([str(ADB),'-s',serial,'shell','pm','path',PACKAGE],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=30,creationflags=FLAGS)
 if p.returncode==1 and not (p.stdout+p.stderr).strip():return False
 if p.returncode:raise RuntimeError((p.stdout+p.stderr).strip() or 'Unable to query installed app')
 return 'package:' in p.stdout

def available_instances(text=None):
    return _available_instances(text)


def select_instance(instances, selection):
    return _select_instance(instances, selection)

def main():
 initialize_utf8()
 parser=argparse.ArgumentParser();parser.add_argument('--check-only',action='store_true');parser.add_argument('--yes',action='store_true');parser.add_argument('--source',type=Path);parser.add_argument('--list-instances',action='store_true');parser.add_argument('--instance');args=parser.parse_args()
 if args.list_instances:
  sys.stdout.reconfigure(encoding='utf-8');print(json.dumps(available_instances(),ensure_ascii=False));return
 if ctypes.windll.shell32.IsUserAnAdmin():raise RuntimeError('Run normally, without administrator privileges.')
 community=(ROOT/'COMMUNITY-PACKAGE.json').exists()
 if community:
  from import_game import prepare_game
  sources=list(ROOT.glob('*.xapk'))
  source=args.source or (sources[0] if len(sources)==1 else None)
  if source is None:raise RuntimeError('Use Set Up Game and select your own original Village Life XAPK.')
  prepare_game(source,ROOT)
 sources=list(ROOT.glob('*.xapk'))
 if len(sources)!=1:raise VillageRuntimeError('VL-GAME-ARCHIVE-MISSING','Expected exactly one supported original XAPK.','Choose the file in Set Up Game; no player save has been changed.')
 x=sources[0];apk=ROOT/'analysis/local-client/local-service-client.apk'
 expected_apk=APK_SHA
 if community:
  receipt=json.loads((apk.parent/'changes.json').read_text(encoding='utf-8'))
  if receipt.get('source_sha256')!='37f4ac5ee3b46133a1aeb14d1ca78975a64dc600c6d9d17fb99717d6cf532a71' or not receipt.get('local_player_generated'):raise RuntimeError('Local game preparation receipt mismatch')
  expected_apk=receipt['output_sha256']
 if digest(x)!=ARCHIVE_SHA or digest(apk)!=expected_apk:raise RuntimeError('Game input hash mismatch; setup stopped.')
 target=prepare(ROOT)
 if args.check_only:print('Package inputs and original expansion file verified.');return
 global ADB, MANAGER, PROGRAM
 installation=discover_bluestacks(require_manager=True)
 PROGRAM=installation.directory;ADB=installation.adb;MANAGER=installation.manager
 settings_path=ROOT/'play-settings.json'
 previous=json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.exists() else {}
 selected=select_instance(available_instances(),args.instance or previous.get('instance'))
 instance=selected['id'];port=selected['adb_port']
 info=run([MANAGER,'showvminfo',instance,'--machinereadable'])
 if 'VMState="poweroff"' not in info:raise RuntimeError('Close the selected '+instance+' instance in Multi-instance Manager, then run setup again.')
 print('Target: '+instance+' / '+ascii(selected['name'])+'. No other instance will be changed.')
 if not args.yes:input('Press Enter to configure NAT host routing and install this private game copy. NAT settings do not prove isolation; the guest egress checks must pass. Ctrl+C to cancel: ')
 if 'nic1="nat"' not in info:raise RuntimeError('Dedicated instance network adapter 1 must use NAT; setup will not replace another network configuration.')
 run([MANAGER,'modifyvm',instance,'--nat-bind-ip1=127.0.0.1','--nat-localhostreachable1=on'])
 network=inspect_network(instance)
 (ROOT/'setup-network-check.json').write_text(json.dumps({'instance':instance,'config':network},indent=2),encoding='utf-8')
 if not network['verified']:raise RuntimeError('The dedicated instance did not retain its local network settings: '+network['reason']+'. See setup-network-check.json; installed game data was not changed.')
 subprocess.Popen([str(PROGRAM/'HD-Player.exe'),'--instance',instance],creationflags=FLAGS)
 serial='127.0.0.1:'+str(port)
 def adb(*v):return run([ADB,'-s',serial,*v])
 client = ADBClient(ADB, serial)
 print('Waiting for the selected Android instance to boot. Slow devices get multiple retries.', flush=True)
 client.wait_for_boot(deadline_seconds=300, progress=lambda message: print(message, flush=True))
 # A verified VM NAT configuration is insufficient on some BlueStacks releases.
 # Test egress while Wi-Fi is ON; never skip a failed or inconclusive probe.
 checked = verify_guest_network(client, instance, config=inspect_network(instance))
 checked['instance'] = instance
 (ROOT/'setup-network-check.json').write_text(json.dumps(checked,indent=2,ensure_ascii=False),encoding='utf-8')
 if not checked['isolated']:
  raise VillageRuntimeError('VL-NET-EGRESS', checked['reason'],
    'BlueStacks has not been proven isolated with Wi-Fi enabled. No game was changed. Export diagnostics; ask the developer to test an instance-scoped firewall policy. Do not bypass this check.')
 if package_installed(serial):
  installed=adb('shell','pm','path',PACKAGE).strip().removeprefix('package:')
  installed_hash=adb('shell','sha256sum',installed).split()[0]
  if installed_hash!=expected_apk:raise RuntimeError('A different game copy is already installed. Its data was preserved. Use a fresh dedicated instance.')
  print('The correct game is already installed; keeping its data.')
 else:adb('install','-g',str(apk))
 adb('shell','mkdir','-p','/sdcard/Android/obb/'+PACKAGE)
 adb('push',str(target),'/sdcard/Android/obb/'+PACKAGE+'/'+OBB)
 (ROOT/'backend/private_state').mkdir(exist_ok=True,parents=True)
 settings_path=ROOT/'play-settings.json'
 settings=json.loads(settings_path.read_text(encoding='utf-8')) if settings_path.exists() else {}
 settings.update(instance=instance,instance_display_name=selected['name'],adb_port=port,instance_binding=make_binding(selected,installation));settings_path.write_text(json.dumps(settings,indent=2,ensure_ascii=False),encoding='utf-8')
 print('Setup complete. Return to the launcher and click Play / Restart. Do not sign in to Google or Facebook. If Google shows an offline sign-in error, dismiss it yourself with Back.')
if __name__=='__main__':
 try:main()
 except Exception as ex:report_error(ex,report_file=ROOT/'latest-runtime-error.json');sys.exit(1)
