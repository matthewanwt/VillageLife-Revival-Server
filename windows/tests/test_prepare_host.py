import hashlib,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
import prepare_host
class HostInputsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.archive=self.root/'original.xapk';self.payload=b'original expansion fixture'
  with zipfile.ZipFile(self.archive,'w') as z:z.writestr('Android/obb/package/'+prepare_host.OBB,self.payload)
  self.original=self.archive.read_bytes();self.target=self.root/'analysis/runtime_inputs'/prepare_host.OBB
  for name,value in [('ARCHIVE_SHA',hashlib.sha256(self.original).hexdigest()),('OBB_SHA',hashlib.sha256(self.payload).hexdigest())]:
   scope=patch.object(prepare_host,name,value);scope.start();self.addCleanup(scope.stop)
 def test_extract_and_repair_interrupted_copy_without_changing_archive(self):
  self.target.parent.mkdir(parents=True);self.target.write_bytes(b'interrupted old copy')
  self.assertEqual(prepare_host.prepare(self.root),self.target);self.assertEqual(self.target.read_bytes(),self.payload)
  self.assertEqual(self.archive.read_bytes(),self.original);self.assertFalse(self.target.with_suffix('.obb.partial').exists())
 def test_reject_wrong_source_before_writing(self):
  self.archive.write_bytes(b'wrong archive')
  with self.assertRaises(RuntimeError):prepare_host.prepare(self.root)
  self.assertFalse(self.target.exists())
 def test_failed_extraction_preserves_existing_file_and_cleans_partial(self):
  self.target.parent.mkdir(parents=True);self.target.write_bytes(b'previous file')
  with patch.object(prepare_host,'OBB_SHA','wrong'):
   with self.assertRaises(RuntimeError):prepare_host.prepare(self.root)
  self.assertEqual(self.target.read_bytes(),b'previous file');self.assertFalse(self.target.with_suffix('.obb.partial').exists())
if __name__=='__main__':unittest.main()
