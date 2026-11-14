"""Simulates multiple BlueStacks VMs without installing or starting BlueStacks."""
from pathlib import Path
from subprocess import CompletedProcess
import tempfile
import unittest
from unittest.mock import patch
from villagelife.platforms.bluestacks import (parse_instances, select_by_id, bind_instance,
    verify_binding, InstanceError, Instance, adb_status, start_bound_instance)
from villagelife.platforms.network import report

CONFIG='''bst.instance.Pie64.display_name="Personal"
bst.instance.Pie64.adb_port="5555"
bst.instance.Pie64.status.adb_port="5555"
bst.instance.Pie64_4.display_name="VLTest1"
bst.instance.Pie64_4.adb_port="5595"
bst.instance.Pie64_4.status.adb_port="5595"
'''


class InstanceIsolationTests(unittest.TestCase):
    def test_guest_probe_uses_path_wget_and_checks_response(self):
        from villagelife.platforms.original_client import probe_local_server
        binding = Path('selected-instance.json')
        with patch('villagelife.platforms.original_client._adb', side_effect=[
            CompletedProcess([], 0, b'{"service":"villagelife-revival-server"}', b''),
            CompletedProcess([], 0, b'', b'toybox: Unknown command wget'),
            CompletedProcess([], 0, b'', b'wget: Connection refused'),
        ]) as adb:
            probe_local_server(binding)
            command = adb.call_args.args[1][-1]
            self.assertIn('command -v wget', command)
            self.assertIn('10.0.2.2:80/health', command)
            with self.assertRaisesRegex(InstanceError, 'VL-GUEST-PROBE-UNAVAILABLE'):
                probe_local_server(binding)
            with self.assertRaisesRegex(InstanceError, 'VL-GUEST-BACKEND-UNREACHABLE.*Connection refused'):
                probe_local_server(binding)

    def test_expansion_repair_preserves_apk_and_activates_only_complete_file(self):
        from villagelife.platforms.original_client import OBB_NAME, repair_prepared_obb
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            obb = root / OBB_NAME
            obb.write_bytes(b'obb')
            with patch('villagelife.platforms.original_client.prepared_apk_installed', return_value=True), \
                    patch('villagelife.platforms.original_client._obb_matches',
                          side_effect=[False, False, True, True]), \
                    patch('villagelife.platforms.original_client._adb',
                          return_value=CompletedProcess([], 0, b'', b'')) as adb:
                repair_prepared_obb(root / 'binding.json', root / 'client.apk', obb)
                actions = [call.args[1] for call in adb.call_args_list]
                self.assertEqual([args[:2] for args in actions],
                                 [['shell', 'mkdir'], ['push', str(obb)], ['shell', 'mv']])
                self.assertTrue(actions[1][-1].endswith('.vl-part'))
                self.assertEqual(actions[2][-2], actions[1][-1])

    def test_guided_probe_distinguishes_transport_from_boot(self):
        selected = Instance('Pie64_4', 'Village Life', 5595, 5595)
        binding = Path('selected-instance.json')
        serial = '127.0.0.1:5595'
        for device, boot, expected in [
            (b'offline', b'', 'unreachable'),
            (b'device', b'0', 'booting'),
            (b'device', b'1\r\n', 'ready'),
        ]:
            with self.subTest(expected=expected), \
                    patch('villagelife.platforms.bluestacks.installation', return_value=Path('BlueStacks')), \
                    patch('villagelife.platforms.bluestacks.list_instances', return_value=[selected]), \
                    patch('villagelife.platforms.bluestacks.verify_binding', return_value=selected), \
                    patch('villagelife.platforms.bluestacks.subprocess.run', side_effect=[
                        CompletedProcess([], 1, b'already connected', b''),
                        CompletedProcess([], 0, device, b''),
                        CompletedProcess([], 0, boot, b''),
                    ]) as run:
                result = adb_status(binding, once=True)
                self.assertEqual(result['status'], expected)
                self.assertEqual(result['connected'], expected != 'unreachable')
                self.assertEqual(run.call_args_list[1].args[0][1:], ['-s', serial, 'get-state'])
                self.assertEqual(run.call_count, 2 if expected == 'unreachable' else 3)

    def test_first_boot_opens_only_the_selected_instance_and_waits_before_adb(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            binding = root / 'binding.json'
            new = Instance('Pie64_8', 'Fresh instance', 5635, 5555)
            personal = Instance('Pie64', 'Personal', 5555, 5555)
            rows = [personal, new]
            bind_instance(binding, select_by_id(rows, new.id, check_live_port=False), root)
            with patch('villagelife.platforms.bluestacks.installation', return_value=root), \
                    patch('villagelife.platforms.bluestacks.list_instances', return_value=rows), \
                    patch('villagelife.platforms.bluestacks.subprocess.Popen') as launch, \
                    patch('villagelife.platforms.bluestacks.subprocess.run') as adb:
                self.assertEqual(start_bound_instance(binding), new.id)
                self.assertEqual(launch.call_args.args[0], [str(root / 'HD-Player.exe'), '--instance', new.id])
                self.assertEqual(adb_status(binding, once=True)['status'], 'initializing')
                self.assertEqual(adb_status(binding, once=True)['status'], 'initializing')
                adb.assert_not_called()
                with self.assertRaisesRegex(InstanceError, 'VL-BS-PORT-DIVERGED'):
                    verify_binding(binding, rows, root)
                rows[1] = Instance(new.id, new.display_name, 5635, 5635)
                adb.side_effect = [CompletedProcess([], 0, b'', b''),
                                   CompletedProcess([], 0, b'device', b''),
                                   CompletedProcess([], 0, b'1', b'')]
                self.assertEqual(adb_status(binding, once=True)['status'], 'ready')
                self.assertEqual(adb.call_args_list[0].args[0][1:], ['connect', '127.0.0.1:5635'])

    def test_explicit_selection_never_falls_back(self):
        rows=parse_instances(CONFIG)
        self.assertEqual(select_by_id(rows,'Pie64_4').adb_port,5595)
        for bad in ('VLTest1','Pie64_3','Pie64_5',''):
            with self.assertRaises(InstanceError):select_by_id(rows,bad)

    def test_selection_sticks_and_every_config_drift_fails(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); inst=root/'binding.json'; app=root/'bluestacks'; app.mkdir()
            rows=parse_instances(CONFIG)
            bind_instance(inst,select_by_id(rows,'Pie64_4'),app)
            self.assertEqual(verify_binding(inst,rows,app).id,'Pie64_4')
            for change in (CONFIG.replace('VLTest1','Renamed'),
                           CONFIG.replace('5595','6000'),
                           CONFIG.replace('bst.instance.Pie64_4','bst.instance.Pie64_7')):
                with self.assertRaises(InstanceError):verify_binding(inst,parse_instances(change),app)
            with self.assertRaises(InstanceError):verify_binding(inst,rows,root/'different')
            self.assertTrue(inst.exists())

    def test_unrelated_instance_stale_port_does_not_break_selected_vm(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); app=root/'app';app.mkdir(); binding=root/'binding.json'
            rows=parse_instances(CONFIG)
            bind_instance(binding, select_by_id(rows,'Pie64_4'),app)
            changed=parse_instances(CONFIG.replace('Pie64.status.adb_port="5555"','Pie64.status.adb_port="6000"'))
            self.assertEqual(verify_binding(binding,changed,app).id,'Pie64_4')
            with self.assertRaises(InstanceError):select_by_id(changed,'Pie64')

    def test_restart_force_stops_only_the_bound_game_before_launch(self):
        from subprocess import CompletedProcess
        from unittest.mock import call
        from villagelife.platforms.original_client import PACKAGE, launch

        binding = Path('selected-instance.json')
        with patch('villagelife.platforms.original_client._adb', side_effect=[
            CompletedProcess([],0,b'',b''),
            CompletedProcess([],0,b'Events injected: 1',b''),
        ]) as adb:
            launch(binding,restart=True)
        self.assertEqual(adb.call_args_list,[
            call(binding,['shell','am','force-stop',PACKAGE],timeout=15),
            call(binding,['shell','monkey','-p',PACKAGE,'1'],timeout=30),
        ])

    def test_network_report_explicitly_disclaims_isolation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); config=root/'bluestacks.conf';config.write_text(CONFIG)
            result=report(root/'unbound.json',conf=config)
            self.assertFalse(result['policy_verified'])
            self.assertFalse(result['guest_egress_verified'])
            self.assertFalse(result['changes_applied'])
            self.assertEqual(len(result['configured_instances']),2)

    def test_diagnostics_distinguishes_a_stopped_backend_from_a_guest_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / 'bluestacks.conf'
            config.write_text(CONFIG)
            binding = root / 'binding.json'
            with patch('villagelife.platforms.network._host_backend_ready',return_value=False), \
                    patch('villagelife.platforms.original_client.probe_local_server') as probe:
                output = report(binding,conf=config,local_port=80)
                self.assertEqual(output['guest_to_local_check'],'backend_unavailable')
                probe.assert_not_called()
            with patch('villagelife.platforms.network._host_backend_ready',return_value=True), \
                    patch('villagelife.platforms.original_client.probe_local_server',
                          side_effect=InstanceError('VL-GUEST-BACKEND-UNREACHABLE','Unavailable')):
                output = report(binding,conf=config,local_port=80)
                self.assertEqual(output['guest_to_local_check'],'failed')
                self.assertEqual(output['guest_to_local_error_code'],'VL-GUEST-BACKEND-UNREACHABLE')

