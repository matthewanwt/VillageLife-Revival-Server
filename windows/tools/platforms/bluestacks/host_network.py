"""Non-invasive Windows network/process inventory for BlueStacks Wi-Fi debugging.

This is *evidence gathering*, NOT a firewall or an isolation certification.
The PowerShell query does not change processes, network adapters, or VM settings.
We never export command lines, user directories, raw addresses, MACs, or tokens.
"""
from __future__ import annotations

from collections import Counter
import ipaddress
import json
import os
import subprocess


# PowerShell 5.1 compatible. Collect narrowly scoped facts; never emit raw
# command lines or raw connection addresses to the support report.
_WINDOWS_QUERY = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$vlResult = [ordered]@{
  processes = @()
  connections = @()
  listeners80 = @()
  adapters = @()
  hyperv_firewall_cmdlet = [bool](Get-Command Get-NetFirewallHyperVVMSetting -ErrorAction SilentlyContinue)
  net_tcp_cmdlet = [bool](Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)
  errors = @()
}
try {
  $vlProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^(HD-|Bstk|BlueStacks|vmwp)' })
  $vlResult.processes = @($vlProcesses | ForEach-Object {
    $vlInstance = $null
    if ($_.Name -ieq 'HD-Player.exe' -and $_.CommandLine -match '(?i)--instance\s+(?:"([A-Za-z0-9_]+)"|([A-Za-z0-9_]+))') {
      $vlInstance = if ($Matches[1]) { $Matches[1] } else { $Matches[2] }
    }
    [ordered]@{ name = $_.Name; pid = [int]$_.ProcessId; instance = $vlInstance }
  })
} catch { $vlResult.errors += 'process_inventory_unavailable' }
try {
  $vlPids = @($vlResult.processes | ForEach-Object { $_.pid })
  $vlResult.connections = @(Get-NetTCPConnection -ErrorAction Stop | Where-Object {
    $vlPids -contains $_.OwningProcess
  } | Select-Object -First 250 | ForEach-Object {
    [ordered]@{ pid = [int]$_.OwningProcess; remote = [string]$_.RemoteAddress; remote_port = [int]$_.RemotePort; state = [string]$_.State }
  })
  $vlResult.listeners80 = @(Get-NetTCPConnection -LocalPort 80 -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
    [ordered]@{ pid = [int]$_.OwningProcess }
  })
} catch { $vlResult.errors += 'tcp_inventory_unavailable' }
try {
  $vlResult.adapters = @(Get-NetAdapter -ErrorAction Stop | ForEach-Object {
    [ordered]@{
      status = [string]$_.Status
      description = [string]$_.InterfaceDescription
      medium = [string]$_.NdisPhysicalMedium
    }
  })
} catch { $vlResult.errors += 'adapter_inventory_unavailable' }
$vlResult | ConvertTo-Json -Depth 6 -Compress
'''


def address_class(address: str) -> str:
    """Privacy-preserving TCP endpoint classification; do not emit IP literals."""
    try:
        ip = ipaddress.ip_address(str(address).split('%', 1)[0])
    except ValueError:
        return 'unknown'
    if ip.is_unspecified:
        return 'unspecified'
    if ip.is_loopback:
        return 'loopback'
    if ip.is_link_local:
        return 'link_local'
    if ip.is_multicast:
        return 'multicast'
    if ip.is_private:
        return 'private_or_special'
    if ip.is_global:
        return 'public'
    return 'other_special'


def _category(description: str, medium: str) -> str:
    val = (description + ' ' + medium).lower()
    if any(s in val for s in ('bluestacks', 'bstk', 'hyper-v', 'vethernet', 'virtualbox', 'virtual ethernet')):
        return 'virtual_or_emulator'
    if any(s in val for s in ('802.11', 'wi-fi', 'wifi', 'wireless')):
        return 'wireless'
    if any(s in val for s in ('ethernet', '802.3', 'lan')):
        return 'wired_or_ethernet'
    return 'other_or_unknown'


def summarise(raw: dict) -> dict:
    """Aggressively minimise Windows process/network inventory for support."""
    if not isinstance(raw, dict):
        return {'status': 'invalid', 'errors': ['invalid_response']}
    processes = raw.get('processes') or []
    if not isinstance(processes, list):
        processes = [processes]
    safe_processes = []
    pids = set()
    for entry in processes[:150]:
        try:
            name = str(entry.get('name', ''))
            if not (name.lower().startswith(('hd-', 'bstk', 'bluestacks')) or name.lower() == 'vmwp.exe'):
                continue
            pid = int(entry['pid'])
            if pid < 0:
                continue
            instance = str(entry.get('instance') or '')
            if not instance.startswith(('Pie64', 'Nougat', 'Rvc64', 'Android')) or len(instance) > 40:
                instance = ''
            safe_processes.append({'name': name[:70], 'pid': pid, 'instance': instance or None})
            pids.add(pid)
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    tcp_counts = Counter()
    tcp_states = Counter()
    for connection in (raw.get('connections') or [])[:250]:
        try:
            if int(connection.get('pid', -1)) not in pids:
                continue
            category = address_class(connection.get('remote', ''))
            tcp_counts[category] += 1
            tcp_states[str(connection.get('state', 'unknown'))[:30]] += 1
        except (ValueError, TypeError, AttributeError):
            continue
    adapters = Counter()
    for a in (raw.get('adapters') or [])[:80]:
        if isinstance(a, dict):
            adapters[(_category(str(a.get('description', '')), str(a.get('medium', ''))), str(a.get('status', '?'))[:24])] += 1
    listener_count = len(raw.get('listeners80') or [])
    return {
        'status': 'collected',
        'processes': safe_processes,
        'observed_tcp_remote_classes': dict(tcp_counts),
        'observed_tcp_states': dict(tcp_states),
        'adapter_categories': [{'type': t, 'status': s, 'count': n} for (t, s), n in sorted(adapters.items())],
        'port80_listener_count': listener_count,
        'hyperv_firewall_cmdlet_present': bool(raw.get('hyperv_firewall_cmdlet')),
        'net_tcp_cmdlet_present': bool(raw.get('net_tcp_cmdlet')),
        'collection_errors': [str(x)[:60] for x in (raw.get('errors') or [])[:12]],
        'limitations': [
            'Only observed TCP sessions from known BlueStacks-related process names were counted; this does not reveal all VM traffic.',
            'Adapter and cmdlet availability do not prove an effective isolation policy.',
            'No raw network addresses, commands, interface names or process paths were retained.',
        ],
    }


def inspect_host(*, runner=None, platform=None) -> dict:
    """Query Windows without requiring admin rights or changing configuration."""
    if platform is None:
        platform = os.name
    if platform != 'nt':
        return {'status': 'unavailable', 'reason': 'Windows-only; run on the BlueStacks host.'}
    if runner is None:
        runner = subprocess.run
    try:
        response = runner(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', _WINDOWS_QUERY],
            capture_output=True, timeout=25, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if response.returncode:
            return {'status': 'unavailable', 'reason': 'Windows network inventory query failed.', 'exit_code': response.returncode}
        return summarise(json.loads(response.stdout.decode('utf-8-sig', errors='replace')))
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError, ValueError) as ex:
        return {'status': 'unavailable', 'reason': 'Windows network inventory query could not complete.', 'exception': type(ex).__name__}
