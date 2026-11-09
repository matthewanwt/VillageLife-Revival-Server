"""Own one local game session; never download/install or alter the source archive."""
from pathlib import Path
import subprocess,sys,time,datetime,json,ctypes,hashlib,shutil,threading,queue,urllib.request,urllib.error,socket,argparse,os
from hosted_connection import ssh_command
from network_check import inspect_network,assess_adb_probe,EXTERNAL_PROBE_COMMAND
from runtime_errors import VillageRuntimeError, initialize_utf8, report_error
from platforms.bluestacks.discovery import discover_bluestacks
from platforms.bluestacks.instances import available_instances, select_instance, validate_binding
from platforms.bluestacks.adb import ADBClient
from platforms.bluestacks.net_assurance import verify_guest_network
from platforms.bluestacks.ports import require_client_port
ROOT=Path(__file__).resolve().parents[1]
ADB=Path(os.environ.get('ProgramFiles',r'C:\Program Files'))/'BlueStacks_nxt/HD-Adb.exe'  # resolved at launch
SETTINGS=json.loads((ROOT/'play-settings.json').read_text(encoding='utf-8')) if (ROOT/'play-settings.json').exists() else {}
INSTANCE=SETTINGS.get('instance','Pie64_1');SERIAL='127.0.0.1:'+str(SETTINGS.get('adb_port',5565))
PLAYER=ADB.with_name('HD-Player.exe');PACKAGE='com.playdemic.villagelife.android'
EXPECTED='8d25823b824ba766b38e53aedb74b270a0254e6bf3fbbcf1a858b090a66b5c08'
FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)
HEALTH_STATUS=None
ADB_CLIENT=None
def say(text):print(text,flush=True)
def digest(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def adb(*args,timeout=15):
 if ADB_CLIENT is None:raise VillageRuntimeError('VL-ADB-NOT-READY','ADB adapter was not initialised.')
 result=ADB_CLIENT.command(*args,timeout=timeout)
 return result.code,result.output
def health():
 global HEALTH_STATUS
 try:
  with urllib.request.urlopen('http://127.0.0.1/health',timeout=2) as r:return r.read()==b'local-village-service\n'
 except urllib.error.HTTPError as ex:
  HEALTH_STATUS=ex.code;ex.close();return False
 except OSError:return False
def stop_process(p):
 if p and p.poll() is None:
  p.terminate()
  try:p.wait(5)
  except subprocess.TimeoutExpired:p.kill();p.wait(5)
def dependencies():
 global ADB, PLAYER, INSTANCE, SERIAL, ADB_CLIENT
 if os.name == 'nt' and ctypes.windll.shell32.IsUserAnAdmin():
  raise VillageRuntimeError('VL-ADMIN-USER','The launcher should run as a standard user.', 'Close it and reopen normally without Run as administrator.')
 if not SETTINGS.get('instance') or not SETTINGS.get('adb_port'):
  raise VillageRuntimeError('VL-SETUP-REQUIRED','A BlueStacks game instance has not been configured.','Click Set Up Game.')
 install=discover_bluestacks()
 selected=select_instance(available_instances(),SETTINGS.get('instance'))
 validate_binding(SETTINGS,selected,install)
 ADB,PLAYER=install.adb,install.player
 INSTANCE=selected['id'];SERIAL='127.0.0.1:'+str(selected['adb_port'])
 ADB_CLIENT=ADBClient(ADB,SERIAL)
 for relative in ['backend/server.py','analysis/private/game_tables.sqlite','analysis/obb_tcf.inventory.csv']:
  path=ROOT/relative
  if not path.exists():raise VillageRuntimeError('VL-RUNTIME-FILE-MISSING',f'Required runtime file missing: {relative}', 'Rebuild the private player package from the 2.11 source; do not copy private saves into Git.')
 archives=list(ROOT.glob('*.xapk'))
 if len(archives)!=1:
  raise VillageRuntimeError('VL-GAME-ARCHIVE-MISSING','Expected exactly one user-provided XAPK.','Select the supported original archive in Set Up Game.')
 archive=archives[0]
 if digest(archive)!=EXPECTED:
  raise VillageRuntimeError('VL-GAME-HASH','The supplied XAPK is not the verified supported version.','Select the original supported release; no file has been changed.')
 return archive

def main():
 initialize_utf8()
 parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--smoke-test',type=int,default=0);parser.add_argument('--test-state',type=Path);args=parser.parse_args()
 if args.test_state:
  args.test_state=args.test_state.resolve()
  if not args.test_state.is_relative_to((ROOT/'experiments').resolve()) or not 1<=args.smoke_test<=900 or SETTINGS.get('server_mode','local')!='local':raise RuntimeError('Disposable test state requires local mode, an experiments subfolder and a timeout of1-900 seconds.')
 x=dependencies();say('Original archive verified. Dependencies ready.')
 if args.check:return
 require_client_port(80)
 out=ROOT/'experiments'/('play-session-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));out.mkdir(parents=True)
 state_dir=args.test_state or ROOT/'backend/private_state'
 state_dir.mkdir(parents=True,exist_ok=True)
 if args.test_state:
  shutil.copytree(state_dir,out/'save-before')
  snapshot=out/'save-before'
 else:
  snapshot=ROOT/'backups'/out.name
  snapshot.parent.mkdir(parents=True,exist_ok=True)
  shutil.copytree(state_dir,snapshot)
 (out/'backup-location.txt').write_text(str(snapshot),encoding='utf-8')
 say('Local save backed up. Logs: '+str(out))
 backend=None;log_thread=None;backend_log_thread=None;logstop=threading.Event();commands=queue.Queue();game_started=False
 def read_commands():
  for line in sys.stdin:commands.put(line.strip())
  commands.put('stop')
 def capture():
  logpath=out/'android.log'
  with logpath.open('ab') as log:
   while not logstop.is_set():
    if logpath.stat().st_size >= 8*1024*1024:
     say('Android log reached 8 MiB per-session limit; further Android logging paused. Save and gameplay continue.')
     break
    p=subprocess.Popen([str(ADB),'-s',SERIAL,'logcat','-v','threadtime'],stdout=log,stderr=subprocess.STDOUT,creationflags=FLAGS)
    while not logstop.wait(.5) and p.poll() is None:
     if logpath.stat().st_size >= 8*1024*1024:break
    stop_process(p)
    if not logstop.is_set() and logpath.stat().st_size<8*1024*1024:
     log.write(b'\n[Launcher restarted Android log capture after EOF]\n');log.flush();logstop.wait(1)

 def capture_backend(stream, path):
  # Drain the child pipe even after the cap, so its stdout can never stall the server.
  with path.open('wb') as output:
   remaining=8*1024*1024
   while True:
    chunk=stream.read1(8192)
    if not chunk:break
    if remaining>0:
     portion=chunk[:remaining];output.write(portion);remaining-=len(portion)
     if remaining==0:output.write(b'\n[VL: backend log limit reached; remaining output omitted]\n')

 try:
   mode=SETTINGS.get('server_mode','local')
   if mode not in {'local','ssh','online'}:raise VillageRuntimeError('VL-CONNECTION-MODE','Unknown server mode.','Select Local or Online in Connection settings.')
   command=ssh_command(SETTINGS) if mode=='ssh' else [sys.executable,'-u',str(ROOT/'tools/online_relay.py')] if mode=='online' else [sys.executable,'-u',str(ROOT/'backend/server.py'),'--seconds','0']
   if args.test_state:command+=['--state-dir',str(state_dir)]
   backend=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=FLAGS)
   backend_log_thread=threading.Thread(target=capture_backend,args=(backend.stdout,out/'backend.log'),daemon=True)
   backend_log_thread.start()
   for _ in range(60):
    if health():break
    if mode=='online' and HEALTH_STATUS in {401,403}:raise VillageRuntimeError('VL-ONLINE-AUTH','The online server rejected the join code.','Check the host HTTPS address and private join code in Connection settings.')
    if backend.poll() is not None:raise VillageRuntimeError('VL-BACKEND-EXIT','The local backend exited before it became ready.','Export diagnostics; inspect backend.log privately.')
    time.sleep(.25)
   else:raise VillageRuntimeError('VL-BACKEND-TIMEOUT','The local backend did not answer its health check.','Check port 80 and backend.log; export diagnostics.')
   say('Disposable village test; automatic stop after '+str(args.smoke_test)+' seconds.') if args.test_state else None
   say('Disposable local server ready.' if args.test_state else ('Private hosted connection' if mode in {'ssh','online'} else 'Local server')+' ready; no fixed play-time limit.')
   subprocess.Popen([str(PLAYER),'--instance',INSTANCE],creationflags=FLAGS)
   ADB_CLIENT.wait_for_boot(deadline_seconds=300,progress=say)
   code,text=adb('shell',"printf 'GET /health HTTP/1.0\\r\\n\\r\\n' | toybox nc -w 3 10.0.2.2 80")
   if code or 'local-village-service' not in text:raise VillageRuntimeError('VL-NET-LOCAL-ROUTE','The Android client cannot reach the Windows localhost server at 10.0.2.2:80.','Check whether another app is using port 80, whether BlueStacks NAT is configured for host loopback, and export diagnostics.',details=text[:350])
   network=verify_guest_network(ADB_CLIENT,INSTANCE)
   (out/'network-check.json').write_text(json.dumps(network,indent=2,ensure_ascii=False),encoding='utf-8')
   if not network['isolated']:
    raise VillageRuntimeError('VL-NET-EGRESS',network['reason'],
     'Guest external access is not blocked or the test was inconclusive. No game launched. Export diagnostics; do not disable the network guard.',
     details=str(out/'network-check.json'))
   (out/'environment.json').write_text(json.dumps({'administrator':False,'source_sha256_before':EXPECTED,'instance':INSTANCE,'external_tcp':network['reason'],'backend_seconds':0,'server_mode':mode,'disposable_test_state':bool(args.test_state)},indent=2))
   adb('shell','am','force-stop',PACKAGE)
   adb('logcat','-c')
   log_thread=threading.Thread(target=capture,daemon=True);log_thread.start()
   code,text=adb('shell','am','start','-n',PACKAGE+'/'+PACKAGE+'.VillageLife')
   if code or 'Error:' in text or 'Error type' in text:raise VillageRuntimeError('VL-APK-LAUNCH','Android could not launch the Village Life activity.','Verify that the correct signed game APK is installed in the selected instance.',details=text.strip()[:350])
   game_started=True;say('Game started. Keep this launcher open. Restart Game recovers a closed game.')
   if not args.smoke_test:threading.Thread(target=read_commands,daemon=True).start()
   started=time.monotonic();last_check=0;was_alive=True;misses=0
   while True:
    try:command=commands.get(timeout=.25)
    except queue.Empty:command=''
    if args.test_state and (args.test_state.parent/'STOP').exists():break
    if command=='stop' or args.smoke_test and time.monotonic()-started>=args.smoke_test:break
    if command=='restart':
     adb('shell','am','force-stop',PACKAGE);adb('shell','am','start','-n',PACKAGE+'/'+PACKAGE+'.VillageLife');was_alive=True;misses=0;say('Game restarted from its saved village.')
    if backend.poll() is not None:raise VillageRuntimeError('VL-BACKEND-CRASH','The backend exited while playing, so the game was stopped to protect the session.','Your save backup is retained. Export diagnostics.')
    if time.monotonic()-last_check>5:
     last_check=time.monotonic();alive=bool(adb('shell','pidof',PACKAGE)[1].strip())
     misses=0 if alive else misses+1
     if was_alive and misses>=2:say('Game process closed. Logs retained. Use Play / Restart to reopen it.');was_alive=False
     elif not was_alive and alive:say('Game is running again.');was_alive=True
 finally:
  say('Stopping game and local server...')
  if game_started:
   try:adb('shell','am','force-stop',PACKAGE)
   except Exception as ex:say('Warning: could not force-stop Android client: '+type(ex).__name__)
  logstop.set()
  if log_thread:log_thread.join(8)
  stop_process(backend)
  if backend_log_thread:backend_log_thread.join(4)
  after=digest(x);(out/'result.json').write_text(json.dumps({'source_sha256_after':after,'source_unchanged':after==EXPECTED,'game_started':game_started,'server_mode':SETTINGS.get('server_mode','local'),'remaining_game_pids':adb('shell','pidof',PACKAGE)[1].strip() if game_started else ''},indent=2),encoding='utf-8')
  say('Stopped. Save retained. BlueStacks itself remains open.')
if __name__=='__main__':
 try:main()
 except Exception as ex:report_error(ex,report_file=ROOT/'latest-runtime-error.json');sys.exit(1)
