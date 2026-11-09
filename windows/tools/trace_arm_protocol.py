"""Static ARM32 protocol trace. This decodes instructions; it executes no game code."""
from pathlib import Path
import csv,io,json,struct,zipfile
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'analysis/protocol';OUT.mkdir(exist_ok=True)
with zipfile.ZipFile(next(ROOT.glob('*.xapk'))) as z:
 with zipfile.ZipFile(io.BytesIO(z.read('com.playdemic.villagelife.android.apk'))) as a:IMAGE=a.read('lib/armeabi-v7a/libpdandroid.so')
def u32(off):return struct.unpack_from('<I',IMAGE,off)[0]
ph=u32(28);psz,pn=struct.unpack_from('<HH',IMAGE,42)
SEGS=[struct.unpack_from('<8I',IMAGE,ph+i*psz) for i in range(pn)]
def read(addr,size=4):
 for typ,off,va,_,fs,*_ in SEGS:
  if typ==1 and va<=addr and addr+size<=va+fs:return IMAGE[off+addr-va:off+addr-va+size]
 return b''
def word(addr):
 b=read(addr);return int.from_bytes(b,'little') if len(b)==4 else None
def cstring(addr):
 if addr is None:return None
 raw=read(addr,250)
 if not raw:return None
 raw=raw.split(b'\0',1)[0]
 if not raw or any(x<32 or x>126 for x in raw):return None
 return raw.decode('ascii')
shoff=u32(32);ssz,sn,snames=struct.unpack_from('<HHH',IMAGE,46)
sections=[struct.unpack_from('<10I',IMAGE,shoff+i*ssz) for i in range(sn)]
strsh=sections[snames];sectionnames=IMAGE[strsh[4]:strsh[4]+strsh[5]]
def section_name(sh):return sectionnames[sh[0]:sectionnames.find(b'\0',sh[0])].decode()
SYMBOLS=list(csv.DictReader((ROOT/'analysis/libpdandroid.so.symbols.csv').open(encoding='utf-8')))
NAMES={int(s['address'],16)&~1:s['name'] for s in SYMBOLS if s['defined']=='True'}
relocations={}
for sh in sections:
 if sh[1]!=9:continue
 symbols=sections[sh[6]];strings=sections[symbols[6]];strings=IMAGE[strings[4]:strings[4]+strings[5]]
 for p in range(sh[4],sh[4]+sh[5],sh[9] or 8):
  off,info=struct.unpack_from('<II',IMAGE,p);index=info>>8
  if not index:continue
  nameoff=u32(symbols[4]+index*(symbols[9] or 16))
  relocations[off]=strings[nameoff:strings.find(b'\0',nameoff)].decode(errors='replace')
def immediate(w):
 value=w&255;rotate=((w>>8)&15)*2
 return ((value>>rotate)|(value<<(32-rotate)))&0xffffffff if rotate else value
for sh in sections:
 if section_name(sh)!='.plt':continue
 for addr in range(sh[3],sh[3]+sh[5]-8,4):
  a,b,c=word(addr),word(addr+4),word(addr+8)
  if a&0xfffff000==0xe28fc000 and b&0xfffff000==0xe28cc000 and c&0xfffff000==0xe5bcf000:
   got=(addr+8+immediate(a)+immediate(b)+(c&4095))&0xffffffff
   if got in relocations:NAMES[addr]=relocations[got]+'@PLT'
