import base64,hashlib,json,zipfile
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'analysis/private'
def sections(raw):
 out=[]
 for section in raw.replace(b'\r\n',b'\n').split(b'\n\n'):
  lines=[]
  for line in section.split(b'\n'):
   if line.startswith(b' ') and lines:lines[-1]+=line[1:]
   elif line:lines.append(line)
  out.append(dict(x.decode('utf-8').split(': ',1) for x in lines if b': ' in x))
 return out
mf=(p/'MANIFEST.MF').read_bytes();sf=(p/'CERT.SF').read_bytes()
assert base64.b64decode(sections(sf)[0]['SHA1-Digest-Manifest'])==hashlib.sha1(mf).digest()
count=0
with zipfile.ZipFile(p/'client-original-copy.apk') as z:
 for sec in sections(mf)[1:]:
  if 'Name' not in sec:continue
  assert base64.b64decode(sec['SHA1-Digest'])==hashlib.sha1(z.read(sec['Name'])).digest(),sec['Name'];count+=1
result=dict(legacy_manifest_digest_valid=True,signed_entry_digests_valid=count,apk_v2_verified=False,chain_trust_established=False)
(p.parent/'jar_entry_digest_verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
