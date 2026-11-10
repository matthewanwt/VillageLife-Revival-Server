import tempfile
import unittest
import zipfile
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from prepare_original_client import PATCHES, patch_library, unpack_game, make_unsigned

class PreparationTests(unittest.TestCase):
    def test_local_patch_rejects_unknown_client(self):
        with self.assertRaises(ValueError):patch_library(b'not the game')
    def test_faithful_endpoint_replacement_and_original_unchanged(self):
        original=b'ABCD'+b'**'.join(old+b'\x00' for old in PATCHES)+b'EF'
        updated=patch_library(original)
        self.assertEqual(len(original),len(updated))
        for old,new in PATCHES.items():
            self.assertNotIn(old+b'\0',updated)
            self.assertIn(new+b'\0'*(len(old)-len(new)+1),updated)
        self.assertNotEqual(original,updated)
    def test_xapk_extraction_and_modified_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);xapk=root/'game.xapk';apk=root/'game.apk';original_library=b'::'.join(k+b'\0' for k in PATCHES)
            with zipfile.ZipFile(apk,'w') as a:
                a.writestr('lib/armeabi-v7a/libpdandroid.so',original_library)
                a.writestr('assets/origmanifest.xml',b'<manifest/>')
                a.writestr('META-INF/CERT.SF',b'original signing metadata')
            with zipfile.ZipFile(xapk,'w') as z:
                z.write(apk,'com.playdemic.villagelife.android.apk')
                z.writestr('main.241.com.playdemic.villagelife.android.obb',b'TCF1-synthetic')
            out=root/'local';raw,expansion=unpack_game(xapk,out)
            self.assertEqual(expansion.read_bytes(),b'TCF1-synthetic')
            unsigned=make_unsigned(raw,out)
            with zipfile.ZipFile(unsigned) as z:
                self.assertNotIn('META-INF/CERT.SF',z.namelist())
                self.assertEqual(z.read('lib/armeabi-v7a/libpdandroid.so'),patch_library(original_library))
            with zipfile.ZipFile(raw) as z:
                self.assertEqual(z.read('lib/armeabi-v7a/libpdandroid.so'),original_library)
