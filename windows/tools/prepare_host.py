"""Verify private source inputs and extract the unchanged expansion file atomically."""
from pathlib import Path
import hashlib,os,shutil,zipfile
ROOT=Path(__file__).resolve().parents[1]
ARCHIVE_SHA='8d25823b824ba766b38e53aedb74b270a0254e6bf3fbbcf1a858b090a66b5c08'
OBB_SHA='543ef1c7409dbe6fdc79d4fa78faecc2e2b56b2fbbf0bd04f709f938d4965269'
OBB='main.241.com.playdemic.villagelife.android.obb'
def digest(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def prepare(root=ROOT):
 root=Path(root);archives=list(root.glob('*.xapk'))
 if len(archives)!=1 or digest(archives[0])!=ARCHIVE_SHA:raise RuntimeError('Exactly one verified original XAPK is required.')
 target=root/'analysis/runtime_inputs'/OBB
 if target.exists() and digest(target)==OBB_SHA:return target
 target.parent.mkdir(parents=True,exist_ok=True);temp=target.with_suffix('.obb.partial')
 try:
  with zipfile.ZipFile(archives[0]) as archive:
   names=[v.filename for v in archive.infolist() if v.filename.endswith('/'+OBB)]
   if len(names)!=1:raise RuntimeError('Original expansion entry missing or ambiguous.')
   with archive.open(names[0]) as source,temp.open('wb') as dest:
    shutil.copyfileobj(source,dest);dest.flush();os.fsync(dest.fileno())
  if digest(temp)!=OBB_SHA:raise RuntimeError('Expansion file hash mismatch; existing file preserved.')
  os.replace(temp,target)
 finally:
  if temp.exists():temp.unlink()
 return target
if __name__=='__main__':
 prepare();print('Original archive and expansion file verified. Private backend inputs ready.')
