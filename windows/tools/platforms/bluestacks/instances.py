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
    for match in re.finditer(r'^bst\.instance\.([^.=\s]+)\.(display_name|adb_port)="([^"\r\n]*)"\s*$', text, re.MULTILINE):
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
        result.append({"id": key, "name": row["display_name"], "adb_port": port})
    return result


def select_instance(instances, selection):
    if not selection:
        raise VillageRuntimeError("VL-BS-INSTANCE-UNSET", "A dedicated Pie64 instance has not been selected.", "Click Set Up Game and choose a dedicated instance.")
    by_id = [row for row in instances if row["id"] == selection]
    candidates = by_id or [row for row in instances if row["name"] == selection]
    if len(candidates) != 1:
        raise VillageRuntimeError("VL-BS-INSTANCE-MISSING", "The selected BlueStacks instance is unavailable or ambiguous.", "Open Set Up Game and reselect the original dedicated instance. Do not overwrite another instance's game data.")
    return candidates[0]


def validate_binding(settings, selected, installation):
    """Check both the old simple settings and newer immutable binding receipt."""
    if selected["id"] != settings.get("instance") or selected["adb_port"] != settings.get("adb_port"):
        raise VillageRuntimeError("VL-BS-INSTANCE-CHANGED", "The saved BlueStacks instance or its ADB port has changed.", "Open Set Up Game and verify the original dedicated instance. Saves have not been modified.")
    bound = settings.get("instance_binding")
    if bound:
        expected = {"id": selected["id"], "adb_port": selected["adb_port"], "installation": installation.key}
        if any(bound.get(k) != v for k, v in expected.items()):
            raise VillageRuntimeError("VL-BS-INSTANCE-CHANGED", "BlueStacks no longer matches the last verified installation.", "Review the instance in Set Up Game. Do not blindly select a different instance.")
    return selected


def make_binding(selected, installation):
    return {"id": selected["id"], "adb_port": selected["adb_port"], "installation": installation.key}
