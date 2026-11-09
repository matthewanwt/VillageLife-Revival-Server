"""Prepare a player's own verified XAPK locally. No game files are distributed/downloaded."""
from pathlib import Path
from contextlib import closing
import argparse,csv,hashlib,json,os,secrets,shutil,sqlite3,struct,subprocess,sys,zipfile
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE_SHA='8d25823b824ba766b38e53aedb74b270a0254e6bf3fbbcf1a858b090a66b5c08'
SOURCE_APK_SHA='37f4ac5ee3b46133a1aeb14d1ca78975a64dc600c6d9d17fb99717d6cf532a71'
OBB_SHA='543ef1c7409dbe6fdc79d4fa78faecc2e2b56b2fbbf0bd04f709f938d4965269'
LIB_AFTER_SHA='a12faae81ab252d7754c175de0479f4bb8eb24cb7c5721ab9bf4c2e27215154f'
APK_NAME='com.playdemic.villagelife.android.apk';OBB_NAME='main.241.com.playdemic.villagelife.android.obb'
REPLACEMENTS={b'https://playvlg.playdemic.com/web/':b'http://10.0.2.2/web/',b'https://playvlg.playdemic.com/':b'http://10.0.2.2/',b'http://vlt-prod.cdn.playdemic.com/assets/v270/':b'http://10.0.2.2/assets/v270/',b'http://vlt-prod-backup.cdn.playdemic.com/assets/v270/':b'http://10.0.2.2/assets/v270/'}

