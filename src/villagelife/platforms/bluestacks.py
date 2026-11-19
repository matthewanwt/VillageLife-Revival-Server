"""Read-only discovery and explicit binding to a BlueStacks Pie64 instance.

Never falls back to another VM or configures networking. The display name is a
human-readable hint, NOT the identity. Instances are owned by BlueStacks.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping
import json
import os
import re
import subprocess
import time


class InstanceError(RuntimeError):
    def __init__(self, code: str, explanation: str):
        super().__init__(f'[{code}] {explanation}')
        self.code = code


@dataclass(frozen=True)
class Instance:
    id: str
    display_name: str
    adb_port: int
    live_adb_port: int | None


def parse_instances(text: str) -> list[Instance]:
    if len(text) > 8_000_000:
        raise InstanceError('VL-BS-CONFIG-INVALID', 'BlueStacks configuration is too large')
    result: dict[str, dict[str, str]] = {}
    pattern = re.compile(r'^bst\.instance\.(Pie64(?:_\d+)?)\.(display_name|adb_port|status\.adb_port)="([^"\r\n]*)"\s*$', re.M)
    for match in pattern.finditer(text):
        ident, field, value = match.groups()
        row = result.setdefault(ident, {})
        if field in row:
            raise InstanceError('VL-BS-CONFIG-INVALID', 'Duplicate BlueStacks configuration field')
        row[field] = value
    instances = []
    for ident, data in sorted(result.items()):
        try:
            port = int(data['adb_port'])
            live = int(data['status.adb_port']) if 'status.adb_port' in data else None
            name = data['display_name']
            if not 1 <= port <= 65535 or (live is not None and not 1 <= live <= 65535):
                raise ValueError()
        except (KeyError, ValueError) as exc:
            raise InstanceError('VL-BS-CONFIG-INVALID', f'Incomplete or invalid instance {ident}') from exc
        instances.append(Instance(ident, name, port, live))
    return instances


def config_path(*, programdata: Path | None = None) -> Path:
    home = programdata or Path(os.environ.get('ProgramData', 'C:/ProgramData'))
    return home / 'BlueStacks_nxt' / 'bluestacks.conf'


def list_instances(*, config: Path | None = None) -> list[Instance]:
    try:
        return parse_instances((config or config_path()).read_text(encoding='utf-8-sig'))
    except OSError as exc:
        raise InstanceError('VL-BS-CONFIG-MISSING', 'BlueStacks configuration file is unavailable') from exc


def select_by_id(rows: list[Instance], ident: str, *, check_live_port: bool = True) -> Instance:
    """Only accept an exact stable internal ID. Never name/default fallback."""
    selected = [row for row in rows if row.id == ident]
    if len(selected) != 1:
        raise InstanceError('VL-BS-INSTANCE-MISSING', 'Selected instance is missing. Reselect it explicitly.')
    row = selected[0]
    if check_live_port and row.live_adb_port is not None and row.live_adb_port != row.adb_port:
        raise InstanceError('VL-BS-PORT-DIVERGED', f'{ident} ADB configuration and live port disagree')
    return row


def _registry_install_dir() -> Path | None:
    """Read BlueStacks 5 install dir from the Windows registry.

    BlueStacks 5 (nxt) writes InstallDir under one of several key names
    depending on edition and locale.  We try all known variants so a custom
    or region-specific install is still found.

    Keys checked (HKEY_LOCAL_MACHINE\\SOFTWARE\\<name>):
      • BlueStacks_nxt       – standard installer (most common)
      • BlueStacks_nxt_cn    – China-region edition
      • BlueStacks_msi5      – MSI / enterprise distributor variant

    Confidence: SUSPECTED for BlueStacks_msi5 (seen in secondary sources only;
    BlueStacks_nxt and BlueStacks_nxt_cn are CONFIRMED in community reports).
    Returns None on any error (non-Windows, key absent, permission denied).
    """
    try:
        import winreg
    except ImportError:
        return None  # not Windows
    _REG_KEYS = (
        r'SOFTWARE\BlueStacks_nxt',
        r'SOFTWARE\BlueStacks_nxt_cn',
        r'SOFTWARE\BlueStacks_msi5',
    )
    for key_name in _REG_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_name) as key:
                value, _ = winreg.QueryValueEx(key, 'InstallDir')
                if value:
                    return Path(value)
        except OSError:
            continue
    return None


def installation(*, search: list[Path] | None = None) -> Path:
    if search is None:
        search = []
        if os.environ.get('VILLAGELIFE_BLUESTACKS_HOME'):
            search.append(Path(os.environ['VILLAGELIFE_BLUESTACKS_HOME']))
        reg_dir = _registry_install_dir()
        if reg_dir is not None:
            search.append(reg_dir)
        for var in ('ProgramFiles', 'ProgramW6432', 'ProgramFiles(x86)'):
            if os.environ.get(var):
                search.append(Path(os.environ[var]) / 'BlueStacks_nxt')
        search.append(Path('C:/Program Files/BlueStacks_nxt'))
    for root in search:
        if (root / 'HD-Player.exe').is_file() and (root / 'HD-Adb.exe').is_file():
            return root.resolve()
    searched = '; '.join(str(p) for p in search) if search else '(none)'
    raise InstanceError(
        'VL-BS-NOT-FOUND',
        f'BlueStacks 5 not found. Repair or install BlueStacks 5.'
        f' Searched: {searched}.'
        f' Set VILLAGELIFE_BLUESTACKS_HOME to override.'
    )


def _atomic_settings(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.json.pending')
    try:
        pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def bind_instance(path: Path, selected: Instance, install_dir: Path) -> dict:
    """Remember the selected VM's identity. ADB still requires strict verification."""
    receipt = {'schema': 1, 'id': selected.id, 'name': selected.display_name,
               'adb_port': selected.adb_port, 'install_dir': str(install_dir.resolve()).casefold()}
    # This never touches BlueStacks itself and stores no account or save data.
    _atomic_settings(path, receipt)
    return receipt


