"""Legacy transport codec recovered from native functions; no remote connections."""
import json,zlib
KEY=b'PlaydemicLTD'
MAX_DECODED=8*1024*1024

def xor(data,key=KEY):
 if not key:raise ValueError('empty protocol key')
 return bytes(value^key[i%len(key)] for i,value in enumerate(data))

def encode(document,compressed=True,prefix=False):
 raw=json.dumps(document,separators=(',',':'),ensure_ascii=False).encode('utf-8')
 if compressed:return xor(zlib.compress(raw))
 return (b'q=' if prefix else b'')+raw

def decode(data):
 mode='plain'
 if len(data)>MAX_DECODED:raise ValueError('request too large')
 if not data.startswith((b'q=',b'{',b'[')):
  de=zlib.decompressobj();data=de.decompress(xor(data),MAX_DECODED+1)
  if not de.eof or len(data)>MAX_DECODED:raise ValueError('invalid or oversized compressed message')
  mode='zlib-xor'
 if data.startswith(b'q='):data=data[2:]
 return json.loads(data.decode('utf-8')),mode
