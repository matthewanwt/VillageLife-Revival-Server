"""Read-only XAPK/APK/ELF/DEX/AXML/TCF inspection; never load game code."""
from pathlib import Path
import collections,csv,hashlib,io,json,re,struct,sys,xml.etree.ElementTree as ET,zipfile,zlib
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'analysis';OUT.mkdir(exist_ok=True)
PRIVATE=OUT/'private';PRIVATE.mkdir(exist_ok=True)
SOURCE=next(ROOT.glob('*.xapk'))
EXPECTED='8d25823b824ba766b38e53aedb74b270a0254e6bf3fbbcf1a858b090a66b5c08'
def digest(b):return hashlib.sha256(b).hexdigest()
def filehash(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def savejson(name,data):(OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=True),encoding='utf-8')
def uleb(b,p):
 value=0;shift=0
 while True:
  v=b[p];p+=1;value|=(v&127)<<shift
  if v<128:return value,p
  shift+=7
  assert shift<=35

def axml(b):
 strings=[];root=None;stack=[];pos=8
 while pos<len(b):
  kind,hs,sz=struct.unpack_from('<HHI',b,pos);assert sz>=hs and pos+sz<=len(b)
  if kind==1:
   n,styles,flags,start,_=struct.unpack_from('<5I',b,pos+8)
   offsets=struct.unpack_from('<'+'I'*n,b,pos+hs)
   for offset in offsets:
    p=pos+start+offset
    if flags&256:
     length=b[p];p+=1
     if length&128:p+=1
     length=b[p];p+=1
     if length&128:length=((length&127)<<8)|b[p];p+=1
     text=b[p:p+length].decode('utf-8',errors='replace')
    else:
     length=struct.unpack_from('<H',b,p)[0];p+=2
     if length&32768:length=((length&32767)<<16)|struct.unpack_from('<H',b,p)[0];p+=2
     text=b[p:p+length*2].decode('utf-16le',errors='replace')
    strings.append(text)
  elif kind==0x102:
   ns,name,astart,asz,count,_,_,_=struct.unpack_from('<II6H',b,pos+16)
   el=ET.Element(strings[name]);assert asz>=20
   for i in range(count):
    a=pos+16+astart+i*asz;an,ak,raw,_,_,typ,value=struct.unpack_from('<IIIHBBI',b,a)
    key=('android:' if an!=0xffffffff and 'android' in strings[an] else '')+strings[ak]
    if raw!=0xffffffff:val=strings[raw]
    elif typ==3:val=strings[value]
    elif typ==0x12:val='true' if value else 'false'
    elif typ==1:val='@0x%08x'%value
    elif typ==0x10:val=str(value)
    else:val='0x%x'%value
    el.set(key,val)
   if stack:stack[-1].append(el)
   else:root=el;root.set('xmlns:android','http://schemas.android.com/apk/res/android')
   stack.append(el)
  elif kind==0x103:stack.pop()
  pos+=sz
 assert root is not None and not stack
 return root

