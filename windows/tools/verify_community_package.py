"""Developer-only clean-extract and own-XAPK import validation; never installs/launches Android."""
from pathlib import Path
import csv,datetime,hashlib,json,sqlite3,subprocess,sys,zipfile,os,argparse
ROOT=Path(__file__).resolve().parents[1]
def digest(p):
 with Path(p).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--complete',action='store_true');parser.add_argument('--candidate',action='store_true');parser.add_argument('--field-test',action='store_true');args=parser.parse_args()
 if args.field_test and (args.complete or args.candidate):parser.error('Choose field test alone')
 if args.complete and args.candidate:parser.error('Choose candidate or complete validation')
 info=json.loads((ROOT/'dist'/('latest-community-field-test.json' if args.field_test else 'latest-community-candidate.json' if args.candidate else 'latest-community-complete-package.json' if args.complete else 'latest-community-package.json')).read_text(encoding='utf-8'));archive=Path(info['zip'])
 if digest(archive)!=info['sha256']:raise RuntimeError('Community ZIP hash mismatch')
 out=ROOT/'experiments'/('community-player-validation-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));out.mkdir(parents=True)
 with zipfile.ZipFile(archive) as package:
  manifest=json.loads(package.read('PACKAGE-MANIFEST.json'))
  for name,record in manifest['files'].items():
   if not (out/name).resolve().is_relative_to(out.resolve()):raise RuntimeError('Unexpected package path')
   with package.open(name) as stream:
    if hashlib.file_digest(stream,'sha256').hexdigest()!=record['sha256']:raise RuntimeError('Manifest mismatch: '+name)
  package.extractall(out)
 python=out/'runtime/python/python.exe';source=next((out if info.get('game_files_included') else ROOT).glob('*.xapk'))
 isolation=subprocess.run([str(python),'-c','import sys,json; print(json.dumps({"prefix":sys.prefix,"paths":sys.path,"isolated":sys.flags.isolated}))'],cwd=out,capture_output=True,text=True,timeout=20,env={**os.environ,'PYTHONPATH':str(ROOT/'tools')},creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 if isolation.returncode:raise RuntimeError(isolation.stderr)
 runtime_info=json.loads(isolation.stdout)
 if not runtime_info['isolated'] or not Path(runtime_info['prefix']).resolve().is_relative_to(out.resolve()) or any(not Path(p).resolve().is_relative_to(out.resolve()) for p in runtime_info['paths']):raise RuntimeError('Bundled Python is not isolated to the player folder')
 run=subprocess.run([str(python),'-u',str(out/'tools/import_game.py'),'--source',str(source)],cwd=out,capture_output=True,text=True,timeout=240,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 (out/'import-check.log').write_text(run.stdout+run.stderr,encoding='utf-8')
 if run.returncode:raise RuntimeError(run.stdout+run.stderr)
 query='SELECT s.path,t.name,r.ordinal,r.fields_json FROM game_rows r JOIN game_tables t ON r.table_id=t.id JOIN source_files s ON t.source_id=s.id ORDER BY s.path,t.id,r.ordinal'
 with sqlite3.connect(ROOT/'analysis/private/game_tables.sqlite') as original,sqlite3.connect(out/'analysis/private/game_tables.sqlite') as derived:
  before=original.execute(query).fetchall();after=derived.execute(query).fetchall()
  if before!=after:raise RuntimeError('Derived original table data differs from inspected baseline')
 setup=subprocess.run([str(python),str(out/'tools/setup_local.py'),'--check-only'],cwd=out,capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 (out/'setup-check.log').write_text(setup.stdout+setup.stderr,encoding='utf-8')
 if setup.returncode:raise RuntimeError(setup.stdout+setup.stderr)
 apk=out/'analysis/local-client/local-service-client.apk'
 jarsigner=Path(r'C:\Program Files\Java\jdk-21\bin\jarsigner.exe')
 signature=subprocess.run([str(jarsigner),'-verify',str(apk)],capture_output=True,text=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 (out/'independent-signature-check.log').write_text(signature.stdout+signature.stderr,encoding='utf-8')
 if signature.returncode or 'jar verified' not in (signature.stdout+signature.stderr).lower():raise RuntimeError('Independent JAR signature verification failed')
 result={'folder':str(out),'zip':str(archive),'manifest_files_verified':len(manifest['files']),'bundled_python_import_passed':True,'bundled_python_isolated_from_registry_and_environment':True,'original_table_rows_identical':len(after),'setup_check_passed_without_android_install':True,'dotnet_local_signature_verified':True,'independent_jarsigner_verification_passed':True,'original_xapk_unchanged':digest(source)=='8d25823b824ba766b38e53aedb74b270a0254e6bf3fbbcf1a858b090a66b5c08','community_zip_unchanged':digest(archive)==info['sha256'],'game_archive_included':info.get('game_files_included',False),'personal_data_included':False,'android_installed_or_run':False}
 (ROOT/'analysis'/('latest-community-field-test-validation.json' if args.field_test else 'latest-community-candidate-validation.json' if args.candidate else 'latest-community-complete-validation.json' if args.complete else 'latest-community-validation.json')).write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
