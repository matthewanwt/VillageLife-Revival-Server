"""Host operator's private friendship linking tool; no social writes exposed publicly."""
from pathlib import Path
import sys,argparse,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import social
parser=argparse.ArgumentParser();parser.add_argument('--state-dir',type=Path,default=Path(__file__).resolve().parents[1]/'backend/private_state');parser.add_argument('action',choices=['list','link','unlink']);parser.add_argument('players',nargs='*');args=parser.parse_args()
if args.action=='list':
 for ident,(profile,saved) in social.profiles(args.state_dir).items():
  record=social.public_record(profile,saved);print(ident+' | '+record['name']+' | level '+str(record['userLevelId']))
else:
 if len(args.players)!=2:parser.error('Provide two public player IDs from list')
 social.link(args.state_dir,*args.players,remove=args.action=='unlink');print('Friendship '+('removed' if args.action=='unlink' else 'linked')+'. No currency or village objects changed.')
