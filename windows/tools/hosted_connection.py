"""Private invitation-only hosting transport. Never exposes the legacy HTTP service."""
import re,shutil

def ssh_command(settings,ssh=None):
 host=settings.get('server_host','');user=settings.get('server_user','')
 if not isinstance(host,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',host):raise ValueError('A server hostname or IPv4 address is required')
 if not isinstance(user,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,63}',user):raise ValueError('A valid server SSH user is required')
 port=settings.get('server_ssh_port',22);target=settings.get('server_port',8080)
 for value in [port,target]:
  if isinstance(value,bool) or not isinstance(value,int) or not 1<=value<=65535:raise ValueError('Invalid hosted port')
 executable=ssh or shutil.which('ssh')
 if not executable:raise ValueError('Windows OpenSSH client is required for private hosted play')
 return [executable,'-N','-T','-o','ExitOnForwardFailure=yes','-o','StrictHostKeyChecking=yes','-o','BatchMode=yes','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-p',str(port),'-L',f'127.0.0.1:80:127.0.0.1:{target}',user+'@'+host]
