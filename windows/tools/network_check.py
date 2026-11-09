"""Verify the dedicated VM isolation without relying on one English error string."""
from pathlib import Path
import os,re
import xml.etree.ElementTree as ET

# Some bundled ADB builds report transport success even when Android exits 1.
# Read the Android shell result explicitly rather than trusting adb.exe's exit.
PROBE_MARKER='__VL_NETWORK_EXIT__='
EXTERNAL_PROBE_COMMAND='toybox nc -w 3 1.1.1.1 443 </dev/null; vl_network_rc=$?; printf "\\n__VL_NETWORK_EXIT__=%s\\n" "$vl_network_rc"'

def assess_adb_probe(config,transport_code,output):
 matches=re.findall(r'^'+PROBE_MARKER+r'(\d+)\s*$',output,re.MULTILINE)
 remote_code=int(matches[0]) if len(matches)==1 and 0<=int(matches[0])<=255 else None
 details={'probe_transport_exit_code':transport_code,'probe_android_exit_code':remote_code}
 if transport_code!=0 or remote_code is None:
  return {**details,'isolated':False,'reason':'Android network test did not return a valid result; check the selected instance and its ADB connection'}
 clean=re.sub(r'^'+PROBE_MARKER+r'\d+\s*$','',output,flags=re.MULTILINE)
 if remote_code not in {0,1}:
  return {**details,'isolated':False,'reason':'Android network test could not run normally; check the selected instance and its ADB connection'}
 return {**details,**assess_probe(config,remote_code,clean)}

def inspect_network(instance,programdata=None):
 if not isinstance(instance,str) or not re.fullmatch(r'Pie64(?:_\d+)?',instance):return {'verified':False,'reason':'Unexpected dedicated instance name'}
 base=Path(programdata or os.environ.get('ProgramData',r'C:\ProgramData'))
 path=base/'BlueStacks_nxt'/'Engine'/instance/(instance+'.bstk')
 result={'verified':False,'config_file':str(path)}
 try:
  if path.stat().st_size>4*1024*1024:raise ValueError('Configuration file is unexpectedly large')
  root=ET.fromstring(path.read_bytes())
  tag=lambda e:e.tag.rsplit('}',1)[-1]
  hardware=next(e for e in root.iter() if tag(e)=='Hardware')
  network=next(e for e in hardware if tag(e)=='Network')
  adapters=[e for e in network if tag(e)=='Adapter' and e.get('enabled','false').lower()=='true']
  if len(adapters)!=1 or adapters[0].get('slot')!='0':raise ValueError('Dedicated instance must have only its NAT adapter enabled')
  modes=[e for e in adapters[0] if tag(e)!='DisabledModes']
  nat=next((e for e in modes if tag(e)=='NAT'),None)
  if nat is None or len(modes)!=1:raise ValueError('Dedicated instance is not using the expected NAT mode')
  result.update(nat_bind_ip=nat.get('hostip',''),localhost_reachable=nat.get('localhost-reachable','false').lower()=='true')
  if result['nat_bind_ip']!='127.0.0.1' or not result['localhost_reachable']:raise ValueError('Local-only NAT settings were not applied; close this instance and run Set Up Game again')
  result.update(verified=True,reason='Dedicated VM configuration uses loopback-only NAT')
 except (OSError,ET.ParseError,ValueError,StopIteration) as error:result['reason']=str(error) or 'Dedicated VM network configuration could not be read'
 return result

def assess_probe(config,code,output):
 if code==0:return {'isolated':False,'reason':'Android can connect to the external probe address. For disconnected local play, turn off this PC\'s Wi-Fi and unplug Ethernet, close the dedicated instance, then retry setup. Keep this PC disconnected while playing. The configured NAT restriction alone is not sufficient on this system'}
 if not config.get('verified'):return {'isolated':False,'reason':config.get('reason','Dedicated instance configuration could not be verified')}
 text=output.lower()
 if code in {126,127} or any(s in text for s in ['not found','unknown option','unknown command','permission denied','no such device','device offline','no devices','cannot connect to daemon','more than one device','error: device']):return {'isolated':False,'reason':'Android network probe could not run; check the dedicated instance and its ADB connection'}
 return {'isolated':True,'reason':'Loopback-only VM NAT verified and external TCP connection did not succeed'}
