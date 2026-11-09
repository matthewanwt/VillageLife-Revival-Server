import unittest
from hosted_connection import ssh_command
class HostedConnectionTests(unittest.TestCase):
 def test_forward_is_loopback_only_with_strict_keys_and_keepalive(self):
  command=ssh_command({'server_host':'example.invalid','server_user':'tester'},'ssh')
  self.assertIn('127.0.0.1:80:127.0.0.1:8080',command)
  self.assertIn('StrictHostKeyChecking=yes',command);self.assertIn('BatchMode=yes',command)
  self.assertEqual(command[-1],'tester@example.invalid')
 def test_options_and_invalid_ports_cannot_be_injected(self):
  for update in [{'server_host':'-oProxyCommand=bad'},{'server_user':'user@elsewhere'},{'server_port':True},{'server_ssh_port':0}]:
   with self.assertRaises(ValueError):ssh_command({'server_host':'example.invalid','server_user':'tester',**update},'ssh')
if __name__=='__main__':unittest.main()
