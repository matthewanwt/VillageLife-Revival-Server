"""Decode the legacy SPK1 copy stream by static analysis of GSINTPACK::UNPACKOLD.
No original native code is executed. Validate exact length and XML syntax.
"""
from pathlib import Path
import collections,hashlib,json,struct,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];PRIVATE=ROOT/'analysis/private'
def unpack_old(raw):
 assert raw[:4]==b'SPK1'
 expected=struct.unpack_from('<I',raw,4)[0];assert 0<expected<64000000
 src=memoryview(raw)[8:];p=0;out=bytearray()
 while True:
  control=src[p];p+=1
  if control==0:break
  mode=control&0xc0
  if mode==0:
   assert p+control<=len(src)
   out.extend(src[p:p+control]);p+=control
  else:
   if mode==0x40:
    back=((control&3)<<8)+src[p]+1;p+=1
    length=((control>>2)&15)+3
   elif mode==0x80:
    first,second=src[p:p+2];p+=2
    back=((first&63)<<8)+second+1
    length=((control&63)<<2)+(first>>6)+4
   else:
    first,second,third=src[p:p+3];p+=3
    back=((first&1)<<16)+(second<<8)+third+1
    length=((control&63)<<7)+(first>>1)+5
   assert 0<back<=len(out),(p,control,back,len(out))
   assert len(out)+length<=expected
   for _ in range(length):out.append(out[-back])
  assert len(out)<=expected
 assert len(out)==expected,(len(out),expected)
 return bytes(out)

def tests():
 def wrap(payload,size):return b'SPK1'+struct.pack('<I',size)+payload
 assert unpack_old(wrap(b'\x03abc\x40\x02\0',6))==b'abcabc'
 assert unpack_old(wrap(b'\x03abc\x80\0\x02\0',7))==b'abcabca'
 assert unpack_old(wrap(b'\x03abc\xc0\0\0\x02\0',8))==b'abcabcab'
 assert unpack_old(wrap(b'\x01A\x40\0\0',4))==b'AAAA'
 for bad in [wrap(b'\x40\0\0',3),wrap(b'\x03abc\0',4)]:
  try:unpack_old(bad)
  except (AssertionError,IndexError):pass
  else:raise AssertionError('Malformed stream accepted')

tests();rows=[]
for file in sorted((PRIVATE/'packed_xml').rglob('*.xml')):
 raw=file.read_bytes();decoded=unpack_old(raw)
 root=None;parse_error=None
 try:root=ET.fromstring(decoded.rstrip(b'\0'))
 except ET.ParseError as e:parse_error=str(e)
 target=PRIVATE/'decoded_xml'/file.relative_to(PRIVATE/'packed_xml');target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(decoded)
 tables=[]
 for el in (root.iter() if root is not None else []):
  if el.get('name') and ('table' in el.tag.lower() or 'numrows' in el.attrib):
   tables.append(dict(tag=el.tag,name=el.get('name'),declared_rows=el.get('numrows'),actual_child_elements=len(el)))
 rows.append(dict(file=str(file.relative_to(PRIVATE/'packed_xml')).replace('\\','/'),packed_bytes=len(raw),decoded_bytes=len(decoded),sha256=hashlib.sha256(decoded).hexdigest(),root_tag=root.tag if root is not None else None,xml_parse_error=parse_error,trailing_nuls=len(decoded)-len(decoded.rstrip(b'\0')),tables=tables))
(ROOT/'analysis/decoded_xml_tables.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps(dict(xml_files_decoded=len(rows),decoded_bytes=sum(x['decoded_bytes'] for x in rows),xml_parsed=sum(x['xml_parse_error'] is None for x in rows),xml_parse_errors={x['file']:x['xml_parse_error'] for x in rows if x['xml_parse_error']},synthetic_copy_mode_and_rejection_checks='passed',english_tables={x['file']:[t['name'] for t in x['tables']] for x in rows if x['file'].endswith('_en.xml')}),indent=2))