def elf(b,label):
 assert b[:6]==b'\x7fELF\x01\x01'
 shoff=struct.unpack_from('<I',b,32)[0];shsz,shnum,shstr=struct.unpack_from('<3H',b,46)
 sections=[struct.unpack_from('<10I',b,shoff+i*shsz) for i in range(shnum)]
 symbols=[];needed=[]
 for sh in sections:
  _,typ,_,_,off,size,link,_,_,entsize=sh
  if typ in (2,11):
   st=sections[link];strings=b[st[4]:st[4]+st[5]]
   for p in range(off,off+size,entsize):
    no,val,ss,info,other,index=struct.unpack_from('<IIIBBH',b,p)
    if no:
     name=strings[no:strings.find(b'\0',no)].decode(errors='replace')
     symbols.append(dict(name=name,address=hex(val),size=ss,defined=index!=0,table='dynsym' if typ==11 else 'symtab'))
  if typ==6:
   st=sections[link];strings=b[st[4]:st[4]+st[5]]
   for p in range(off,off+size,entsize or 8):
    tag,value=struct.unpack_from('<II',b,p)
    if tag==1:needed.append(strings[value:strings.find(b'\0',value)].decode())
 if symbols:
  with (OUT/(label+'.symbols.csv')).open('w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=symbols[0]);w.writeheader();w.writerows(symbols)
 texts=[x.decode('ascii') for x in re.findall(rb'[\x20-\x7e]{6,}',b)]
 urls=sorted(set(s for s in texts if re.match(r'^https?://[^\s]+$',s)))
 routes=sorted(set(s for s in texts if re.match(r'^Client[A-Za-z]+Service/[A-Za-z0-9_]+$',s)))
 (OUT/(label+'.endpoints.txt')).write_text('\n'.join(urls+routes)+'\n',encoding='utf-8')
 interesting=[s for s in texts if re.search(r'^_Z.*Script_|ClientService/Login|ProcessOfflineConsumption|^gameserveraddr$|^requestserveraddr$|^chatserveraddr$|JavaScriptCore',s)]
 (OUT/(label+'.startup_symbols.txt')).write_text('\n'.join(interesting)+'\n',encoding='utf-8')
 return dict(sha256=digest(b),bytes=len(b),elf_class=32,machine=struct.unpack_from('<H',b,18)[0],architecture='ARM (APK armeabi-v7a directory)',needed=needed,symbol_count=len(symbols),defined_symbol_count=sum(x['defined'] for x in symbols),service_routes=routes,urls=urls)

def dex(b,label):
 assert b[:4]==b'dex\n'
 n,off=struct.unpack_from('<II',b,56);texts=[]
 for i in range(n):
  p=struct.unpack_from('<I',b,off+4*i)[0];_,p=uleb(b,p);texts.append(b[p:b.index(b'\0',p)].decode('utf-8',errors='replace'))
 cn,co=struct.unpack_from('<II',b,96);methods=0;nonempty=0
 for i in range(cn):
  dataoff=struct.unpack_from('<I',b,co+i*32+24)[0]
  if not dataoff:continue
  sizes=[]
  for _ in range(4):v,dataoff=uleb(b,dataoff);sizes.append(v)
  for _ in range(sizes[0]+sizes[1]):_,dataoff=uleb(b,dataoff);_,dataoff=uleb(b,dataoff)
  for _ in range(sizes[2]+sizes[3]):
   _,dataoff=uleb(b,dataoff);_,dataoff=uleb(b,dataoff);code,dataoff=uleb(b,dataoff)
   if code:
    methods+=1;nonempty+=struct.unpack_from('<I',b,code+12)[0]>0
 names=[s for s in texts if s.startswith('Lcom/playdemic/') and s.endswith(';')]
 (OUT/(label+'.playdemic_classes.txt')).write_text('\n'.join(names)+'\n',encoding='utf-8')
 (OUT/(label+'.network_strings.txt')).write_text('\n'.join(s for s in texts if re.match(r'^https?://',s) or re.search(r'Obb|OBB|DownloadExpansion|nativePreInit|PDActivity|PDNativeMethods',s))+'\n',encoding='utf-8')
 return dict(sha256=digest(b),version=b[4:7].decode(),strings=n,class_definitions=cn,methods_with_code=methods,nonempty_method_bodies=nonempty,sha1_header_valid=hashlib.sha1(b[32:]).digest()==b[12:32],adler32_header_valid=zlib.adler32(b[12:])&0xffffffff==struct.unpack_from('<I',b,8)[0])

def tcf(b,label,expected_manifest):
 magic,n,names_size,data_size=struct.unpack_from('<4sIII',b);assert magic==b'TCF1'
 pool=16+16*n;base=pool+names_size;assert base+data_size==len(b)
 rows=[];allnames=set();ranges=[];matches=0;zlib_decoded=[]
 for i in range(n):
  no,off,size,check=struct.unpack_from('<4I',b,16+16*i)
  assert no<names_size and off+size<=data_size
  start=pool+no;end=b.index(b'\0',start,pool+names_size);name=b[start:end].decode('utf-8')
  assert name not in allnames;allnames.add(name);raw=b[base+off:base+off+size]
  expected=expected_manifest.get(name)
  match=expected is not None and int(expected['size'],16)==size and int(expected['check'],16)==check
  matches+=match;ranges.append((off,off+size))
  row=dict(path=name,offset_in_tcf=base+off,stored_bytes=size,check_word=hex(check),sha256=digest(raw),manifest_metadata_matches=match,magic=raw[:4].hex())
  if raw[:4]==b'SPK1':
   row['unpacked_size']=struct.unpack_from('<I',raw,4)[0]
   if raw[8:10] in (b'x\xda',b'x\x9c',b'x\x01') and row['unpacked_size']<64000000:
    de=zlib.decompressobj();unpacked=de.decompress(raw[8:],row['unpacked_size']+1)
    assert de.eof and len(unpacked)==row['unpacked_size']
    row['compression']='zlib';row['unpacked_sha256']=digest(unpacked)
    if name.endswith('.t3g'):
     target=PRIVATE/'unpacked'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(unpacked)
     strings=[s.decode('ascii') for s in re.findall(rb'[\x20-\x7e]{6,}',unpacked)]
     (OUT/'gui_startup_strings.txt').write_text('\n'.join(s for s in strings if re.search(r'http|server|login|offline|script|\.js$|\.php|\.asmx',s,re.I))+'\n',encoding='utf-8')
    zlib_decoded.append(name)
   else:row['compression']='SPK1 custom (not yet decoded)'
  if name.endswith('.xml'):
   target=PRIVATE/'packed_xml'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
  rows.append(row)
 ranges.sort();assert all(ranges[i][1]<=ranges[i+1][0] for i in range(len(ranges)-1))
 with (OUT/(label+'.inventory.csv')).open('w',newline='',encoding='utf-8') as f:
  cols=sorted(set().union(*(r.keys() for r in rows)));w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(rows)
 return dict(magic='TCF1',entries=n,string_pool_bytes=names_size,data_bytes=data_size,all_ranges_in_bounds=True,no_entry_overlap=True,manifest_metadata_matches=matches,extensions=dict(collections.Counter(Path(r['path']).suffix for r in rows)),compression=dict(collections.Counter(r.get('compression','no SPK1 header') for r in rows)),zlib_decoded=zlib_decoded,paths=allnames)

before=filehash(SOURCE);assert before==EXPECTED
result=dict(original_file=SOURCE.name,bytes=SOURCE.stat().st_size,sha256_before=before,game_executed=False,network_probes=False,tools_downloaded=False)
with zipfile.ZipFile(SOURCE) as x:
 assert x.testzip() is None
 result['outer_archive_crc']='passed';result['outer_entries']=[]
 for info in x.infolist():
  raw=x.read(info);result['outer_entries'].append(dict(path=info.filename,bytes=len(raw),sha256=digest(raw)))
 metadata=json.loads(x.read('manifest.json'));savejson('xapk_manifest.json',metadata)
 apkn=next(n for n in x.namelist() if n.endswith('.apk'));apkb=x.read(apkn)
 (PRIVATE/'client-original-copy.apk').write_bytes(apkb)
 with zipfile.ZipFile(io.BytesIO(apkb)) as a:
  assert a.testzip() is None;result['apk_archive_crc']='passed'
  with (OUT/'apk_inventory.csv').open('w',newline='',encoding='utf-8') as f:
   w=csv.writer(f);w.writerow(['path','bytes','crc32','sha256'])
   for i in a.infolist():w.writerow([i.filename,i.file_size,hex(i.CRC),digest(a.read(i))])
  manifest=axml(a.read('AndroidManifest.xml'));ET.indent(manifest);ET.ElementTree(manifest).write(OUT/'AndroidManifest.decoded.xml',encoding='utf-8',xml_declaration=True)
  result['android_manifest']=dict(manifest.attrib)
  result['uses_sdk']=[e.attrib for e in manifest.findall('uses-sdk')]
  result['permissions']=[e.get('android:name') for e in manifest.findall('uses-permission')]
  result['features']=[e.attrib for e in manifest.findall('uses-feature')]
  original=ET.fromstring(a.read('assets/origmanifest.xml'));expected={el.get('name'):el.attrib for el in original}
  result['asset_manifest']=dict(original.attrib,entries=len(expected))
  result['native']={Path(n).name:elf(a.read(n),Path(n).name) for n in a.namelist() if n.startswith('lib/') and n.endswith('.so')}
  result['dex']={n:dex(a.read(n),n) for n in a.namelist() if re.match(r'^classes\d*\.dex$',n)}
  main=tcf(a.read('assets/main.tcf'),'main_tcf',expected)
  result['tcf']={'apk_main':{k:v for k,v in main.items() if k!='paths'}}
  for n in a.namelist():
   if n.startswith('META-INF/') and n.endswith(('.RSA','.SF','.MF')):(PRIVATE/Path(n).name).write_bytes(a.read(n))
 obbn=next(n for n in x.namelist() if n.endswith('.obb'));obb=tcf(x.read(obbn),'obb_tcf',expected)
 result['tcf']['obb']={k:v for k,v in obb.items() if k!='paths'}
 result['asset_manifest']['missing_paths']=sorted(set(expected)-main['paths']-obb['paths'])
 result['asset_manifest']['extra_paths']=sorted((main['paths']|obb['paths'])-set(expected))
result['sha256_after']=filehash(SOURCE);result['original_unchanged']=result['sha256_after']==before
assert result['original_unchanged']
savejson('inspection.json',result)
print(json.dumps(dict(sha256=before,original_unchanged=True,manifest=result['android_manifest'],sdk=result['uses_sdk'],native_libraries={k:dict(bytes=v['bytes'],needed=v['needed'],symbols=v['symbol_count']) for k,v in result['native'].items()},tcf=result['tcf'],missing_assets=result['asset_manifest']['missing_paths'],dex=result['dex']),indent=2))