def verify_binding(path: Path, rows: list[Instance], install_dir: Path, *, check_live_port: bool = True) -> Instance:
    try:
        receipt = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise InstanceError('VL-BS-INSTANCE-UNSET', 'Choose a BlueStacks instance before continuing') from exc
    if not isinstance(receipt, dict) or receipt.get('schema') != 1 or not isinstance(receipt.get('id'), str):
        raise InstanceError('VL-BS-BINDING-INVALID', 'Instance settings are invalid. Reselect the instance.')
    row = select_by_id(rows, receipt['id'], check_live_port=check_live_port)
    if receipt.get('adb_port') != row.adb_port:
        raise InstanceError('VL-BS-INSTANCE-CHANGED', 'ADB port changed. Reselect and verify the instance.')
    if receipt.get('name') != row.display_name:
        raise InstanceError('VL-BS-INSTANCE-RENAMED', 'Instance display name changed. Confirm selection again.')
    if receipt.get('install_dir') != str(install_dir.resolve()).casefold():
        raise InstanceError('VL-BS-INSTANCE-CHANGED', 'BlueStacks installation path changed. Confirm selection.')
    return row


def start_bound_instance(path: Path, *, protect=None) -> str:
    """Opt-in launch of a verified VM; does not install APKs or change networks."""
    root = installation()
    selected = verify_binding(path, list_instances(), root, check_live_port=False)
    if protect is not None:
        protect(selected.id)
    subprocess.Popen([str(root/'HD-Player.exe'), '--instance', selected.id],
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return selected.id


def adb_status(path: Path, *, once: bool = False) -> dict:
    root = installation()
    adb = root/'HD-Adb.exe'
    deadline = time.monotonic() + 45
    status = 'unreachable'
    while time.monotonic() < deadline:
        rows = list_instances()
        selected = verify_binding(path, rows, root, check_live_port=False)
        if selected.live_adb_port != selected.adb_port:
            status = 'initializing'
            if once:
                return {'instance': selected.id, 'name': selected.display_name,
                        'adb_port': selected.adb_port, 'connected': False, 'status': status}
            time.sleep(1)
            continue
        serial = f'127.0.0.1:{selected.adb_port}'
        try:
            hidden = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            def run(*args: str):
                return subprocess.run([str(adb), *args], capture_output=True,
                                      timeout=6, creationflags=hidden)
            run('connect', serial)
            probe = run('-s', serial, 'get-state')
            if probe.returncode == 0 and probe.stdout.strip() == b'device':
                boot = run('-s', serial, 'shell', 'getprop', 'sys.boot_completed')
                status = 'ready' if boot.returncode == 0 and boot.stdout.strip() == b'1' else 'booting'
            else:
                status = 'unreachable'
        except (OSError, subprocess.TimeoutExpired):
            status = 'tool_unavailable'
        if once or status == 'ready':
            return {'instance': selected.id, 'name': selected.display_name,
                    'adb_port': selected.adb_port, 'connected': status in {'booting', 'ready'},
                    'status': status}
        time.sleep(1)
    if status == 'tool_unavailable':
        raise InstanceError('VL-ADB-UNAVAILABLE', 'ADB command failed or timed out while waiting for the selected instance')
    if status == 'booting':
        raise InstanceError('VL-BS-BOOT-PENDING', 'ADB is connected, but Android has not finished starting')
    if status == 'initializing':
        raise InstanceError('VL-BS-PORT-DIVERGED', 'BlueStacks has not confirmed the selected instance’s ADB port')
    raise InstanceError('VL-ADB-NOT-READY', 'Selected instance did not become ready. Check that it is running and ADB is enabled.')


def open_manager() -> None:
    path = installation()/'HD-MultiInstanceManager.exe'
    if not path.is_file():
        raise InstanceError('VL-BS-MANAGER-MISSING', 'BlueStacks Multi-instance Manager is unavailable')
    subprocess.Popen([str(path)], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
