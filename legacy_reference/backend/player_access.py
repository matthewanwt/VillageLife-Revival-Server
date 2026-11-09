"""Optional invitation-key gate for a hosted backend; local mode stays loopback-only."""
import copy,hashlib,json,secrets,uuid,os
from pathlib import Path

def provision(path,name):
 if not isinstance(name,str) or not name.strip() or len(name.encode('utf-8'))>64 or any(ord(c)<32 for c in name):raise ValueError('A short player name is required')
 path=Path(path);document=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'version':1,'accounts':{}}
 token=secrets.token_urlsafe(32);ident=hashlib.sha256(token.encode()).hexdigest();account={'deviceId':'hosted-'+uuid.uuid4().hex,'name':name.strip()}
 document['accounts'][ident]=account;path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix('.tmp')
 with temp.open('w',encoding='utf-8') as f:json.dump(document,f,indent=2);f.flush();os.fsync(f.fileno())
 os.replace(temp,path);return token,account

def authenticate(path,authorization):
 scheme,_,token=(authorization or '').partition(' ')
 if scheme.lower()!='bearer' or not 20<=len(token)<=512:raise PermissionError('Online invitation required')
 try:
  document=json.loads(Path(path).read_text(encoding='utf-8'));account=document['accounts'].get(hashlib.sha256(token.encode()).hexdigest())
  if not account or not isinstance(account.get('deviceId'),str) or not account['deviceId'].startswith('hosted-') or not isinstance(account.get('name'),str):raise PermissionError('Online invitation rejected')
  return dict(account)
 except (OSError,ValueError,KeyError,TypeError):raise PermissionError('Online access unavailable') from None

def bind(document,account):
 if not isinstance(document,dict):raise ValueError('Request object required')
 result=copy.deepcopy(document);result['deviceId']=account['deviceId'];result['_accountName']=account['name'];return result