REG=lambda n: ['r'+str(i) for i in range(13)]+['sp','lr','pc'] if False else ('sp' if n==13 else 'lr' if n==14 else 'pc' if n==15 else 'r'+str(n))
COND=['eq','ne','cs','cc','mi','pl','vs','vc','hi','ls','ge','lt','gt','le','','nv']
OP=['and','eor','sub','rsb','add','adc','sbc','rsc','tst','teq','cmp','cmn','orr','mov','bic','mvn']
def trace(sym):
 base=int(sym['address'],16)&~1;registers={};lines=[];refs=[];calls=[]
 for pc in range(base,base+int(sym['size']),4):
  w=word(pc);cond=COND[w>>28];text='';note=[];rn=(w>>16)&15;rd=(w>>12)&15
  if w&0x0e000000==0x0a000000:
   off=w&0xffffff;off=off-(1<<24) if off&0x800000 else off;target=pc+8+(off<<2)
   name=NAMES.get(target,hex(target));text=('bl' if w&(1<<24) else 'b')+cond+' '+name
   calls.append(dict(pc=hex(pc),target=hex(target),name=name,args={REG(r):hex(v) for r,v in registers.items() if r<4}))
   for r in [0,1,2,3,12]:registers.pop(r,None)
  elif w&0x0ff00000 in [0x03000000,0x03400000]:
   v=((w>>4)&0xf000)|(w&0xfff);high=w&0x00400000
   text=('movt' if high else 'movw')+cond+' '+REG(rd)+', #'+hex(v)
   registers[rd]=((registers.get(rd,0)&0xffff)|(v<<16)) if high else v
  elif w&0x0c000000==0x04000000:
   load=bool(w&(1<<20));byte=bool(w&(1<<22));regoff=bool(w&(1<<25))
   offset=registers.get(w&15) if regoff else w&4095
   if regoff and w&0xff0:offset=None
   baseval=pc+8 if rn==15 else registers.get(rn)
   addr=None if baseval is None or offset is None else (baseval+(offset if w&(1<<23) else -offset))&0xffffffff
   text=('ldr' if load else 'str')+('b' if byte else '')+cond+' '+REG(rd)+', ['+REG(rn)+', '+(REG(w&15) if regoff else '#'+hex(w&4095))+']'
   if load:
    val=word(addr) if addr is not None and not byte else None
    if val is not None:registers[rd]=val;note.append('mem['+hex(addr)+']='+hex(val))
    else:registers.pop(rd,None)
  elif w&0x0c000000==0 and w&0x0fc000f0!=0x00000090:
   op=(w>>21)&15;imm=bool(w&(1<<25));v=immediate(w) if imm else registers.get(w&15)
   if not imm and w&0xff0:v=None
   a=pc+8 if rn==15 else registers.get(rn)
   operand='#'+hex(immediate(w)) if imm else REG(w&15)+(' shift='+hex(w&0xff0) if w&0xff0 else '')
   text=OP[op]+cond+' '+REG(rd)+', '+REG(rn)+', '+operand
   val=None
   if op==13:val=v
   elif a is not None and v is not None:
    if op==4:val=(a+v)&0xffffffff
    elif op==2:val=(a-v)&0xffffffff
    elif op==0:val=a&v
   if op not in [8,9,10,11]:
    if val is None:registers.pop(rd,None)
    else:registers[rd]=val
  else:text='word '+hex(w)
  for r,v in list(registers.items()):
   string=cstring(v)
   if string and len(string)>=1:
    key=(pc,r,v,string)
    if r==rd:
     note.append(REG(r)+' -> '+repr(string));refs.append(dict(pc=hex(pc),reg=REG(r),address=hex(v),text=string))
  lines.append(hex(pc)+'  '+format(w,'08x')+'  '+text+(' ; '+'; '.join(note) if note else ''))
 return dict(name=sym['name'],address=hex(base),size=int(sym['size']),calls=calls,string_references=refs,disassembly=lines)
filters=['GSINTLOAD14UpdateRequired','GetFolderNameLetter','CreateManifestFromXML','AND_TestCurrManifest','_Z7FixHTTPPc','GSINTSERVER13P_PostMessage','Script_2082_createSession','Script_2083_createSessionListener','Script_2482_UserSettingsModelParser','GSINTSERVER10InitServer','GSINTSERVER15GameServer_Init','GSINTSERVER7Encrypt','GSINTSERVER8PostJson','GSINTSERVER13GetJSONResult','GSINTSERVER15NewServerThread','Script_2237_ServerAddCall','Script_2238_ServerAddCallToBatch','Script_2264_ServerUpdate','Script_0047_StateLoadSession','Script_0052_StateLoadUserGetStartupInfo','Script_2332_ServerGetStartupInfo','Script_2338_ServerGetUserGameSettings','Script_0040_StateLoadInitialisation']
traces=[trace(s) for s in SYMBOLS if s['defined']=='True' and any(f in s['name'] for f in filters)]
for t in traces:(OUT/(t['name']+'.txt')).write_text('\n'.join(t['disassembly'])+'\n',encoding='utf-8')
(OUT/'static_trace.json').write_text(json.dumps(traces,indent=2),encoding='utf-8')
print(json.dumps(dict(functions=len(traces),plt_imports_resolved=sum('@PLT' in x for x in NAMES.values()),caution='linear register values are hints, not control-flow proof',references={t['name']:sorted(set(x['text'] for x in t['string_references'])) for t in traces}),indent=2))
