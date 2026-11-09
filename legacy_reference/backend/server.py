"""Private local diagnostic service. Unknown game calls fail explicitly."""
from pathlib import Path
import argparse,csv,datetime,http.server,json,sqlite3,threading,time,urllib.parse,zipfile,io
from codec import decode,encode
from session import login,process
import community,session,player_access,social
ROOT=Path(__file__).resolve().parents[1]
class Server(http.server.ThreadingHTTPServer):
 daemon_threads=True
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def account(self):
  path=getattr(self.server,'access_file',None)
  return player_access.authenticate(path,self.headers.get('Authorization')) if path else None
 def record(self,item):
  if self.server.summary_logs:
   document=item.pop('document',None)
   if document is not None:
    item['services']=[c.get('service',c.get('Service','')) for c in document.get('data',{}).get('calls',document.get('Calls',[]))]
  item.update(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),path=self.path,host=self.headers.get('Host'))
  with self.server.log_lock:
   with self.server.log.open('a',encoding='utf-8') as f:f.write(json.dumps(item)+'\n')
 def reply(self,status,data,kind='application/octet-stream'):
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_GET(self):
  try:self.account()
  except PermissionError:self.reply(403,b'Online invitation rejected','text/plain');return
  path=urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
  if '..' in path.split('/'):self.reply(400,b'Invalid path');return
  if path=='/health':self.reply(200,b'local-village-service\n','text/plain');return
  if path.endswith('/envvars.txt'):
   self.record(dict(method='GET',served='local diagnostic environment marker',derived=True))
   self.reply(200,b'preservation_local=1\r\n','text/plain');return
  if path.endswith('/foldername.txt'):
   self.record(dict(method='GET',served='local folder map',derived=True))
   self.reply(200,b'foldernamea=local/\r\nfoldernamek=local/\r\n','text/plain');return
  if path.endswith('/quikmanifest.xml'):
   self.record(dict(method='GET',served='version-only shipped manifest',derived=True))
   self.reply(200,self.server.manifest.split(b'>',1)[0]+b'></manifest>','application/xml');return
  if path.endswith('/origmanifest.xml'):
   self.record(dict(method='GET',served='original shipped manifest',experimental_alias=path.endswith('/quikmanifest.xml')))
   self.reply(200,self.server.manifest,'application/xml');return
  key=path[path.find('files/'):] if 'files/' in path else path.lstrip('/')
  row=self.server.assets.get(key)
  if row:
   with self.server.obb.open('rb') as f:f.seek(int(row['offset_in_tcf']));data=f.read(int(row['stored_bytes']))
   self.record(dict(method='GET',served=key,bytes=len(data)));self.reply(200,data);return
  self.record(dict(method='GET',unimplemented=True));self.reply(404,b'<HTML>Not implemented</HTML>','text/html')
 def do_POST(self):
  self.request_started=time.monotonic()
  self.connection.settimeout(15)
  try:self.post_message()
  except PermissionError:self.reply(403,b'Online invitation rejected','text/plain')
  except (TimeoutError,ConnectionError,OSError) as ex:
   self.record(dict(method='TRANSPORT_ERROR',error=type(ex).__name__,message=str(ex)))
  except Exception as ex:
   self.record(dict(method='SERVER_ERROR',error=type(ex).__name__,message=str(ex)))
   self.reply(500,b'Local service error; check private server log','text/plain')
 def post_message(self):
  account=self.account()
  n=int(self.headers.get('Content-Length','0'))
  if n<=0 or n>8*1024*1024:self.reply(400,b'Invalid message length');return
  raw=self.rfile.read(n)
  try:document,mode=decode(raw)
  except Exception as ex:self.record(dict(method='POST',decode_error=str(ex),bytes=n));self.reply(400,b'Unknown request encoding');return
  if not isinstance(document,dict):self.reply(400,b'Request object required');return
  if account:document=player_access.bind(document,account)
  # Retain traffic privately; these are fresh local-test identifiers, never sent onward.
  self.record(dict(method='POST',transport=mode,document=document))
  if urllib.parse.urlsplit(self.path).path.rstrip('/')=='/Playdemic.Community.Web/Client/Home':
   try:
    if account:
     with session.LOCK:
      profile_path=session.profile_path(account['deviceId'])
      profile=json.loads(profile_path.read_text(encoding='utf-8')) if profile_path.exists() else session.login({'deviceId':account['deviceId'],'_accountName':account['name']})['data']['users'][0]
     own_id=social.public_id(profile)
     if str(document.get('UserId',0)) not in {'0',str(profile['pId']),own_id}:raise PermissionError('Player identity mismatch')
     response=community.process(document,{'Id':int(profile['pId']),'Name':account['name'],'GroupId':0,'IsAcceptingInvites':False,'XpLevel':profile.get('userLevelId',1)},lambda service,data:session.community_relationship_operation(profile,service,data))
    else:
     with session.LOCK:
      matches=[(p,s) for p,s in social.profiles(session.STATE).values() if str(p['pId'])==str(document.get('UserId'))]
     local_user=None
     if len(matches)==1:
      profile,saved=matches[0];local_user={'Id':int(profile['pId']),'Name':saved.get('normal',{}).get('user',{}).get('name','Local Village'),'GroupId':0,'IsAcceptingInvites':False,'XpLevel':saved.get('normal',{}).get('user',{}).get('userLevelID',1)}
     response=community.process(document,local_user,(lambda service,data:session.community_relationship_operation(profile,service,data)) if len(matches)==1 else None)
   except ValueError as ex:self.reply(400,str(ex).encode());return
   self.record(dict(method='RESPONSE',implemented='local community services; chat disabled',status=200,calls=[{'id':str(c.get('Id','')),'code':c['code'],'message':c.get('message','')} for c in response['data']]))
   self.reply(200,encode(response,compressed=mode=='zlib-xor'));return
  if urllib.parse.urlsplit(self.path).path.rstrip('/')=='/web/ClientService/Login':
   try:response=login(document)
   except ValueError as ex:self.reply(400,str(ex).encode());return
   self.record(dict(method='RESPONSE',implemented='fresh local session',status=200))
   self.reply(200,encode(response,compressed=mode=='zlib-xor'));return
  if urllib.parse.urlsplit(self.path).path.rstrip('/')=='/web/ClientService/Process':
   try:response=process(document,native_ids=True)
   except ValueError as ex:self.reply(400,str(ex).encode());return
   self.record(dict(method='RESPONSE',calls=[dict(id=c['id'],code=c['code'],message=c.get('message','')) for c in response['data']['calls']],elapsed_ms=round((time.monotonic()-self.request_started)*1000,2)))
   self.reply(200,encode(response,compressed=mode=='zlib-xor'));return
  self.reply(501,encode({'code':501,'message':'Local service contract not implemented yet','data':{}},compressed=mode=='zlib-xor'))

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=80);parser.add_argument('--seconds',type=int,default=600)
 parser.add_argument('--state-dir',type=Path);parser.add_argument('--log-dir',type=Path);parser.add_argument('--summary-logs',action='store_true');parser.add_argument('--access-file',type=Path);args=parser.parse_args()
 if args.access_file and not args.access_file.is_file():parser.error('Hosted invitation file is missing; refusing to start')
 if args.state_dir:session.STATE=args.state_dir.resolve()
 if args.seconds<0 or not 1<=args.port<=65535:parser.error('Invalid duration or port')
 out=(args.log_dir or ROOT/'experiments')/('local-service-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 with zipfile.ZipFile(next(ROOT.glob('*.xapk'))) as z:
  with zipfile.ZipFile(io.BytesIO(z.read('com.playdemic.villagelife.android.apk'))) as a:manifest=a.read('assets/origmanifest.xml')
 srv=Server(('127.0.0.1',args.port),Handler);srv.log=out/'requests.jsonl';srv.log_lock=threading.Lock();srv.manifest=manifest;srv.summary_logs=args.summary_logs or bool(args.access_file);srv.access_file=args.access_file
 srv.obb=next((ROOT/'analysis/runtime_inputs').glob('*.obb'))
 with (ROOT/'analysis/obb_tcf.inventory.csv').open(encoding='utf-8') as f:srv.assets={r['path']:r for r in csv.DictReader(f)}
 (out/'service.json').write_text(json.dumps(dict(bind='127.0.0.1',port=args.port,seconds=args.seconds,mode='diagnostic',remote_proxy=False,game_patch=False)),encoding='utf-8')
 timer=threading.Timer(args.seconds,srv.shutdown) if args.seconds>0 else None
 if timer:timer.daemon=True;timer.start()
 print('Local diagnostic service: '+str(out),flush=True)
 try:srv.serve_forever()
 finally:
  if timer:timer.cancel()
  srv.server_close()
if __name__=='__main__':main()
