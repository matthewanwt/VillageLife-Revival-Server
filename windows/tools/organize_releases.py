"""Archive superseded release artifacts without deleting builds or touching saves."""
from pathlib import Path
import argparse,datetime,json,re
ROOT=Path(__file__).resolve().parents[1]
POINTERS=['latest-package.json','latest-community-package.json','latest-community-complete-package.json','latest-player-package.json']
PATTERN=re.compile(r'^(VillageLife-(?:Windows-PrivateTest|Community-(?:Player|Complete))-\d{8}T\d{6}Z)(?:\.zip(?:\.sha256\.txt)?)?$')

def checked(path,dist):
 path=Path(path).resolve()
 if path==dist or not path.is_relative_to(dist):raise ValueError('Release path escapes distribution folder')
 return path

def organize(apply=False):
 dist=(ROOT/'dist').resolve();keep=set();current=[]
 for name in POINTERS:
  pointer=dist/name
  if not pointer.exists():continue
  value=json.loads(pointer.read_text(encoding='utf-8'));current.append({'pointer':name,**value})
  for key in ['folder','zip']:
   if key in value:
    path=checked(value[key],dist)
    if not path.exists():raise ValueError('Current release artifact missing: '+str(path))
    keep.add(path.name)
    if key=='zip':keep.add(path.name+'.sha256.txt')
 moves=[]
 for path in sorted(dist.iterdir()):
  match=PATTERN.fullmatch(path.name)
  if not match or path.name in keep:continue
  source=checked(path,dist);target=checked(dist/'archive'/match[1]/path.name,dist)
  if target.exists():raise ValueError('Archive target already exists: '+str(target))
  if path.is_symlink():raise ValueError('Refusing to move a release symlink')
  moves.append({'from':str(source),'to':str(target),'build':match[1]})
 result={'createdUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'apply':apply,'current_builds':sorted({Path(v['folder']).name for v in current if 'folder' in v}),'superseded_builds':len({m['build'] for m in moves}),'artifact_moves':len(moves),'moves':moves,'deleted_files':0,'saves_touched':False}
 if apply:
  for move in moves:
   source=checked(move['from'],dist);target=checked(move['to'],dist);target.parent.mkdir(parents=True,exist_ok=True);source.rename(target)
  archive=dist/'archive';archive.mkdir(exist_ok=True)
  (archive/('organization-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
  (dist/'RELEASES.json').write_text(json.dumps({'current':current,'archived_builds':[p.name for p in sorted(archive.iterdir()) if p.is_dir()]},indent=2),encoding='utf-8')
  player=next(v for v in current if v['pointer']=='latest-player-package.json')
  (dist/'README.md').write_text('# Village Life releases\n\nCurrent player download: ['+Path(player['zip']).name+']('+Path(player['zip']).name+').\n\nThe active development application and server live in the project root. Current\ncomplete-player, runtime-only and private test snapshots remain here. Superseded\nversions are grouped under archive/ with their ZIPs and checksums. Nothing was\ndeleted; personal saves and experiment evidence were not moved. RELEASES.json\nlists the current pointers and archived build names.\n',encoding='utf-8')
 return result
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args();print(json.dumps(organize(args.apply),indent=2))
