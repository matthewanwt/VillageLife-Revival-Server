"""Native friend-list/read-only visit contracts. Operator-linked private testing only."""
from pathlib import Path
from contextlib import closing
import hashlib,json,re,sqlite3,time
import world
SERVICES={'ClientFriendService/GetFriends','ClientFriendService/GetApplicationFriends','ClientFriendService/GetFriendStartupInfo','ClientFriendService/GetFriendStartupInfoForExtras'}
def public_id(profile):
 ident=str(profile['pId'])
 # The native application-friend parser skips identifiers of length one.
 return ident if len(ident)>1 else str(10**14+int(hashlib.sha256(profile['deviceId'].encode()).hexdigest()[:12],16))
def profiles(directory):
 result={}
 for path in Path(directory).glob('*.json'):
  if not re.fullmatch(r'[0-9a-f]{64}\.json',path.name):continue
  profile=json.loads(path.read_text(encoding='utf-8'));ident=public_id(profile)
  if ident in result:raise ValueError('Duplicate public player identifier')
  save=path.with_suffix('.tutorial.json');saved=json.loads(save.read_text(encoding='utf-8')) if save.exists() else {}
  result[ident]=(profile,saved)
 return result

def database(directory):
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
 conn=sqlite3.connect(directory/'social.sqlite',timeout=10)
 conn.execute('PRAGMA journal_mode=WAL')
 conn.execute('CREATE TABLE IF NOT EXISTS friendship (a TEXT NOT NULL,b TEXT NOT NULL,created_at INTEGER NOT NULL,PRIMARY KEY(a,b),CHECK(a<b))')
 conn.commit();return conn

def pair(a,b):
 a,b=str(a),str(b)
 if a==b or not a.isdecimal() or not b.isdecimal() or max(len(a),len(b))>18:raise ValueError('Two different public player identifiers required')
 return tuple(sorted([a,b]))

def link(directory,a,b,remove=False):
 edge=pair(a,b);known=profiles(directory)
 if any(v not in known for v in edge):raise ValueError('Unknown player')
 with closing(database(directory)) as conn,conn:
  if remove:conn.execute('DELETE FROM friendship WHERE a=? AND b=?',edge)
  else:conn.execute('INSERT OR IGNORE INTO friendship VALUES (?,?,?)',(*edge,int(time.time())))

def friend_ids(directory,ident):
 with closing(database(directory)) as conn:
  return [b if a==ident else a for a,b in conn.execute('SELECT a,b FROM friendship WHERE a=? OR b=? ORDER BY created_at,a,b',(ident,ident))]

def public_record(profile,saved):
 normal=saved.get('normal',{});user=normal.get('user',{});ident=public_id(profile)
 name=profile.get('displayName',user.get('name','Village '+ident[-4:]))
 return {'identifier':{'pId':ident,'fbId':'0'},'pId':ident,'fbId':'0','Id':int(ident),'name':name,'firstname':name,'userLevelId':user.get('userLevelID',1),'status':1,'isPlayer':1,'isAppUser':1,'createdAt':profile.get('createdAt',0)}

def native_response(directory,viewer,viewer_normal,service,data):
 ident=public_id(viewer);known=profiles(directory);friends=friend_ids(directory,ident)
 if service in {'ClientFriendService/GetFriends','ClientFriendService/GetApplicationFriends'}:
  return {'friends':[public_record(*known[v]) for v in friends if v in known],'fofs':[]}
 target=data.get('friendUserId')
 if not isinstance(target,str) or not target.isdecimal():raise ValueError('friendUserId string required')
 if target!=ident and target not in friends:raise PermissionError('Village visits require an approved friendship')
 if target not in known:raise PermissionError('Village unavailable')
 profile,saved=known[target];normal=saved.get('normal')
 if not normal:raise ValueError('This player has not reached their village yet')
 record=public_record(profile,saved);friend={**record,'maxAreaId':normal['user'].get('maxAreaId',normal['areaId']),'scenarioId':normal['scenarioId'],'userLevelID':normal['user']['userLevelID']}
 if service.endswith('ForExtras'):return {'friend':friend,'OfflineConsumptionMessageModel':[]}
 projection=world.area_content(normal,normal['areaId'])
 return {'friend':friend,'world':world.startup(normal,int(time.time()))['world'],'areaJson':projection['areaJson'],'user':dict(viewer_normal['user']) if viewer_normal else {}}
