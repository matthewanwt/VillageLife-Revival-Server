"""Executable synthetic regression cases; require no emulator or game files."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from platforms.bluestacks.discovery import discover_bluestacks
from platforms.bluestacks.instances import available_instances, select_instance, validate_binding, make_binding
from platforms.bluestacks.ports import port_available, require_client_port
from platforms.bluestacks.adb import ADBClient, ADBResult
from platforms.bluestacks.net_assurance import verify_guest_network
from runtime_errors import VillageRuntimeError
from export_diagnostics import redact, export_bundle
import json
import zipfile


class DiscoveryTests(unittest.TestCase):
    def test_autodetect_from_known_programfiles_location_and_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            installation = Path(tmp)/'BlueStacks_nxt'
            installation.mkdir()
            for binary in ('HD-Adb.exe', 'HD-Player.exe', 'BstkVMMgr.exe'):
                (installation/binary).touch()
            found = discover_bluestacks({'ProgramFiles': tmp}, candidates=None, require_manager=True)
            self.assertEqual(found.directory, installation)
            overridden = discover_bluestacks({'VILLAGELIFE_BLUESTACKS_HOME': str(installation)}, candidates=[], require_manager=True)
            self.assertEqual(overridden.directory, installation)

    def test_missing_executable_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(VillageRuntimeError) as caught:
            discover_bluestacks({}, candidates=[tmp])
        self.assertIn('VL-BS-NOT-FOUND', str(caught.exception))

    def test_port_change_and_other_instance_refused(self):
        text = 'bst.instance.Pie64_1.display_name="Village café 村"\n' + 'bst.instance.Pie64_1.adb_port="5565"\n'
        old = select_instance(available_instances(text), 'Pie64_1')
        with tempfile.TemporaryDirectory() as tmp:
            inst = discover_mock_installation(Path(tmp))
            settings = {'instance':'Pie64_1','adb_port':5565,'instance_binding':make_binding(old,inst)}
            validate_binding(settings,old,inst)
            with self.assertRaises(VillageRuntimeError):
                validate_binding(settings,{**old,'adb_port':5575},inst)
            with self.assertRaises(VillageRuntimeError):
                validate_binding(settings,old,discover_mock_installation(Path(tmp)/'other'))



    def test_deleted_instance_never_falls_back_to_default(self):
        config = 'bst.instance.Pie64.display_name="Default"\nbst.instance.Pie64.adb_port="5555"\n'
        with self.assertRaises(VillageRuntimeError) as caught:
            select_instance(available_instances(config), 'Pie64_4')
        self.assertEqual(caught.exception.code, 'VL-BS-INSTANCE-MISSING')

    def test_renamed_instance_fails_with_specific_recovery_message(self):
        config = 'bst.instance.Pie64_4.display_name="Renamed VM"\nbst.instance.Pie64_4.adb_port="5595"\n'
        chosen = select_instance(available_instances(config), 'Pie64_4')
        with tempfile.TemporaryDirectory() as tmp:
            installation = discover_mock_installation(Path(tmp))
            settings = {
                'instance': 'Pie64_4', 'adb_port': 5595,
                'instance_display_name': 'VLTest1',
                'instance_binding': make_binding(chosen, installation),
            }
            with self.assertRaises(VillageRuntimeError) as caught:
                validate_binding(settings, chosen, installation)
            self.assertEqual(caught.exception.code, 'VL-BS-INSTANCE-RENAMED')

    def test_stale_instance_port_fails_without_switching(self):
        config = 'bst.instance.Pie64_4.display_name="VLTest1"\nbst.instance.Pie64_4.adb_port="5595"\n'
        chosen = select_instance(available_instances(config), 'Pie64_4')
        with tempfile.TemporaryDirectory() as tmp:
            installation = discover_mock_installation(Path(tmp))
            with self.assertRaises(VillageRuntimeError) as caught:
                validate_binding({'instance': 'Pie64_4', 'adb_port': 5555}, chosen, installation)
            self.assertEqual(caught.exception.code, 'VL-BS-INSTANCE-CHANGED')

def discover_mock_installation(p):
    from platforms.bluestacks.discovery import BlueStacksInstallation
    return BlueStacksInstallation(p)


class AdbTests(unittest.TestCase):
    def test_connect_timeout_is_retried_then_boot_succeeds(self):
        cli = ADBClient(Path('HD-Adb.exe'), '127.0.0.1:5565')
        responses = iter([ADBResult(124,'timeout'),ADBResult(1,'offline'),ADBResult(0,'connected'),ADBResult(0,'1')])
        clock_values = iter([0,0,0,0,0,0,0,0,0,0])
        with patch.object(cli, '_call', side_effect=lambda *args, **kwargs: next(responses)):
            with patch('platforms.bluestacks.adb.time.sleep',return_value=None):
                result = cli.wait_for_boot(deadline_seconds=120,clock=lambda: 0,sleep=lambda _:None)
        self.assertEqual(result,2)

    def test_deadline_stops_retry_loop_with_helpful_code(self):
        cli=ADBClient(Path('HD-Adb.exe'),'127.0.0.1:5565')
        current=[0]
        def clock():
            current[0]+=1
            return current[0]
        with patch.object(cli, '_call',return_value=ADBResult(124,'timeout')):
            with self.assertRaises(VillageRuntimeError) as caught:
                cli.wait_for_boot(deadline_seconds=5,clock=clock,sleep=lambda _:None)
        self.assertEqual(caught.exception.code,'VL-ADB-BOOT-TIMEOUT')


class NetworkTests(unittest.TestCase):
    class Guest:
        def __init__(self, codes):self.codes=iter(codes)
        def command(self, *args, timeout=12):
            android_rc=next(self.codes)
            return ADBResult(0,f'no route\n__VL_NETWORK_EXIT__={android_rc}\n')
    def test_three_blocked_probes_pass(self):
        state=verify_guest_network(self.Guest([1,1,1]),'Pie64_1',config={'verified':True})
        self.assertTrue(state['isolated'])
        self.assertEqual(len(state['checks']),3)
    def test_any_guest_egress_forces_rejection(self):
        for codes in ([1,0,1],[1,1,127],[1,1,1]):
            result=verify_guest_network(self.Guest(codes),'Pie64_1',config={'verified':codes!=[1,1,1]})
            self.assertFalse(result['isolated'])
    def test_port_80_conflict_cannot_be_silently_replaced(self):
        import socket
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port=sock.getsockname()[1]
            with self.assertRaises(VillageRuntimeError): require_client_port(port)


class DiagnosticsTests(unittest.TestCase):
    def test_redacts_join_code_bearer_email_user_path(self):
        given='join_code=SECRET_TOKEN Authorization:Bearer ABC123 matt@example.org C:\\Users\\matthew\\Documents'
        clean=redact(given)
        self.assertNotIn('SECRET_TOKEN',clean)
        self.assertNotIn('ABC123',clean)
        self.assertNotIn('matt@example.org',clean)
        self.assertNotIn('matthew\\Documents',clean)
    def test_zip_contains_only_allowlisted_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'play-settings.json').write_text('{"join_code":"SECRET"}')
            (root/'latest-runtime-error.json').write_text('{"code":"VL-PORT-IN-USE"}')
            (root/'backend').mkdir()
            (root/'backend'/'private_state').mkdir()
            (root/'backend'/'private_state'/'save.json').write_text('SENSITIVE')
            file=export_bundle(root)
            with zipfile.ZipFile(file) as archive:
                names=archive.namelist()
                self.assertIn('reports/latest-runtime-error.json',names)
                self.assertNotIn('backend/private_state/save.json',names)
                self.assertNotIn('play-settings.json',names)
                self.assertNotIn('SENSITIVE', '\n'.join(archive.read(n).decode() for n in names))


if __name__=='__main__':unittest.main()