class SeparateInstanceDataTests(unittest.TestCase):
    def test_two_instance_bindings_and_separate_databases_never_mix(self):
        from villagelife.persistence.sqlite_store import SqliteSaveRepository
        from villagelife.core.model import empty_native_village
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); install=root/'fake_install';install.mkdir()
            rows=parse_instances(CONFIG)
            snapshots=[]
            for ident, unique in [('Pie64','WOODLAND_A'),('Pie64_4','MOUNTAIN_B')]:
                profile=root/ident;profile.mkdir()
                binding=profile/'binding.json'
                bind_instance(binding,select_by_id(rows,ident),install)
                database=SqliteSaveRepository(profile/'worlds.sqlite3')
                account=database.create_account(unique)
                state=empty_native_village()
                state['entities'][unique]={'originalToken':unique}
                village=database.create_village(account,state)
                snapshots.append((ident,profile,village,unique))
            a_id,a_root,a_village,a_token=snapshots[0]
            b_id,b_root,b_village,b_token=snapshots[1]
            self.assertEqual(verify_binding(a_root/'binding.json',rows,install).id,a_id)
            self.assertEqual(verify_binding(b_root/'binding.json',rows,install).id,b_id)
            read_a=SqliteSaveRepository(a_root/'worlds.sqlite3').read_village(a_village)
            read_b=SqliteSaveRepository(b_root/'worlds.sqlite3').read_village(b_village)
            self.assertIn(a_token,read_a.payload['entities'])
            self.assertNotIn(b_token,read_a.payload['entities'])
            self.assertIn(b_token,read_b.payload['entities'])
            self.assertNotIn(a_token,read_b.payload['entities'])
            self.assertNotEqual(read_a.account_id,read_b.account_id)
