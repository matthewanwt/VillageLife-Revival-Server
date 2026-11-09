import unittest,subprocess
from unittest.mock import patch
import setup_local
class RecipientSetupTests(unittest.TestCase):
 def test_arbitrary_display_names_unicode_and_duplicates_select_by_internal_id(self):
  text='\n'.join(['bst.instance.Pie64_1.display_name="My village café 村"','bst.instance.Pie64_1.adb_port="5565"','bst.instance.Pie64_2.display_name="My village café 村"','bst.instance.Pie64_2.adb_port="5575"','bst.instance.Nougat32.display_name="Other game"','bst.instance.Nougat32.adb_port="5555"'])
  items=setup_local.available_instances(text)
  self.assertEqual(len(items),2);self.assertEqual(setup_local.select_instance(items,'Pie64_2')['adb_port'],5575)
  with self.assertRaises(ValueError):setup_local.select_instance(items,'My village café 村')
  self.assertEqual(setup_local.select_instance(items[:1],'My village café 村')['id'],'Pie64_1')
 def test_setup_never_guesses_a_target_and_rejects_unsupported_or_invalid_ports(self):
  items=setup_local.available_instances('bst.instance.Pie64.display_name="Any name"\nbst.instance.Pie64.adb_port="5555"')
  for selection in [None,'Other game','../Pie64','Nougat32']:
   with self.subTest(selection=selection),self.assertRaises(ValueError):setup_local.select_instance(items,selection)
  with self.assertRaises(ValueError):setup_local.available_instances('bst.instance.Pie64.display_name="Any"\nbst.instance.Pie64.adb_port="70000"')
 def test_missing_android_package_is_expected_exit_one(self):
  with patch.object(setup_local.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','')):self.assertFalse(setup_local.package_installed('127.0.0.1:5555'))
 def test_existing_app_is_detected_without_reinstall(self):
  with patch.object(setup_local.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'package:/data/app/example/base.apk','')):self.assertTrue(setup_local.package_installed('127.0.0.1:5555'))
 def test_offline_adb_is_not_treated_as_empty_instance(self):
  with patch.object(setup_local.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','error: device offline')):
   with self.assertRaises(RuntimeError):setup_local.package_installed('127.0.0.1:5555')
if __name__=='__main__':unittest.main()
