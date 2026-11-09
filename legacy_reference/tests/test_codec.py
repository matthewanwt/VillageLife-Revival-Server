import unittest
from codec import xor,encode,decode
class WireTests(unittest.TestCase):
 def test_known_xor_vector(self):
  self.assertEqual(xor(b'abc'),bytes([0x31,0x0e,0x02]))
 def test_native_plain_form_and_binary_roundtrip(self):
  request={'data':{'calls':[{'id':'1','service':'ClientStartupService/GetStartupInfo','data':{}}]}}
  self.assertEqual(decode(encode(request,False,True)),(request,'plain'))
  self.assertEqual(decode(encode(request)),(request,'zlib-xor'))
 def test_reject_unknown_and_incomplete_data(self):
  with self.assertRaises(Exception):decode(b'not-json')
  with self.assertRaises(Exception):decode(encode({'ok':True})[:-5])
if __name__=='__main__':unittest.main()
