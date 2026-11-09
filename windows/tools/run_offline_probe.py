"""Bounded original-game startup in the dedicated BlueStacks instance, offline."""
from pathlib import Path
import ctypes,datetime,hashlib,json,subprocess,time,zipfile,sys
ROOT=Path(__file__).resolve().parents[1]
ADB=Path('C:/Program Files/BlueStacks_nxt/HD-Adb.exe')
VM=Path('C:/Program Files/BlueStacks_nxt/BstkVMMgr.exe')
SERIAL='127.0.0.1:5565';INSTANCE='Pie64_1';PACKAGE='com.playdemic.villagelife.android'
SOURCE=next(ROOT.glob('*.xapk'));EXPECTED='8d25823b824ba766b38e53aedb74b270a0254e6bf3fbbcf1a858b090a66b5c08'
SECONDS=int(sys.argv[1]) if len(sys.argv)>1 else 45
assert 10<=SECONDS<=180
STAMP=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
SESSION=ROOT/'experiments'/('offline-startup-'+STAMP);SESSION.mkdir(parents=True)
WORK=ROOT/'analysis/runtime_inputs';WORK.mkdir(exist_ok=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()
def run(args,timeout=30,check=True):
 p=subprocess.run([str(x) for x in args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
 text=p.stdout.decode('utf-8',errors='replace')
 with (SESSION/'host_commands.log').open('a',encoding='utf-8') as f:
  f.write(json.dumps([str(x) for x in args])+'\n'+text+'\n')
 if check and p.returncode:raise RuntimeError(text)
 return text

def adb(*args,**kw):return run([ADB,'-s',SERIAL,*args],**kw)
assert not ctypes.windll.shell32.IsUserAnAdmin()
assert sha(SOURCE)==EXPECTED
result=dict(started_utc=STAMP,instance=INSTANCE,adb_serial=SERIAL,administrator=False,original_sha256_before=EXPECTED,game_modified=False,timeout_seconds=SECONDS)
network_off=False;job_scheduled=False
try:
 assert 'device' in adb('get-state')
 existing=adb('shell','pm','list','packages',PACKAGE).strip()
 with zipfile.ZipFile(SOURCE) as z:
  apk_name=next(n for n in z.namelist() if n.endswith('.apk'))
  obb_name=next(n for n in z.namelist() if n.endswith('.obb'))
  apk=WORK/'client-original-copy.apk';obb=WORK/Path(obb_name).name
  for name,dest in [(apk_name,apk),(obb_name,obb)]:
   with z.open(name) as src,dest.open('wb') as out:
    while block:=src.read(1048576):out.write(block)
 result['apk_sha256']=sha(apk);result['obb_sha256']=sha(obb)
 if existing:
  remote=adb('shell','pm','path',PACKAGE).strip().split('package:',1)[1]
  assert adb('shell','sha256sum',remote).split()[0]==sha(apk),'Existing app differs; refuse replacement.'
 else:
  text=adb('install',str(apk),timeout=90);assert 'Success' in text,text
 target='/sdcard/Android/obb/'+PACKAGE
 adb('shell','mkdir','-p',target)
 adb('push',str(obb),target+'/'+obb.name,timeout=90)
 result['installed_package_dump']=adb('shell','dumpsys','package',PACKAGE)
 adb('shell','am','force-stop',PACKAGE)
 guest='''#!/system/bin/sh
sleep 5
logcat -c
logcat -v threadtime > /data/local/tmp/vl-probe-logcat.txt 2>&1 &
LOGPID=$!
echo START_UTC=$(date -u)
am start -n com.playdemic.villagelife.android/com.playdemic.villagelife.android.VillageLife
for i in $(seq 1 45); do
  if grep -q -E 'FATAL EXCEPTION|Fatal signal [0-9]+' /data/local/tmp/vl-probe-logcat.txt; then
    echo FIRST_FATAL_DETECTED=$i
    break
  fi
  sleep 1
done
am force-stop com.playdemic.villagelife.android
echo STOP_UTC=$(date -u)
pidof com.playdemic.villagelife.android
kill $LOGPID
sleep 1
echo COMPLETE > /data/local/tmp/vl-probe-complete.txt
'''
 guest=guest.replace('seq 1 45','seq 1 '+str(SECONDS))
 local=SESSION/'guest-probe.sh';local.write_text(guest,encoding='utf-8',newline='\n')
 adb('push',str(local),'/data/local/tmp/vl-probe.sh')
 adb('shell','rm','-f','/data/local/tmp/vl-probe-complete.txt')
 adb('shell','nohup sh /data/local/tmp/vl-probe.sh > /data/local/tmp/vl-probe-job.txt 2>&1 < /dev/null &')
 job_scheduled=True
 run([VM,'controlvm',INSTANCE,'setlinkstate1','off']);network_off=True
 state=run([VM,'showvminfo',INSTANCE,'--machinereadable']);assert 'cableconnected1="off"' in state
 result['guest_network']='virtual NIC cable disconnected before delayed app launch'
 result['network_disconnected_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 (SESSION/'progress.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print('Offline bounded guest probe scheduled. Session: '+str(SESSION),flush=True)
 # Guest independently stops the app, closes its log and writes a completion marker.
 
 for _ in range((SECONDS+22)//10):time.sleep(10)
 run([VM,'controlvm',INSTANCE,'setlinkstate1','on']);network_off=False
 result['network_restored_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 run([ADB,'connect',SERIAL],check=False)
 for attempt in range(6):
  try:
   run([ADB,'disconnect',SERIAL],check=False)
   run([ADB,'connect',SERIAL],check=False)
   text=adb('shell','cat','/data/local/tmp/vl-probe-complete.txt',timeout=5)
   if 'COMPLETE' in text:break
  except (RuntimeError,subprocess.TimeoutExpired):pass
  time.sleep(2)
 else:raise RuntimeError('Offline probe completion was not confirmed; app cleanup required.')
 result['guest_job_complete']=True
 result['remaining_game_pids']=adb('shell','pidof',PACKAGE,check=False).strip()
 assert not result['remaining_game_pids']
 for remote,name in [('vl-probe-logcat.txt','logcat.txt'),('vl-probe-job.txt','guest_job.txt')]:
  adb('pull','/data/local/tmp/'+remote,str(SESSION/name))
 result['guest_job_output']=(SESSION/'guest_job.txt').read_text(errors='replace')
 result['status']='completed_offline_probe'
except Exception as exc:
 result['status']='probe_error';result['error']=str(exc)
 if job_scheduled:
  try:adb('shell','am','force-stop',PACKAGE,timeout=5,check=False)
  except Exception:pass
 raise
finally:
 if network_off:
  # Keep the offline guest offline until its independently scheduled stop deadline.
  if job_scheduled:time.sleep(58)
  run([VM,'controlvm',INSTANCE,'setlinkstate1','on'],check=False)
 result['original_sha256_after']=sha(SOURCE)
 result['original_unchanged']=result['original_sha256_after']==EXPECTED
 (SESSION/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 print(json.dumps({k:v for k,v in result.items() if k!='installed_package_dump'},indent=2),flush=True)