def digest(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def unpack_old(raw):
 if raw[:4]!=b'SPK1':raise ValueError('Expected original SPK1 data')
 expected=struct.unpack_from('<I',raw,4)[0]
 if not 0<expected<64000000:raise ValueError('Invalid packed data length')
 source=memoryview(raw)[8:];index=0;out=bytearray()
 while True:
  control=source[index];index+=1
  if control==0:break
  mode=control&0xc0
  if mode==0:
   if index+control>len(source):raise ValueError('Truncated literal')
   out.extend(source[index:index+control]);index+=control
  else:
   if mode==0x40:back=((control&3)<<8)+source[index]+1;index+=1;length=((control>>2)&15)+3
   elif mode==0x80:
    first,second=source[index:index+2];index+=2;back=((first&63)<<8)+second+1;length=((control&63)<<2)+(first>>6)+4
   else:
    first,second,third=source[index:index+3];index+=3;back=((first&1)<<16)+(second<<8)+third+1;length=((control&63)<<7)+(first>>1)+5
   if not 0<back<=len(out) or len(out)+length>expected:raise ValueError('Invalid packed copy')
   for _ in range(length):out.append(out[-back])
  if len(out)>expected:raise ValueError('Packed data exceeded declared size')
 if len(out)!=expected:raise ValueError('Packed data length mismatch')
 return bytes(out)

def patch_library(data):
 for old,new in REPLACEMENTS.items():
  if data.count(old+b'\0')!=1:raise ValueError('Original endpoint mismatch')
  offset=data.index(old+b'\0');data=data[:offset]+new+b'\0'*(len(old)-len(new))+data[offset+len(old):]
 if hashlib.sha256(data).hexdigest()!=LIB_AFTER_SHA:raise ValueError('Prepared library hash mismatch')
 return data

def tcf_index(path):
 with Path(path).open('rb') as stream:
  magic,count,names_size,data_size=struct.unpack('<4sIII',stream.read(16))
  if magic!=b'TCF1' or count>100000 or names_size>16000000:raise ValueError('Invalid original expansion directory')
  entries=stream.read(16*count);names=stream.read(names_size);base=16+16*count+names_size
  if base+data_size!=Path(path).stat().st_size:raise ValueError('Expansion size mismatch')
  records=[];seen=set()
  for index in range(count):
   name_offset,offset,size,_=struct.unpack_from('<4I',entries,index*16)
   if name_offset>=len(names) or offset+size>data_size:raise ValueError('Expansion entry out of bounds')
   end=names.find(b'\0',name_offset)
   if end<0:raise ValueError('Unterminated asset path')
   name=names[name_offset:end].decode('utf-8')
   if name in seen:raise ValueError('Duplicate asset path')
   seen.add(name);records.append({'path':name,'offset_in_tcf':base+offset,'stored_bytes':size})
 return records

def create_database(obb,records,target):
 target=Path(target);target.parent.mkdir(parents=True,exist_ok=True)
 partial=target.with_suffix('.sqlite.partial')
 if partial.exists():partial.unlink()
 schema="""PRAGMA foreign_keys=ON;
CREATE TABLE source_files(id INTEGER PRIMARY KEY,path TEXT UNIQUE,sha256 TEXT);
CREATE TABLE game_tables(id INTEGER PRIMARY KEY,source_id INTEGER REFERENCES source_files(id),name TEXT,declared_rows INTEGER,actual_rows INTEGER);
CREATE TABLE game_rows(table_id INTEGER REFERENCES game_tables(id),ordinal INTEGER,row_id TEXT,fields_json TEXT,PRIMARY KEY(table_id,ordinal));
CREATE INDEX table_name ON game_tables(name);CREATE INDEX row_key ON game_rows(table_id,row_id);"""
 try:
  with closing(sqlite3.connect(partial)) as conn,Path(obb).open('rb') as stream:
   conn.executescript(schema)
   for entry in sorted((r for r in records if r['path'].endswith('_en.xml')),key=lambda r:r['path']):
    stream.seek(entry['offset_in_tcf']);raw=unpack_old(stream.read(entry['stored_bytes']));root=ET.fromstring(raw.rstrip(b'\0'))
    sid=conn.execute('INSERT INTO source_files(path,sha256) VALUES(?,?)',(Path(entry['path']).name,hashlib.sha256(raw).hexdigest())).lastrowid
    for table in root.iter('table'):
     rows=table.findall('./rows/row');expected=int(table.get('numrows'))
     if len(rows)!=expected:raise ValueError('Original table row count mismatch')
     tid=conn.execute('INSERT INTO game_tables(source_id,name,declared_rows,actual_rows) VALUES(?,?,?,?)',(sid,table.get('name'),expected,len(rows))).lastrowid
     for ordinal,row in enumerate(rows):
      data={}
      for field in row:
       value=ET.tostring(field,encoding='unicode') if len(field) or field.attrib else (field.text or '')
       if field.tag in data:
        if not isinstance(data[field.tag],list):data[field.tag]=[data[field.tag]]
        data[field.tag].append(value)
       else:data[field.tag]=value
      conn.execute('INSERT INTO game_rows VALUES(?,?,?,?)',(tid,ordinal,row.findtext('id'),json.dumps(data,ensure_ascii=True)))
   if conn.execute('select count(*) from game_tables').fetchone()[0]!=131 or conn.execute('select count(*) from game_rows').fetchone()[0]!=50601:raise ValueError('Unsupported original game tables')
   conn.commit()
   if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Derived table database is invalid')
  conn.close();os.replace(partial,target)
 finally:
  if partial.exists():partial.unlink()

def verify_game_copy(original,prepared):
 with zipfile.ZipFile(original) as source,zipfile.ZipFile(prepared) as result:
  names={i.filename for i in source.infolist() if not i.filename.upper().startswith('META-INF/')}
  if names!={i.filename for i in result.infolist() if not i.filename.upper().startswith('META-INF/')}:raise ValueError('Prepared APK entry list changed')
  for name in names:
   expected=source.read(name)
   if name=='lib/armeabi-v7a/libpdandroid.so':expected=patch_library(expected)
   if result.read(name)!=expected:raise ValueError('Unexpected change to original game entry: '+name)

def prepare_game(source,root=ROOT,signer_command=None):
 source=Path(source).resolve();root=Path(root).resolve()
 if not source.is_file() or digest(source)!=ARCHIVE_SHA:raise ValueError('Select the original Village Life241.0.5.270.0 XAPK. This archive version/hash is not supported.')
 root.mkdir(parents=True,exist_ok=True);archives=list(root.glob('*.xapk'))
 if len(archives)>1 or any(digest(p)!=ARCHIVE_SHA for p in archives):raise ValueError('Remove unrelated XAPK copies from this player folder before setup; files were preserved.')
 archive=archives[0] if archives else root/'VillageLife-Original.xapk'
 if not archives:
  partial=archive.with_suffix('.xapk.partial');shutil.copyfile(source,partial)
  if digest(partial)!=ARCHIVE_SHA:raise ValueError('Copied archive hash mismatch')
  os.replace(partial,archive)
 print('Original XAPK verified; creating local game data from your copy.',flush=True)
 inputs=root/'analysis/runtime_inputs';inputs.mkdir(parents=True,exist_ok=True);apk=inputs/'client-original-copy.apk';obb=inputs/OBB_NAME
 with zipfile.ZipFile(archive) as original:
  for target,name,expected in [(apk,APK_NAME,SOURCE_APK_SHA),(obb,OBB_NAME,OBB_SHA)]:
   if target.exists() and digest(target)==expected:continue
   names=[n for n in original.namelist() if n==name or n.endswith('/'+name)]
   if len(names)!=1:raise ValueError('Original game archive entry missing or ambiguous')
   partial=target.with_suffix(target.suffix+'.partial')
   with original.open(names[0]) as incoming,partial.open('wb') as output:shutil.copyfileobj(incoming,output)
   if digest(partial)!=expected:raise ValueError('Original game entry hash mismatch')
   os.replace(partial,target)
 records=tcf_index(obb);inventory=root/'analysis/obb_tcf.inventory.csv'
 with inventory.open('w',newline='',encoding='utf-8') as output:
  writer=csv.DictWriter(output,fieldnames=['path','offset_in_tcf','stored_bytes']);writer.writeheader();writer.writerows(records)
 database=root/'analysis/private/game_tables.sqlite'
 if not database.exists():create_database(obb,records,database)
 local=root/'analysis/local-client';local.mkdir(parents=True,exist_ok=True);prepared=local/'local-service-client.apk';receipt=local/'changes.json'
 signer_command=signer_command or [str(root/'runtime/dotnet/dotnet.exe'),str(root/'StartVillageLife/VillageLifeLauncher.dll')]
 if prepared.exists() and receipt.exists() and json.loads(receipt.read_text(encoding='utf-8')).get('output_sha256')==digest(prepared):
  verify_game_copy(apk,prepared)
 else:
  if prepared.exists():raise ValueError('Existing prepared game differs from its receipt; files were preserved. Use a fresh player folder or restore its backup.')
  unsigned=local/'prepared.unsigned.apk';signed=local/'prepared.signed.partial.apk';password=local/'signing-password.private';key=local/'local-signing.pfx'
  if not password.exists():password.write_text(secrets.token_urlsafe(32),encoding='utf-8')
  if signed.exists():signed.unlink()
  try:
   with zipfile.ZipFile(apk) as original,zipfile.ZipFile(unsigned,'w') as output:
    for info in original.infolist():
     if info.filename.upper().startswith('META-INF/'):continue
     data=original.read(info)
     if info.filename=='lib/armeabi-v7a/libpdandroid.so':data=patch_library(data)
     output.writestr(info,data)
   result=subprocess.run([*signer_command,'--sign-apk',str(unsigned),str(signed),str(key),str(password)],capture_output=True,text=True,timeout=180,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
   if result.returncode:raise RuntimeError(result.stdout+result.stderr)
   verify_game_copy(apk,signed);os.replace(signed,prepared)
   receipt.write_text(json.dumps({'source_sha256':SOURCE_APK_SHA,'original_xapk_sha256':ARCHIVE_SHA,'output_sha256':digest(prepared),'library_after_sha256':LIB_AFTER_SHA,'local_player_generated':True,'code_instructions_changed':False,'changes':'four endpoint strings and local signature only'},indent=2),encoding='utf-8')
  finally:
   if unsigned.exists():unsigned.unlink()
   if signed.exists():signed.unlink()
 result=subprocess.run([*signer_command,'--verify-apk',str(prepared)],capture_output=True,text=True,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 if result.returncode:raise RuntimeError('Local APK signature verification failed')
 if digest(source)!=ARCHIVE_SHA or digest(archive)!=ARCHIVE_SHA:raise ValueError('Original XAPK changed during setup')
 print('Local game data and locally signed copy verified. Original XAPK unchanged.',flush=True)
 return {'apk_sha256':digest(prepared),'source_unchanged':True,'asset_entries':len(records),'database':str(database)}

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--source',type=Path,required=True);args=parser.parse_args();prepare_game(args.source)
if __name__=='__main__':main()
