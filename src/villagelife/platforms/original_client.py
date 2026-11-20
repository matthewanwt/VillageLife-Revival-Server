"""Private original-client preparation and explicit BlueStacks installation.

Nothing here downloads, redistributes, or alters the supplied XAPK.  It only
creates a separately signed local copy under the user's application-data area.
"""
from __future__ import annotations

from pathlib import Path
from hashlib import file_digest
import os
import shlex
import shutil
import subprocess
import zipfile

from villagelife.platforms import bluestacks

PACKAGE = 'com.playdemic.villagelife.android'
OBB_NAME = f'main.241.{PACKAGE}.obb'
OBB_DIR = f'/sdcard/Android/obb/{PACKAGE}'


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
    hidden = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        return subprocess.run(args, capture_output=True, timeout=timeout, check=False,
                              creationflags=hidden)
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


def prepared_apk_installed(binding: Path, apk: Path) -> bool:
    result = _adb(binding, ['shell', 'pm', 'path', PACKAGE], timeout=15)
    lines = result.stdout.decode('utf-8', 'replace').splitlines()
    paths = [line.removeprefix('package:') for line in lines if line.startswith('package:')]
    if result.returncode or len(paths) != 1:
        return False
    result = _adb(binding, ['shell', f'sha256sum {shlex.quote(paths[0])}'], timeout=30)
    with apk.open('rb') as source:
        expected = file_digest(source, 'sha256').hexdigest().encode('ascii')
    return result.returncode == 0 and result.stdout.split()[:1] == [expected]


def _obb_matches(binding: Path, remote: str, size: int) -> bool:
    result = _adb(binding, ['shell', f'stat -c %s {remote}'], timeout=15)
    return result.returncode == 0 and result.stdout.strip() == str(size).encode('ascii')


def _obb_digest_matches(binding: Path, remote: str, obb: Path) -> bool:
    result = _adb(binding, ['shell', f'sha256sum {shlex.quote(remote)}'], timeout=180)
    with obb.open('rb') as source:
        expected = file_digest(source, 'sha256').hexdigest().encode('ascii')
    return result.returncode == 0 and result.stdout.split()[:1] == [expected]


def prepared_installation_ready(binding: Path, obb: Path | None = None, *, verify_hash=False) -> bool:
    if not existing_installation(binding):
        return False
    size = obb.stat().st_size if obb is not None else 452933712
    return (size > 0 and _obb_matches(binding, f'{OBB_DIR}/{OBB_NAME}', size)
            and (not verify_hash or (obb is not None and _obb_digest_matches(binding, f'{OBB_DIR}/{OBB_NAME}', obb))))


def install_prepared(binding: Path, apk: Path, obb: Path, *, replace: bool = False) -> None:
    """Install only a prepared local APK and matching OBB into the bound VM."""
    apk = apk.resolve(strict=True)
    obb = obb.resolve(strict=True)
    if obb.name != OBB_NAME or obb.stat().st_size == 0:
        raise ValueError('The prepared expansion file is invalid')
    if prepared_apk_installed(binding, apk):
        _install_obb(binding, obb)
        return
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
    if not existing_installation(binding):
        raise bluestacks.InstanceError('VL-GAME-VERIFY-FAILED', 'APK installation could not be verified')
    _install_obb(binding, obb)


def repair_prepared_obb(binding: Path, apk: Path, obb: Path) -> None:
    obb = obb.resolve(strict=True)
    if obb.name != OBB_NAME or obb.stat().st_size == 0:
        raise ValueError('The prepared expansion file is invalid')
    if not prepared_apk_installed(binding, apk):
        raise bluestacks.InstanceError('VL-GAME-VERIFY-FAILED', 'The selected instance does not have the matching prepared APK')
    _install_obb(binding, obb)


