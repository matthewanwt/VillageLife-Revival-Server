"""Loopback relay: the old game uses local HTTP; only this process uses remote HTTPS."""
from pathlib import Path
import argparse,http.server,json,urllib.request,urllib.parse,urllib.error,socket

def validate(config,allow_loopback_http=False):
 url=config.get('server_url','').rstrip('/');parts=urllib.parse.urlsplit(url)
 if parts.username or parts.password or parts.query or parts.fragment or not parts.hostname:raise ValueError('Enter a server HTTPS address without credentials or query parameters')
 if parts.scheme!='https' and not (allow_loopback_http and parts.scheme=='http' and parts.hostname in {'127.0.0.1','localhost'}):raise ValueError('Online play requires HTTPS')
 key=config.get('join_code','')
 if not isinstance(key,str) or not 20<=len(key)<=512 or any(ord(c)<33 or ord(c)>126 for c in key):raise ValueError('A valid private join code is required')
 return url,key
class Relay(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,code,data,kind='application/octet-stream'):
  self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def forward(self):
  if not self.path.startswith('/') or '..' in urllib.parse.unquote(self.path).split('/'):self.reply(400,b'Invalid path');return
  raw=None
  if self.command=='POST':
   try:n=int(self.headers.get('Content-Length','0'))
   except ValueError:self.reply(400,b'Invalid length');return
   if not 0<n<=8*1024*1024:self.reply(400,b'Invalid length');return
   self.connection.settimeout(15);raw=self.rfile.read(n)
  req=urllib.request.Request(self.server.upstream+self.path,data=raw,method=self.command,headers={'Authorization':'Bearer '+self.server.join_code,'Content-Type':self.headers.get('Content-Type','application/octet-stream')})
  try:
   with urllib.request.urlopen(req,timeout=20) as response:self.reply(response.status,response.read(),response.headers.get('Content-Type','application/octet-stream'))
  except urllib.error.HTTPError as ex:
   with ex:self.reply(ex.code,ex.read(),ex.headers.get('Content-Type','application/octet-stream'))
  except (OSError,TimeoutError):self.reply(502,b'Online server unavailable; check the launcher','text/plain')
 def do_GET(self):self.forward()
 def do_POST(self):self.forward()
def make_server(config,port=80,allow_loopback_http=False):
 upstream,key=validate(config,allow_loopback_http);server=http.server.ThreadingHTTPServer(('127.0.0.1',port),Relay);server.daemon_threads=True;server.upstream=upstream;server.join_code=key;return server
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--settings',type=Path,default=Path(__file__).resolve().parents[1]/'play-settings.json');args=parser.parse_args()
 config=json.loads(args.settings.read_text(encoding='utf-8'));server=make_server(config)
 print('Private online connection ready. Join code is not logged.',flush=True)
 try:server.serve_forever()
 finally:server.server_close()
if __name__=='__main__':
 try:main()
 except Exception as ex:print('ONLINE CONNECTION: '+str(ex),flush=True);raise SystemExit(1)
