"""Fail-closed external connectivity assessment for Wi-Fi-on field testing.

This module does NOT change Windows or Android firewalls and never equates
loopback-only NAT configuration with a complete outbound-network block.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence
from network_check import assess_adb_probe, inspect_network, EXTERNAL_PROBE_COMMAND

# The canonical check remains identical to the known original.
# The secondary probes make accidental accidental egress more visible; a finite
# sample is still NOT proof that all destinations are blocked.
EXTERNAL_PROBES = (
    ("primary_https", EXTERNAL_PROBE_COMMAND),
    ("secondary_https", 'toybox nc -w 3 9.9.9.9 443 </dev/null; vl_rc=$?; printf "\\n__VL_NETWORK_EXIT__=%s\\n" "$vl_rc"'),
    ("external_dns", 'toybox nc -w 3 8.8.8.8 53 </dev/null; vl_rc=$?; printf "\\n__VL_NETWORK_EXIT__=%s\\n" "$vl_rc"'),
)


def verify_guest_network(adb_client, instance, *, config=None):
    config = inspect_network(instance) if config is None else config
    checks = []
    for label, command in EXTERNAL_PROBES:
        result = adb_client.command("shell", command, timeout=12)
        evaluated = assess_adb_probe(config, result.code, result.output)
        checks.append({"name": label, **evaluated, "output_excerpt": result.output[:350]})
    isolated = bool(config.get("verified")) and all(x["isolated"] for x in checks)
    failed = [x["name"] for x in checks if not x["isolated"]]
    return {
        "isolated": isolated,
        "configuration": config,
        "checks": checks,
        "reason": "Guest external probes were blocked and VM NAT configuration matched; further firewall isolation verification remains necessary." if isolated else "External network access was possible or could not be verified (" + ", ".join(failed) + ").",
        "security_limit": "Probe results cannot guarantee every possible external destination is blocked.",
    }
