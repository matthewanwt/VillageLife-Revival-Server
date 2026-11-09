"""Provision a private hosted player invitation; never print the secret to logs."""
from pathlib import Path
import argparse,sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import player_access,session,social
parser=argparse.ArgumentParser();parser.add_argument('--state-dir',type=Path,required=True);parser.add_argument('--name',required=True);parser.add_argument('--invite-file',type=Path,required=True);args=parser.parse_args()
if args.invite_file.exists():parser.error('Invitation output already exists; refusing to overwrite it')
session.STATE=args.state_dir;token,account=player_access.provision(args.state_dir/'player-access.json',args.name)
profile=session.login({'deviceId':account['deviceId'],'_accountName':account['name']})['data']['users'][0]
args.invite_file.parent.mkdir(parents=True,exist_ok=True);args.invite_file.write_text(json.dumps({'player_name':args.name,'join_code':token,'player_id':social.public_id(profile)},indent=2),encoding='utf-8')
print('Private invitation written to the selected file. Keep it private. Player ID: '+social.public_id(profile))
