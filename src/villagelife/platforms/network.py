"""Read-only, minimal Windows/BlueStacks topology inventory.

No firewall, NAT, or VM settings are changed. This is NOT proof of isolation.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import http.client
import json
import os
from villagelife.platforms import bluestacks


def _host_backend_ready(port: int) -> bool:
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        connection.request('GET', '/health')
        response = connection.getresponse()
        if response.status != 200:
            return False
        payload = json.loads(response.read(4096))
        return isinstance(payload, dict) and payload.get('service') == 'villagelife-revival-server'
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def report(binding_path: Path, *, conf: Path | None = None, guest_checks: bool = False,
           local_port: int | None = None) -> dict:
    output = {'format': 'VillageLifeNetworkEvidenceV1',
              'timestamp_utc': datetime.now(timezone.utc).isoformat(),
              'host_os': os.name, 'policy_verified': False, 'guest_egress_verified': False,
              'guest_to_local_verified': False, 'guest_to_local_check': 'not_tested',
              'changes_applied': False,
              'warning': 'Host network inventory cannot establish guest isolation or Wi-Fi-on safety.'}
    try:
        rows = bluestacks.list_instances(config=conf)
        output['configured_instances'] = [{'id': r.id, 'port_config_matches_live': r.live_adb_port in (None,r.adb_port)} for r in rows]
        if binding_path.is_file():
            selected = json.loads(binding_path.read_text(encoding='utf-8')).get('id')
            output['selected_instance'] = selected
        else:
            output['selected_instance'] = None
        if guest_checks:
            from villagelife.platforms.original_client import guest_network_evidence
            try:
                output['guest_egress_checks'] = guest_network_evidence(binding_path)
                output['guest_egress_verified'] = False
                output['guest_check_note'] = ('Individual probes are observations only; they cannot establish '
                                              'a complete firewall/NAT policy or prove UDP isolation.')
            except bluestacks.InstanceError as exc:
                output['guest_check_error_code'] = exc.code
    except (OSError, ValueError, bluestacks.InstanceError):
        output['inventory_error_code'] = 'VL-NET-CONFIG-UNAVAILABLE'
    if local_port is not None:
        if not _host_backend_ready(local_port):
            output['guest_to_local_check'] = 'backend_unavailable'
            return output
        from villagelife.platforms.original_client import probe_local_server
        try:
            probe_local_server(binding_path, local_port)
        except bluestacks.InstanceError as exc:
            output['guest_to_local_check'] = 'failed'
            output['guest_to_local_error_code'] = exc.code
        else:
            output['guest_to_local_check'] = 'reachable'
            output['guest_to_local_verified'] = True
    return output
