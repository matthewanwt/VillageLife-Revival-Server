import unittest,threading,http.server,urllib.request
from online_relay import validate,make_server
class RelayTests(unittest.TestCase):
 def test_online_requires_https_and_does_not_accept_credentials_in_url(self):
  for url in ['http://example.invalid','https://user:password@example.invalid','https://example.invalid/?secret=x']:
   with self.assertRaises(ValueError):validate({'server_url':url,'join_code':'x'*43})
 def test_loopback_relay_adds_key_and_preserves_binary_body(self):
  captured=[]
  class Upstream(http.server.BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_POST(self):
    body=self.rfile.read(int(self.headers['Content-Length']));captured.append((self.headers.get('Authorization'),self.path,body));self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
  upstream=http.server.ThreadingHTTPServer(('127.0.0.1',0),Upstream);worker=threading.Thread(target=upstream.serve_forever,daemon=True);worker.start()
  relay=make_server({'server_url':'http://127.0.0.1:'+str(upstream.server_port),'join_code':'x'*43},port=0,allow_loopback_http=True);forwarder=threading.Thread(target=relay.serve_forever,daemon=True);forwarder.start()
  try:
   data=b'\x00\xffbinary';request=urllib.request.Request('http://127.0.0.1:'+str(relay.server_port)+'/web/ClientService/Process',data=data)
   with urllib.request.urlopen(request,timeout=5) as response:self.assertEqual(response.read(),data)
   self.assertEqual(captured,[('Bearer '+'x'*43,'/web/ClientService/Process',data)])
  finally:relay.shutdown();relay.server_close();upstream.shutdown();upstream.server_close();forwarder.join(5);worker.join(5)
if __name__=='__main__':unittest.main()
