"""BlueStacks manager selection tests that never touch a VM."""
import unittest
from unittest.mock import Mock
from platforms.bluestacks.instances import available_instances
from platforms.bluestacks.manager import choose_for_setup, open_instance_manager
from platforms.bluestacks.discovery import BlueStacksInstallation
from runtime_errors import VillageRuntimeError
from pathlib import Path
import tempfile

CONFIG = '''bst.instance.Pie64.display_name="Main"
bst.instance.Pie64.adb_port="5555"
bst.instance.Pie64.status.adb_port="5555"
bst.instance.Pie64_4.display_name="VLTest1"
bst.instance.Pie64_4.adb_port="5595"
bst.instance.Pie64_4.status.adb_port="5595"
'''

class ManagerTests(unittest.TestCase):
    def test_two_instances_require_explicit_choice(self):
        instances = available_instances(CONFIG)
        self.assertIsNone(choose_for_setup(instances))
        self.assertEqual(choose_for_setup(instances, preferred='Pie64_4')['adb_port'], 5595)

    def test_single_instance_may_be_suggested(self):
        self.assertEqual(choose_for_setup(available_instances(CONFIG)[:1])['id'], 'Pie64')

    def test_stale_selected_port_fails_closed(self):
        altered = CONFIG.replace('Pie64_4.status.adb_port="5595"','Pie64_4.status.adb_port="7001"')
        with self.assertRaises(VillageRuntimeError):
            choose_for_setup(available_instances(altered), preferred='Pie64_4')

    def test_gui_manager_is_not_vm_control_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed = BlueStacksInstallation(Path(tmp))
            gui = installed.gui_manager
            gui.touch()
            fake = Mock()
            open_instance_manager(installed, popen=fake)
            self.assertEqual(fake.call_args.args[0], [str(gui)])
            self.assertTrue(fake.call_args.kwargs.keys() >= {'creationflags'})

if __name__ == '__main__': unittest.main()