def _install_obb(binding: Path, obb: Path) -> None:
    size = obb.stat().st_size
    destination = f'{OBB_DIR}/{OBB_NAME}'
    if _obb_matches(binding, destination, size) and _obb_digest_matches(binding, destination, obb):
        return
    pending = destination + '.vl-part'

    def transfer_step(label: str, args: list[str], *, timeout: int = 30) -> None:
        result = _adb(binding, args, timeout=timeout)
        if result.returncode:
            raw = (result.stderr + b'\n' + result.stdout).decode('utf-8', 'replace')
            lines = [line.strip() for line in raw.splitlines()
                     if line.strip() and not line.lstrip().startswith('[')]
            detail = ' '.join(lines[-3:])[-400:]
            raise bluestacks.InstanceError('VL-OBB-INSTALL-FAILED',
                f'{label}: {detail or f"ADB exit code {result.returncode}"}. Click Play to retry.')

    if not _obb_matches(binding, pending, size) or not _obb_digest_matches(binding, pending, obb):
        transfer_step('Create expansion folder', ['shell', 'mkdir', '-p', OBB_DIR])
        transfer_step('Transfer expansion file', ['push', str(obb), pending], timeout=300)
        if not _obb_matches(binding, pending, size) or not _obb_digest_matches(binding, pending, obb):
            raise bluestacks.InstanceError('VL-OBB-INSTALL-FAILED', 'The transferred expansion is incomplete. Click Play to retry.')
    transfer_step('Activate expansion file', ['shell', 'mv', '-f', pending, destination])
    if not _obb_matches(binding, destination, size) or not _obb_digest_matches(binding, destination, obb):
        raise bluestacks.InstanceError('VL-OBB-INSTALL-FAILED', 'Android did not confirm the final expansion file.')


def probe_local_server(binding: Path, port: int = 80) -> None:
    """Prove guest-to-host HTTP only; deliberately does not claim isolation."""
    if not 1 <= port <= 65535:
        raise ValueError('Invalid server port')
    url = f'http://10.0.2.2:{port}/health'
    # Pie64 can ship BusyBox wget on PATH without a Toybox wget applet.
    command = (f'if command -v wget >/dev/null 2>&1; then wget -T 6 -O - {url}; '
               f'else toybox wget -T 6 -O - {url}; fi')
    result = _adb(binding, ['shell', command], timeout=15)
    if b'villagelife-revival-server' in result.stdout:
        return
    detail = _adb_detail(result)
    if 'unknown command wget' in detail.lower() or 'wget: not found' in detail.lower():
        raise bluestacks.InstanceError('VL-GUEST-PROBE-UNAVAILABLE', 'This BlueStacks instance has no supported HTTP check')
    raise bluestacks.InstanceError('VL-GUEST-BACKEND-UNREACHABLE',
        'BlueStacks could not verify the local server' + (f': {detail}' if detail else ''))


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


def game_status(binding: Path) -> str:
    """Distinguish an exited Android activity from an unsuccessful query."""
    fast = _adb(binding, ['shell', 'pidof', PACKAGE], timeout=5)
    if fast.returncode == 0 and fast.stdout.strip().replace(b' ', b'').isdigit():
        return 'running'
    if fast.returncode == 1 and not fast.stdout.strip():
        return 'closed'
    result = _adb(binding, ['shell', 'dumpsys', 'activity', 'activities'], timeout=8)
    if result.returncode or b'ACTIVITY MANAGER ACTIVITIES' not in result.stdout:
        # Some HD-Adb versions return success from connect even with no guest.
        state = _adb(binding, ['get-state'], timeout=5)
        if state.returncode or state.stdout.strip() in (b'offline', b'unknown'):
            raise bluestacks.InstanceError('VL-ADB-NOT-READY', 'Selected instance is not ready for ADB')
        return 'unknown'
    package = (PACKAGE + '/').encode('ascii')
    return ('running' if any(b'ActivityRecord{' in line and package in line
                             for line in result.stdout.splitlines()) else 'closed')


def stop_game(binding: Path) -> None:
    stopped = _adb(binding, ['shell', 'am', 'force-stop', PACKAGE], timeout=15)
    if stopped.returncode:
        raise bluestacks.InstanceError('VL-GAME-RESTART-FAILED', 'Android could not close Village Life')


def launch(binding: Path, *, restart: bool = False) -> None:
    if restart:
        stop_game(binding)
    result = _adb(binding, ['shell', 'monkey', '-p', PACKAGE, '1'], timeout=30)
    if result.returncode or b'Events injected: 1' not in result.stdout:
        raise bluestacks.InstanceError('VL-GAME-LAUNCH-FAILED', 'Android could not start Village Life')

