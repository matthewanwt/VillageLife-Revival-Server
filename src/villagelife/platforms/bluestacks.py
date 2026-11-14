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


def select_by_id(rows: list[Instance], ident: str) -> Instance:
    """Only accept an exact stable internal ID. Never name/default fallback."""
    selected = [row for row in rows if row.id == ident]
    if len(selected) != 1:
        raise InstanceError('VL-BS-INSTANCE-MISSING', 'Selected instance is missing. Reselect it explicitly.')
    row = selected[0]
    if row.live_adb_port is not None and row.live_adb_port != row.adb_port:
        raise InstanceError('VL-BS-PORT-DIVERGED', f'{ident} ADB configuration and live port disagree')
    return row


def installation(*, search: list[Path] | None = None) -> Path:
    if search is None:
        search = []
        if os.environ.get('VILLAGELIFE_BLUESTACKS_HOME'):
            search.append(Path(os.environ['VILLAGELIFE_BLUESTACKS_HOME']))
        for var in ('ProgramFiles','ProgramW6432','ProgramFiles(x86)'):
            if os.environ.get(var): search.append(Path(os.environ[var])/'BlueStacks_nxt')
        search.append(Path('C:/Program Files/BlueStacks_nxt'))
    for root in search:
        if (root/'HD-Player.exe').is_file() and (root/'HD-Adb.exe').is_file():
            return root.resolve()
    raise InstanceError('VL-BS-NOT-FOUND', 'BlueStacks 5 not found. Repair or install BlueStacks 5.')


def _atomic_settings(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.json.pending')
    try:
        pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def bind_instance(path: Path, selected: Instance, install_dir: Path) -> dict:
    if selected.live_adb_port is not None and selected.live_adb_port != selected.adb_port:
        raise InstanceError('VL-BS-PORT-DIVERGED', 'Cannot bind an instance with a changed live port')
    receipt = {'schema': 1, 'id': selected.id, 'name': selected.display_name,
               'adb_port': selected.adb_port, 'install_dir': str(install_dir.resolve()).casefold()}
    # This never touches BlueStacks itself and stores no account or save data.
    _atomic_settings(path, receipt)
    return receipt


def verify_binding(path: Path, rows: list[Instance], install_dir: Path) -> Instance:
    try:
        receipt = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise InstanceError('VL-BS-INSTANCE-UNSET', 'Choose a BlueStacks instance before continuing') from exc
    if not isinstance(receipt, dict) or receipt.get('schema') != 1 or not isinstance(receipt.get('id'), str):
        raise InstanceError('VL-BS-BINDING-INVALID', 'Instance settings are invalid. Reselect the instance.')
    row = select_by_id(rows, receipt['id'])
    if receipt.get('adb_port') != row.adb_port:
        raise InstanceError('VL-BS-INSTANCE-CHANGED', 'ADB port changed. Reselect and verify the instance.')
    if receipt.get('name') != row.display_name:
        raise InstanceError('VL-BS-INSTANCE-RENAMED', 'Instance display name changed. Confirm selection again.')
    if receipt.get('install_dir') != str(install_dir.resolve()).casefold():
        raise InstanceError('VL-BS-INSTANCE-CHANGED', 'BlueStacks installation path changed. Confirm selection.')
    return row


def start_bound_instance(path: Path) -> str:
    """Opt-in launch of a verified VM; does not install APKs or change networks."""
    root = installation()
    selected = verify_binding(path, list_instances(), root)
    subprocess.Popen([str(root/'HD-Player.exe'), '--instance', selected.id],
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    return selected.id


def adb_status(path: Path) -> dict:
    root = installation()
    selected = verify_binding(path, list_instances(), root)
    serial = f'127.0.0.1:{selected.adb_port}'
    adb = root/'HD-Adb.exe'
    deadline = time.monotonic() + 45
    command_failed = False
    while time.monotonic() < deadline:
        try:
            hidden = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            connected = subprocess.run([str(adb), 'connect', serial], capture_output=True,
                                       timeout=6, creationflags=hidden)
            probe = subprocess.run([str(adb), '-s', serial, 'get-state'], capture_output=True,
                                   timeout=6, creationflags=hidden)
        except (OSError, subprocess.TimeoutExpired):
            command_failed = True
        else:
            if (not connected.returncode and not probe.returncode and
                    probe.stdout.decode('utf-8','replace').strip() == 'device'):
                return {'instance': selected.id, 'adb_port': selected.adb_port, 'connected': True}
        time.sleep(1)
    if command_failed:
        raise InstanceError('VL-ADB-UNAVAILABLE', 'ADB command failed or timed out while waiting for the selected instance')
    raise InstanceError('VL-ADB-NOT-READY', 'Selected instance did not become ready. Check that it is running and ADB is enabled.')


def open_manager() -> None:
    path = installation()/'HD-MultiInstanceManager.exe'
    if not path.is_file():
        raise InstanceError('VL-BS-MANAGER-MISSING', 'BlueStacks Multi-instance Manager is unavailable')
    subprocess.Popen([str(path)], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
