"""BlueStacks path discovery with explicit override, common paths and registry hints.

No arbitrary directory searches or changes to BlueStacks configuration are made.
"""
from __future__ import annotations
import os
from pathlib import Path
from dataclasses import dataclass
from runtime_errors import VillageRuntimeError


@dataclass(frozen=True)
class BlueStacksInstallation:
    directory: Path

    @property
    def adb(self) -> Path:
        return self.directory / "HD-Adb.exe"

    @property
    def player(self) -> Path:
        return self.directory / "HD-Player.exe"

    @property
    def manager(self) -> Path:
        return self.directory / "BstkVMMgr.exe"

    @property
    def key(self) -> str:
        return str(self.directory.resolve()).casefold()


def _registry_hints():
    try:
        import winreg
    except ImportError:
        return []
    discovered = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for keyname in (r"SOFTWARE\BlueStacks_nxt", r"SOFTWARE\WOW6432Node\BlueStacks_nxt"):
            try:
                with winreg.OpenKey(hive, keyname) as key:
                    for value in ("InstallDir", "InstallPath"):
                        try:
                            path, _ = winreg.QueryValueEx(key, value)
                            if isinstance(path, str):
                                discovered.append(Path(path))
                        except OSError:
                            pass
            except OSError:
                pass
    return discovered


def discover_bluestacks(environ=None, *, candidates=None, require_manager=False):
    """Return the first complete installation, or an actionable typed failure.

    ``candidates`` is injectable to keep this testable on non-Windows systems.
    """
    env = os.environ if environ is None else environ
    possible = []
    override = env.get("VILLAGELIFE_BLUESTACKS_HOME")
    if override:
        possible.append(Path(override))
    if candidates is not None:
        possible.extend(Path(c) for c in candidates)
    else:
        possible.extend(_registry_hints())
        for key in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            if env.get(key):
                possible.append(Path(env[key]) / "BlueStacks_nxt")
        possible.append(Path(r"C:\Program Files\BlueStacks_nxt"))
    seen = set()
    for path in possible:
        resolved = str(path).casefold()
        if resolved in seen:
            continue
        seen.add(resolved)
        result = BlueStacksInstallation(path)
        if result.adb.is_file() and result.player.is_file() and (not require_manager or result.manager.is_file()):
            return result
    raise VillageRuntimeError(
        "VL-BS-NOT-FOUND", "BlueStacks 5 installation could not be located.",
        "Install BlueStacks 5 or set VILLAGELIFE_BLUESTACKS_HOME to the folder containing HD-Adb.exe and HD-Player.exe.",
    )
