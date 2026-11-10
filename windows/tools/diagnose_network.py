"""Read-only BlueStacks host/instance inventory to investigate Wi-Fi-on failures.

No VM setup, APK installation, Windows firewall modification, global ADB restart,
or changes to user settings. With --probe-guest, performs explicit bounded TCP
attempts from an already running Android instance for diagnostic purposes only.
A successful probe assessment is never an isolation certificate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys

from platforms.bluestacks.host_network import inspect_host
from platforms.bluestacks.instances import diagnostic_port_map
from platforms.bluestacks.discovery import discover_bluestacks
from platforms.bluestacks.adb import ADBClient
from platforms.bluestacks.net_assurance import verify_guest_network
from network_check import inspect_network
from runtime_errors import initialize_utf8

ROOT = Path(__file__).resolve().parents[1]


def _read_settings(root: Path) -> dict:
    path = root / 'play-settings.json'
    try:
        if path.stat().st_size > 500_000:
            return {}
        obj = json.loads(path.read_text(encoding='utf-8-sig'))
        return obj if isinstance(obj, dict) else {}
    except (OSError, ValueError):
        return {}


def _instance_list(config_text=None, programdata=None) -> tuple[list, str | None]:
    try:
        if config_text is None:
            base = Path(programdata or os.environ.get('ProgramData', r'C:\ProgramData'))
            path = base / 'BlueStacks_nxt' / 'bluestacks.conf'
            if path.stat().st_size > 8_000_000:
                return [], 'VL-BS-CONFIG-TOO-LARGE'
            config_text = path.read_text(encoding='utf-8-sig')
        return diagnostic_port_map(config_text), None
    except Exception as error:
        # This diagnostic must still report the host context when the BlueStacks
        # settings are damaged; avoid embedding filesystem paths or raw config.
        return [], str(getattr(error, 'code', 'VL-BS-INSTANCE-INVENTORY-FAILED'))


def _public_instance(row: dict) -> dict:
    return {
        'id': row['id'],
        'configured_adb_port': row['adb_port'],
        'live_status_adb_port': row.get('status_adb_port'),
        'display_name_present': bool(row.get('name')),
        'warnings': row.get('warnings', []),
    }


def build_report(*, root=ROOT, instance=None, probe_guest=False, host_report=None,
                 config_text=None, programdata=None, install=None) -> dict:
    """Injectable, no-side-effects report builder for Windows and synthetic tests."""
    root = Path(root)
    settings = _read_settings(root)
    rows, inventory_error = _instance_list(config_text=config_text, programdata=programdata)
    chosen = instance or settings.get('instance')
    by_id = {item['id']: item for item in rows}
    observed = host_report if host_report is not None else inspect_host()
    processes = observed.get('processes') or []
    running = {p.get('instance') for p in processes if p.get('name', '').lower() == 'hd-player.exe'}
    report = {
        'format': 'VillageLifeNetworkTopologyV1',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'selected_instance': chosen if isinstance(chosen, str) and re.fullmatch(r'Pie64(?:_\d+)?', chosen) else None,
        'instances': [dict(_public_instance(row), player_process_observed=row['id'] in running) for row in rows],
        'instance_inventory_error': inventory_error,
        'host': observed,
        'guest': {'status': 'not_tested', 'reason': 'Guest tests are opt-in and do not prove isolation.'},
        'conclusion': 'Evidence only. No network isolation policy has been identified or verified.',
        'modifies_windows_or_bluestacks': False,
    }
    if not chosen:
        report['next_action'] = 'Choose a dedicated Pie64 instance explicitly; the diagnostic will not guess between several instances.'
        return report
    if chosen not in by_id:
        report['next_action'] = 'Selected instance is not in BlueStacks configuration; inspect Multi-instance Manager and verify saved settings.'
        return report
    if chosen not in running:
        report['next_action'] = 'Start the selected instance before gathering guest evidence. No instance was launched automatically.'
    else:
        report['next_action'] = 'Review the observed process mapping and network topology. Guest probes require --probe-guest.'
    if not probe_guest:
        return report
    if by_id[chosen].get('warnings') or not by_id[chosen]['adb_port']:
        report['guest'] = {'status': 'not_tested', 'reason': 'ADB configuration is inconsistent; revalidate the instance before probing.'}
        return report
    if chosen not in running:
        report['guest'] = {'status': 'not_tested', 'reason': 'Selected HD-Player process was not observed; will not probe another VM.'}
        return report
    try:
        installation = install if install is not None else discover_bluestacks()
        selected = by_id[chosen]
        serial = '127.0.0.1:' + str(selected['adb_port'])
        client = ADBClient(installation.adb, serial)
        status = client.command('get-state', timeout=7)
        if status.code != 0 or status.output.strip() != 'device':
            report['guest'] = {'status': 'unavailable', 'reason': 'Selected instance ADB serial is not connected. Enable ADB for that instance and rerun. No global ADB restart was performed.'}
        else:
            config = inspect_network(chosen, programdata=programdata)
            checks = verify_guest_network(client, chosen, config=config)
            report['guest'] = {
                'status': 'probed',
                'probe_checks_all_blocked': bool(checks['isolated']),
                'vm_nat_configuration_matched': bool(config.get('verified')),
                'checks': [{'name': c['name'], 'android_exit_code': c.get('probe_android_exit_code'),
                            'transport_exit_code': c.get('probe_transport_exit_code'),
                            'blocked': bool(c.get('isolated'))} for c in checks['checks']],
                'isolation_policy_verified': False,
                'warning': 'External TCP probe failures are NOT proof of VM isolation, including UDP/DNS/IPv6.',
            }
    except Exception as ex:
        report['guest'] = {'status': 'unavailable', 'reason': 'Guest diagnostic failed.', 'code': getattr(ex, 'code', type(ex).__name__)}
    return report


def main():
    initialize_utf8()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--instance', help='Exact BlueStacks ID, e.g. Pie64 or Pie64_4')
    parser.add_argument('--probe-guest', action='store_true',
                        help='Explicit opt-in: run bounded external TCP probes from selected running guest (no configuration changes).')
    parser.add_argument('--output', type=Path, help='Alternative report location for local investigations')
    args = parser.parse_args()
    report = build_report(instance=args.instance, probe_guest=args.probe_guest)
    target = args.output or (ROOT / 'network-topology-report.json')
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Network diagnostic: ' + str(target), flush=True)
    print('BlueStacks instances: ' + ', '.join(
        f"{row['id']} [configured {row['configured_adb_port']}, live {row['live_status_adb_port'] or 'unknown'}]"
        for row in report['instances']) or '(unavailable)', flush=True)
    print('Selected: ' + str(report['selected_instance'] or '(none)'), flush=True)
    print('Host inventory: ' + str(report['host'].get('status')), flush=True)
    print('Guest tests: ' + str(report['guest']['status']), flush=True)
    print(report['next_action'] if 'next_action' in report else report['conclusion'], flush=True)
    print('No firewall rules, game files, BlueStacks settings, or player saves were changed.', flush=True)
    print('This report is evidence for further investigation, not proof of Wi-Fi isolation.', flush=True)


if __name__ == '__main__':
    main()
