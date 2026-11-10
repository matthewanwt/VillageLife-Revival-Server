"""Private original-client preparation and explicit BlueStacks installation.

Nothing here downloads, redistributes, or alters the supplied XAPK.  It only
creates a separately signed local copy under the user's application-data area.
"""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess
import zipfile

from villagelife.platforms import bluestacks

PACKAGE = 'com.playdemic.villagelife.android'


def _adb_detail(result: subprocess.CompletedProcess[bytes]) -> str:
    """Return a bounded Android-tool message suitable for the local launcher."""
    raw = (result.stderr + b' ' + result.stdout).decode('utf-8', 'replace')
    return ' '.join(raw.split())[:400]


def _adb_install_succeeded(result: subprocess.CompletedProcess[bytes]) -> bool:
    """ADB wrappers vary in stream and exit-code behavior; trust PM's reply.

    HD-Adb can report a successful Package Manager install on stderr or with
    a nonzero wrapper exit code. The subsequent `pm path` check verifies that
    Android actually registered the package before Setup is marked complete.
    An explicit Failure response always wins over a stray Success token.
    """
    detail = _adb_detail(result).casefold()
    return 'failure' not in detail and 'success' in detail


def _run(args: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise bluestacks.InstanceError('VL-ADB-UNAVAILABLE', 'ADB command failed or timed out') from exc


def _adb(binding: Path, args: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess[bytes]:
    root = bluestacks.installation()
    selected = bluestacks.verify_binding(binding, bluestacks.list_instances(), root)
    serial = f'127.0.0.1:{selected.adb_port}'
    connected = _run([str(root / 'HD-Adb.exe'), 'connect', serial], timeout=12)
    if connected.returncode:
        raise bluestacks.InstanceError('VL-ADB-NOT-READY', 'Selected instance is not ready for ADB')
    return _run([str(root / 'HD-Adb.exe'), '-s', serial, *args], timeout=timeout)


def existing_installation(binding: Path) -> bool:
    """Return whether the exact selected guest already has Village Life."""
    result = _adb(binding, ['shell', 'pm', 'path', PACKAGE])
    return result.returncode == 0 and b'package:' in result.stdout


def install_prepared(binding: Path, apk: Path, obb: Path, *, replace: bool = False) -> None:
    """Install only a prepared local APK and matching OBB into the bound VM."""
    apk = apk.resolve(strict=True)
    obb = obb.resolve(strict=True)
    if existing_installation(binding) and not replace:
        raise bluestacks.InstanceError('VL-GAME-EXISTS', 'Village Life is already installed. Confirm replacement before installing the prepared client')
    install = _adb(binding, ['install', *( ['-r'] if replace else [] ), str(apk)], timeout=180)
    # Android intentionally refuses an in-place update if the selected VM has
    # the original Playdemic-signed package.  The launcher obtains explicit
    # replacement approval before passing --replace.  Retain data whenever a
    # prior prepared client has the same private certificate; uninstall only
    # for the specific certificate-conflict result.
    detail = _adb_detail(install)
    if not _adb_install_succeeded(install) and replace and 'INSTALL_FAILED_UPDATE_INCOMPATIBLE' in detail:
        removed = _adb(binding, ['uninstall', PACKAGE], timeout=90)
        if not _adb_install_succeeded(removed):
            raise bluestacks.InstanceError('VL-GAME-REMOVE-FAILED',
                                           'Android could not remove the approved existing Village Life app'
                                           + (': ' + _adb_detail(removed) if _adb_detail(removed) else ''))
        install = _adb(binding, ['install', str(apk)], timeout=180)
        detail = _adb_detail(install)
    if not _adb_install_succeeded(install):
        raise bluestacks.InstanceError('VL-GAME-INSTALL-FAILED', 'Android rejected the locally prepared APK'
                                       + (': ' + detail if detail else f' (ADB exit code {install.returncode})'))
    remote_dir = f'/sdcard/Android/obb/{PACKAGE}'
    mkdir = _adb(binding, ['shell', 'mkdir', '-p', remote_dir])
    pushed = _adb(binding, ['push', str(obb), f'{remote_dir}/{obb.name}'], timeout=300)
    if mkdir.returncode or pushed.returncode:
        raise bluestacks.InstanceError('VL-OBB-INSTALL-FAILED', 'Could not transfer the required OBB to the selected instance')
    installed = _adb(binding, ['shell', 'pm', 'path', PACKAGE])
    if installed.returncode or b'package:' not in installed.stdout:
        raise bluestacks.InstanceError('VL-GAME-VERIFY-FAILED', 'APK installation could not be verified')


def probe_local_server(binding: Path, port: int = 80) -> None:
    """Prove guest-to-host HTTP only; deliberately does not claim isolation."""
    if not 1 <= port <= 65535:
        raise ValueError('Invalid server port')
    # toybox is present on supported BlueStacks Android images.  A nonzero
    # result is surfaced as an actionable connectivity failure, never ignored.
    command = f'toybox wget -q -T 6 -O /dev/null http://10.0.2.2:{port}/health'
    result = _adb(binding, ['shell', 'sh', '-c', command], timeout=15)
    if result.returncode:
        raise bluestacks.InstanceError('VL-GUEST-BACKEND-UNREACHABLE', 'The selected Android guest cannot reach the local backend')


def guest_network_evidence(binding: Path) -> dict[str, str]:
    """Run bounded, read-only guest egress checks for diagnostics.

    These checks neither alter BlueStacks networking nor prove an isolation
    policy.  They make a failed/working external path visible instead of
    mistaking route configuration for a security boundary.
    """
    def run(command: str) -> subprocess.CompletedProcess[bytes]:
        return _adb(binding, ['shell', 'sh', '-c', command], timeout=15)
    def available(command: str) -> bool:
        return run(f'command -v {command} >/dev/null 2>&1').returncode == 0
    def result(command: str, *, required: str | None = None) -> str:
        response = run(command)
        if response.returncode:
            return 'not_reachable'
        if required is not None and required.encode() not in response.stdout:
            return 'not_reachable'
        return 'reachable'

    output: dict[str, str] = {}
    output['adb_shell'] = 'available'
    output['ipv4_route_present'] = (result('ip -4 route show', required='default')
                                    if available('ip') else 'not_measurable (ip unavailable)')
    output['dns_lookup_reachable'] = (result('getent hosts example.com')
                                      if available('getent') else 'not_measurable (getent unavailable)')
    nc = run('toybox --list 2>/dev/null | grep -qx nc').returncode == 0
    if not nc:
        output['ipv4_tcp_443_reachable'] = 'not_measurable (toybox nc unavailable)'
        output['ipv6_tcp_443_reachable'] = 'not_measurable (toybox nc unavailable)'
        output['udp_probe_utility_available'] = 'not_measurable (toybox nc unavailable)'
    else:
        output['ipv4_tcp_443_reachable'] = result('toybox nc -z -w 5 1.1.1.1 443')
        output['ipv6_tcp_443_reachable'] = result('toybox nc -6 -z -w 5 2606:4700:4700::1111 443')
        output['udp_probe_utility_available'] = 'available'
    return output


def launch(binding: Path) -> None:
    result = _adb(binding, ['shell', 'monkey', '-p', PACKAGE, '1'], timeout=30)
    if result.returncode or b'Events injected: 1' not in result.stdout:
        raise bluestacks.InstanceError('VL-GAME-LAUNCH-FAILED', 'Android could not start Village Life')

