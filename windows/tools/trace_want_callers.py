import sys,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import trace_arm_protocol as t
for seg in t.SEGS:
 typ,off,va,_,size,_,flags,_=seg
 if typ!=1 or not flags&1:continue
 for pc in range(va,va+size-4,4):
  w=t.word(pc)
  if w&0x0f000000!=0x0b000000:continue
  delta=w&0xffffff
  if delta&0x800000:delta-=0x1000000
  if (pc+8+delta*4)&0xffffffff!=0x4183e8:continue
  symbol=max((s for s in t.SYMBOLS if s['defined']=='True' and int(s['address'],16)<=pc),key=lambda s:int(s['address'],16))
  result=t.trace(symbol);(t.OUT/(symbol['name']+'.txt')).write_text('\n'.join(result['disassembly']),encoding='utf8')
  print(hex(pc),symbol['name'], sorted(set(v['text'] for v in result['string_references'])))
