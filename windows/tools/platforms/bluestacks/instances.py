"""Read and validate the real BlueStacks Pie64 instance, not a hardcoded ADB port.

A configured instance cannot silently switch to a different VM or TCP endpoint.
"""
from __future__ import annotations
import os
import re
from pathlib import Path
from runtime_errors import VillageRuntimeError


def available_instances(text=None, *, programdata=None):
    if text is None:
        base = Path(programdata or os.environ.get("ProgramData", r"C:\ProgramData"))
        path = base / "BlueStacks_nxt" / "bluestacks.conf"
        try:
            text = path.read_text(encoding="utf-8-sig")
        except OSError as ex:
            raise VillageRuntimeError("VL-BS-CONFIG-MISSING", "BlueStacks instance configuration was not found.", "Open BlueStacks Multi-instance Manager and create a Pie64 instance.") from ex
    if len(text) > 8_000_000:
        raise VillageRuntimeError("VL-BS-CONFIG-INVALID", "BlueStacks instance configuration is unexpectedly large.")
    rows = {}
    for match in re.finditer(r'^bst\.instance\.([^.=\s]+)\.(display_name|adb_port|status\.adb_port)="([^"\r\n]*)"\s*$', text, re.MULTILINE):
        key, name, value = match.groups()
        if not re.fullmatch(r"Pie64(?:_\d+)?", key):
            continue
        entry = rows.setdefault(key, {})
        if name in entry:
            raise VillageRuntimeError("VL-BS-CONFIG-INVALID", f"BlueStacks has duplicate {name} entries for {key}.")
        entry[name] = value
    result = []
    for key, row in sorted(rows.items()):
        if "display_name" not in row or "adb_port" not in row:
            raise VillageRuntimeError("VL-BS-CONFIG-INVALID", f"Incomplete configuration for instance {key}.", "Recreate or repair this instance in BlueStacks Multi-instance Manager.")
        try:
            port = int(row["adb_port"])
        except ValueError:
            port = -1
        if not 1 <= port <= 65535:
            raise VillageRuntimeError("VL-BS-CONFIG-INVALID", f"Invalid ADB port for {key}.")
        # The live status port may differ from the configured port after an
        # emulator restart or BlueStacks update. Never silently retarget ADB.
        status_text = row.get("status.adb_port")
        try:
            status_port = int(status_text) if status_text else None
        except ValueError:
            status_port = -1
        if status_port is not None and not 1 <= status_port <= 65535:
            raise VillageRuntimeError("VL-BS-CONFIG-INVALID", f"Invalid live ADB port for {key}.")
        # Do not reject ALL instances because an unrelated VM has stale status.
        # Only the selected VM is prohibited from connecting on divergent ports.
        result.append({"id": key, "name": row["display_name"], "adb_port": port, "status_adb_port": status_port})
    return result


def select_instance(instances, selection):
    if not selection:
        raise VillageRuntimeError("VL-BS-INSTANCE-UNSET", "A dedicated Pie64 instance has not been selected.", "Click Set Up Game and choose a dedicated instance.")
    by_id = [row for row in instances if row["id"] == selection]
    candidates = by_id or [row for row in instances if row["name"] == selection]
    if len(candidates) != 1:
        raise VillageRuntimeError("VL-BS-INSTANCE-MISSING", "The selected BlueStacks instance is unavailable or ambiguous.", "Open Set Up Game and reselect the original dedicated instance. Do not overwrite another instance's game data.")
    chosen = candidates[0]
    if chosen.get('status_adb_port') is not None and chosen['status_adb_port'] != chosen['adb_port']:
        raise VillageRuntimeError(
            'VL-BS-PORT-DIVERGED',
            f"BlueStacks {chosen['id']} reports configured ADB port {chosen['adb_port']} but live status port {chosen['status_adb_port']}.",
            'Close the selected instance, inspect Multi-instance Manager, and collect diagnostics before changing any stored port.',
        )
    return chosen


def validate_binding(settings, selected, installation):
    """Check both the old simple settings and newer immutable binding receipt."""
    if selected["id"] != settings.get("instance") or selected["adb_port"] != settings.get("adb_port"):
        raise VillageRuntimeError("VL-BS-INSTANCE-CHANGED", "The saved BlueStacks instance or its ADB port has changed.", "Open Set Up Game and verify the original dedicated instance. Saves have not been modified.")
    # Display names are not identities, but an unexpected rename is a useful
    # signal that a user may have changed or recreated their instance. Stop
    # instead of silently treating the old display name as a new instance.
    previous_name = settings.get("instance_display_name")
    if isinstance(previous_name, str) and previous_name != selected["name"]:
        raise VillageRuntimeError(
            "VL-BS-INSTANCE-RENAMED",
            f"BlueStacks instance {selected['id']} was previously named {previous_name!r} and is now named {selected['name']!r}.",
            "Open Set Up Game and confirm the intended instance before continuing. The launcher will not switch instances or modify saves automatically.",
        )
    bound = settings.get("instance_binding")
    if bound:
        expected = {"id": selected["id"], "adb_port": selected["adb_port"], "installation": installation.key}
        if any(bound.get(k) != v for k, v in expected.items()):
            raise VillageRuntimeError("VL-BS-INSTANCE-CHANGED", "BlueStacks no longer matches the last verified installation.", "Review the instance in Set Up Game. Do not blindly select a different instance.")
    return selected


def make_binding(selected, installation):
    return {"id": selected["id"], "adb_port": selected["adb_port"], "installation": installation.key}


def diagnostic_port_map(text: str) -> list[dict]:
    """Lenient, strictly read-only view for reports if configuration is inconsistent.

    Unlike available_instances(), does not hide the remaining instances just
    because a single VM has a missing or divergent live ADB port. Never use
    these entries to connect to ADB or start an instance.
    """
    if len(text) > 8_000_000:
        return []
    rows: dict[str, dict] = {}
    pattern = r'^bst\.instance\.(Pie64(?:_\d+)?)\.(display_name|adb_port|status\.adb_port)="([^"\r\n]*)"\s*$'
    for match in re.finditer(pattern, text, re.MULTILINE):
        vm, field, value = match.groups()
        entry = rows.setdefault(vm, {'id': vm})
        if field in entry:
            entry['duplicate_entry'] = True
        entry[field] = value
    output = []
    for vm, entry in sorted(rows.items()):
        def port(key):
            try:
                value = int(entry.get(key, ''))
                return value if 1 <= value <= 65535 else None
            except ValueError:
                return None
        conf = port('adb_port')
        live = port('status.adb_port')
        errors = []
        if conf is None:
            errors.append('configured_port_missing_or_invalid')
        if 'status.adb_port' in entry and live is None:
            errors.append('live_port_invalid')
        if live is not None and conf is not None and live != conf:
            errors.append('configured_live_port_mismatch')
        if entry.get('duplicate_entry'):
            errors.append('duplicate_config_entry')
        output.append({'id': vm, 'name': entry.get('display_name', ''),
                       'adb_port': conf, 'status_adb_port': live, 'warnings': errors})
    return output
