import unittest
from villagelife.protocol.legacy_codec import encode, decode
from villagelife.protocol.legacy_adapter import LegacyProtocolAdapter, MissingLegacyHandler
from villagelife.core.errors import NotImplementedRule


class ProtocolTests(unittest.TestCase):
    def test_original_wire_roundtrip(self):
        data = {'deviceId': 'TEST', 'data': {'calls': [{'service': 'Sample'}]}, 'unicode': 'é'}
        for compression in (True, False):
            encoded = encode(data, compressed=compression)
            decoded, mode = decode(encoded)
            self.assertEqual(decoded, data)
            self.assertEqual(mode, 'zlib-xor' if compression else 'plain')

    def test_missing_original_endpoint_is_explicit(self):
        with self.assertRaises(NotImplementedRule):
            LegacyProtocolAdapter(MissingLegacyHandler()).handle('/web/ClientService/Process', encode({}, compressed=False))


if __name__ == '__main__':
    unittest.main()
