"""BlueStacks read-only Windows diagnostics; synthetic tests need no Windows VM."""
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from platforms.bluestacks.host_network import address_class, inspect_host, summarise
from platforms.bluestacks.instances import available_instances, select_instance, diagnostic_port_map
from diagnose_network import build_report
from export_diagnostics import export_bundle
from runtime_errors import VillageRuntimeError
import zipfile


CONFIG = '''bst.instance.Pie64.display_name="Main"
bst.instance.Pie64.adb_port="5555"
bst.instance.Pie64.status.adb_port="5555"
bst.instance.Pie64_4.display_name="VL test"
bst.instance.Pie64_4.adb_port="5595"
bst.instance.Pie64_4.status.adb_port="5595"
'''
HOST_RAW = {
    'processes': [
        {'name': 'HD-Player.exe', 'pid': 101, 'instance': 'Pie64_4', 'command_line': 'confidential'},
        {'name': 'BstkSVC.exe', 'pid': 102, 'instance': None},
        {'name': 'UnrelatedBrowser.exe', 'pid': 103, 'instance': 'Pie64'},
    ],
    'connections': [
        {'pid': 101, 'remote': '8.8.8.8', 'state': 'Established'},
        {'pid': 102, 'remote': '127.0.0.1', 'state': 'Established'},
        {'pid': 103, 'remote': '9.9.9.9', 'state': 'Established'},
    ],
    'listeners80': [{'pid': 102}],
    'adapters': [{'description': 'Wireless 802.11 device', 'status': 'Up', 'medium': '802.11'}],
    'hyperv_firewall_cmdlet': False, 'net_tcp_cmdlet': True, 'errors': []
}


class InstanceLivePortTests(unittest.TestCase):
    def test_user_reported_pie_ports_parsed_without_guessing(self):
        rows = available_instances(CONFIG)
        self.assertEqual([(x['id'], x['adb_port'], x['status_adb_port']) for x in rows],
                         [('Pie64', 5555, 5555), ('Pie64_4', 5595, 5595)])

    def test_launcher_refuses_port_disagreement_and_diagnostic_reports_it(self):
        text = CONFIG.replace('Pie64_4.status.adb_port="5595"', 'Pie64_4.status.adb_port="6001"')
        # A stale unrelated VM must not prevent launching the healthy one.
        strict = available_instances(text)
        self.assertEqual(select_instance(strict, 'Pie64')['id'], 'Pie64')
        with self.assertRaises(VillageRuntimeError) as caught:
            select_instance(strict, 'Pie64_4')
        self.assertEqual(caught.exception.code, 'VL-BS-PORT-DIVERGED')
        rows = diagnostic_port_map(text)
        self.assertIn('configured_live_port_mismatch', rows[-1]['warnings'])

    def test_missing_status_field_does_not_break_existing_player_setup(self):
        text = CONFIG.replace('bst.instance.Pie64.status.adb_port="5555"\n', '')
        self.assertIsNone(available_instances(text)[0]['status_adb_port'])


class HostInventoryTests(unittest.TestCase):
    def test_ip_classification(self):
        self.assertEqual(address_class('8.8.8.8'), 'public')
        self.assertEqual(address_class('127.0.0.1'), 'loopback')
        self.assertEqual(address_class('192.168.1.1'), 'private_or_special')
        self.assertEqual(address_class('::1'), 'loopback')

    def test_minimised_output_never_exposes_network_identifiers(self):
        data = summarise(HOST_RAW)
        rendered = json.dumps(data)
        for sensitive in ('8.8.8.8', '9.9.9.9', '127.0.0.1', 'confidential', 'Wireless 802.11 device', 'UnrelatedBrowser.exe'):
            self.assertNotIn(sensitive, rendered)
        self.assertEqual(data['observed_tcp_remote_classes'], {'public': 1, 'loopback': 1})
        self.assertEqual(data['port80_listener_count'], 1)
        self.assertEqual(data['processes'][0]['instance'], 'Pie64_4')
        self.assertFalse(data['hyperv_firewall_cmdlet_present'])

    def test_nonwindows_returns_useful_error(self):
        self.assertEqual(inspect_host(platform='posix')['status'], 'unavailable')

    def test_windows_query_is_solely_read_only_and_reports_results(self):
        class Response:
            returncode = 0
            stdout = json.dumps(HOST_RAW).encode()
        called = []
        def fake_runner(argv, **kwargs):
            called.append((argv, kwargs))
            return Response()
        result = inspect_host(platform='nt', runner=fake_runner)
        self.assertEqual(result['status'], 'collected')
        self.assertEqual(len(called), 1)
        command = called[0][0][-1]
        for forbidden in ('New-NetFirewallRule', 'Set-NetFirewallRule', 'Remove-NetFirewallRule', 'modifyvm', 'adb connect', 'Stop-Process'):
            self.assertNotIn(forbidden, command)


class CliInventoryTests(unittest.TestCase):
    def test_selected_vm_report_readonly_and_report_omits_raw_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = build_report(root=tmp, instance='Pie64_4', host_report=summarise(HOST_RAW), config_text=CONFIG)
            self.assertEqual(len(report['instances']), 2)
            self.assertTrue(report['instances'][1]['player_process_observed'])
            self.assertEqual(report['selected_instance'], 'Pie64_4')
            self.assertEqual(report['guest']['status'], 'not_tested')
            self.assertFalse(report['modifies_windows_or_bluestacks'])
            self.assertNotIn('8.8.8.8', json.dumps(report))

    def test_no_automatic_selection_if_two_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = build_report(root=tmp, host_report=summarise(HOST_RAW), config_text=CONFIG)
            self.assertIsNone(report['selected_instance'])
            self.assertIn('will not guess', report['next_action'])

    def test_disabled_unsafe_guest_probe_on_mismatch(self):
        text = CONFIG.replace('Pie64_4.status.adb_port="5595"', 'Pie64_4.status.adb_port="6001"')
        with tempfile.TemporaryDirectory() as tmp:
            report = build_report(root=tmp, instance='Pie64_4', host_report=summarise(HOST_RAW), config_text=text, probe_guest=True)
            self.assertEqual(report['guest']['status'], 'not_tested')
            self.assertIn('inconsistent', report['guest']['reason'])

    def test_support_bundle_includes_minimised_network_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report = build_report(root=root, instance='Pie64_4', host_report=summarise(HOST_RAW), config_text=CONFIG)
            (root / 'network-topology-report.json').write_text(json.dumps(report), encoding='utf-8')
            with zipfile.ZipFile(export_bundle(root)) as archive:
                self.assertIn('reports/network-topology-report.json', archive.namelist())
                body = archive.read('reports/network-topology-report.json').decode()
                self.assertNotIn('8.8.8.8', body)


if __name__ == '__main__':
    unittest.main()
