import hashlib,struct,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import import_game
class OwnGameImportTests(unittest.TestCase):
 def test_wrong_archive_is_rejected_before_creating_player_data_or_running_signer(self):
  with tempfile.TemporaryDirectory() as folder:
   base=Path(folder);source=base/'wrong.xapk';source.write_bytes(b'wrong input');destination=base/'player'
   with patch.object(import_game.subprocess,'run') as run,self.assertRaises(ValueError):import_game.prepare_game(source,destination)
   self.assertFalse(destination.exists());run.assert_not_called();self.assertEqual(source.read_bytes(),b'wrong input')
 def test_legacy_packed_copy_modes_decode_exactly_and_reject_invalid_backrefs(self):
  def wrap(data,length):return b'SPK1'+struct.pack('<I',length)+data
  for data,length,expected in [(b'\x03abc\x40\x02\0',6,b'abcabc'),(b'\x03abc\x80\0\x02\0',7,b'abcabca'),(b'\x03abc\xc0\0\0\x02\0',8,b'abcabcab'),(b'\x01A\x40\0\0',4,b'AAAA')]:
   with self.subTest(data=data):self.assertEqual(import_game.unpack_old(wrap(data,length)),expected)
  for data in [wrap(b'\x40\0\0',3),wrap(b'\x03abc\0',4),b'not-SPK1-data']:
   with self.subTest(data=data),self.assertRaises((ValueError,IndexError)):import_game.unpack_old(data)
 def test_tcf_index_checks_bounds_and_retains_original_file_offsets(self):
  with tempfile.TemporaryDirectory() as folder:
   file=Path(folder)/'test.obb';names=b'files/test\0';payload=b'asset';file.write_bytes(struct.pack('<4I',int.from_bytes(b'TCF1','little'),1,len(names),len(payload))+struct.pack('<4I',0,0,len(payload),0)+names+payload)
   row=import_game.tcf_index(file)[0];self.assertEqual(row['path'],'files/test');self.assertEqual(file.read_bytes()[row['offset_in_tcf']:],payload)
   broken=bytearray(file.read_bytes());struct.pack_into('<I',broken,20,1000);file.write_bytes(broken)
   with self.assertRaises(ValueError):import_game.tcf_index(file)
 def test_unrecognized_executable_cannot_be_endpoint_patched(self):
  with self.assertRaises(ValueError):import_game.patch_library(b'not the supported original library')
if __name__=='__main__':unittest.main()
