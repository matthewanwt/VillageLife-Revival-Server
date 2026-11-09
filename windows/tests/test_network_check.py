import tempfile,unittest
from pathlib import Path
import network_check as network
class NetworkCheckTests(unittest.TestCase):
 def test_android_failure_is_read_even_when_legacy_adb_reports_success(self):
  result=network.assess_adb_probe({'verified':True},0,'Network unreachable\r\n__VL_NETWORK_EXIT__=1\r\n')
  self.assertTrue(result['isolated']);self.assertEqual(result['probe_android_exit_code'],1)
 def test_android_external_success_still_blocks_and_unknown_results_fail_closed(self):
  self.assertFalse(network.assess_adb_probe({'verified':True},0,'\n__VL_NETWORK_EXIT__=0\n')['isolated'])
  for code,output in [(0,''),(1,'__VL_NETWORK_EXIT__=1'),(0,'__VL_NETWORK_EXIT__=1\n__VL_NETWORK_EXIT__=0'),(0,'__VL_NETWORK_EXIT__=127'),(0,'Permission denied\n__VL_NETWORK_EXIT__=1'),(0,'__VL_NETWORK_EXIT__=999')]:
   with self.subTest(code=code,output=output):self.assertFalse(network.assess_adb_probe({'verified':True},code,output)['isolated'])
  self.assertFalse(network.assess_adb_probe({'verified':False},0,'__VL_NETWORK_EXIT__=1')['isolated'])
 def config(self,xml):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);base=Path(self.tmp.name)
  path=base/'BlueStacks_nxt/Engine/Pie64_1/Pie64_1.bstk';path.parent.mkdir(parents=True);path.write_text(xml,encoding='utf-8')
  return network.inspect_network('Pie64_1',base)
 def test_loopback_nat_is_verified_despite_disabled_other_modes(self):
  result=self.config('<VirtualBox xmlns="urn:test"><Machine><Hardware><Network><Adapter slot="0" enabled="true"><DisabledModes><NATNetwork/></DisabledModes><NAT hostip="127.0.0.1" localhost-reachable="true"/></Adapter><Adapter slot="1"><NAT/></Adapter></Network></Hardware></Machine></VirtualBox>');self.assertTrue(result['verified'])
 def test_public_nat_extra_enabled_adapter_and_malformed_xml_fail_closed(self):
  for inner in ['<Adapter slot="0" enabled="true"><NAT hostip="0.0.0.0" localhost-reachable="true"/></Adapter>','<Adapter slot="0" enabled="true"><NAT hostip="127.0.0.1" localhost-reachable="true"/></Adapter><Adapter slot="1" enabled="true"><NAT/></Adapter>','<Adapter slot="0" enabled="true"><NATNetwork/></Adapter>']:
   self.assertFalse(self.config('<Machine><Hardware><Network>'+inner+'</Network></Hardware></Machine>')['verified'])
  self.assertFalse(self.config('broken')['verified'])
 def test_blocked_probe_wording_does_not_need_exact_english_message(self):
  for output in ['Network is unreachable','No route to host','Cannot assign requested address','Connection timed out','', 'network wording from another version']:
   self.assertTrue(network.assess_probe({'verified':True},1,output)['isolated'])
 def test_successful_external_connection_never_passes(self):
  self.assertFalse(network.assess_probe({'verified':True},0,'')['isolated'])
 def test_tool_or_device_errors_never_count_as_isolation(self):
  for code,output in [(127,'toybox nc: not found'),(1,'error: device offline'),(1,'Permission denied')]:self.assertFalse(network.assess_probe({'verified':True},code,output)['isolated'])
 def test_unverified_config_cannot_pass_on_probe_failure(self):
  self.assertFalse(network.assess_probe({'verified':False,'reason':'setup missing'},1,'Network is unreachable')['isolated'])
 def test_instance_path_cannot_escape_engine_folder(self):
  self.assertFalse(network.inspect_network('../Other')['verified'])
if __name__=='__main__':unittest.main()
