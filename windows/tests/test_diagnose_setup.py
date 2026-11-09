import unittest
from diagnose_setup import parse_remote_status


class SetupDiagnosticTests(unittest.TestCase):
    def test_remote_failure_is_distinct_from_transport_success(self):
        self.assertEqual(parse_remote_status('Network unreachable\r\n__VL_DIAG_EXIT=1\r\n'), 1)
        self.assertEqual(parse_remote_status('\n__VL_DIAG_EXIT=0\n'), 0)

    def test_missing_duplicate_or_invalid_remote_status_is_unknown(self):
        for value in ['', 'device offline', '__VL_DIAG_EXIT=0\n__VL_DIAG_EXIT=1\n',
                      '__VL_DIAG_EXIT=256\n', '__VL_DIAG_EXIT=-1\n', 'prefix__VL_DIAG_EXIT=0']:
            with self.subTest(value=value):
                self.assertIsNone(parse_remote_status(value))
