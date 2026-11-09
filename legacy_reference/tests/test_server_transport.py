import json,tempfile,threading,unittest,urllib.request
from pathlib import Path
from unittest.mock import patch
import codec,server,session
class TransportTests(unittest.TestCase):
 def test_summary_logs_hide_credentials_and_errors_record_cause_and_duration(self):
  with tempfile.TemporaryDirectory() as directory,patch.object(session,'STATE',Path(directory)/'state'):
   srv=server.Server(('127.0.0.1',0),server.Handler);srv.log=Path(directory)/'requests.jsonl';srv.log_lock=threading.Lock();srv.summary_logs=True
   worker=threading.Thread(target=srv.serve_forever,daemon=True);worker.start()
   try:
    def post(path,data):
     req=urllib.request.Request('http://127.0.0.1:'+str(srv.server_port)+path,data=codec.encode(data),method='POST')
     with urllib.request.urlopen(req,timeout=5) as response:return codec.decode(response.read())[0]
    profile=post('/web/ClientService/Login',{'deviceId':'private-device-value'})['data']['users'][0]
    result=post('/web/ClientService/Process',{**profile,'data':{'calls':[{'id':'4','service':'Unknown/Example','data':{}}]}})
    self.assertEqual(result['data']['calls'][0]['code'],501)
    text=srv.log.read_text();self.assertNotIn('private-device-value',text);self.assertNotIn(profile['sessionId'],text)
    response=[json.loads(line) for line in text.splitlines() if json.loads(line).get('calls')][-1]
    self.assertIn('Unknown/Example',response['calls'][0]['message']);self.assertGreaterEqual(response['elapsed_ms'],0)
   finally:srv.shutdown();srv.server_close();worker.join(5)
if __name__=='__main__':unittest.main()
