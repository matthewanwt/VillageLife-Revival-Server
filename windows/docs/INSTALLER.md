# Windows single-EXE installer plan and build

**Status: Inno Setup source ready; an installer EXE is NOT yet built or validated.** This package was prepared on Linux and no Windows/.NET 10 SDK, BlueStacks installation or Inno Setup compiler was available for integration testing.

The goal is one `VillageLifeSetup.exe` downloaded by players. The installer contains the already-built C# launcher, Python runtime and the **legacy-compatible** server until the redesigned core reaches protocol parity. The Windows BlueStacks 5 runtime remains a **separate prerequisite**, and an original supported XAPK must be supplied by the player. Do not include EA/Playdemic's original game files unless redistribution rights are confirmed.

## Stage assembly (from an isolated build, never the working folder)

1. Produce a source-only Windows community player stage based on the verified legacy 2.11 backend. Ensure it includes `backend/server.py`, required tools, `StartVillageLife` compiled launcher, and bundled Python/.NET runtime. The redesigned Alpha is not yet a drop-in replacement.
2. Replace the stage `tools/` source files with `windows/tools/` from this repository (including `platforms/bluestacks/`, `runtime_errors.py`, and `export_diagnostics.py`). Replace the C# launcher source with `windows/launcher/`, compile using .NET 10 on Windows, and stage the compiled `StartVillageLife` files. **Do not substitute source `.cs` files for compiled binaries.**
3. Verify no player saves, `.xapk`, `.apk`, `.obb`, private keys or `play-settings.json` are in the stage.
4. Run in PowerShell:

```powershell
.\windows\installer\Build-Installer.ps1 -StageFolder "C:\VL-build\player-stage"
```

Inno Setup 6 emits `windows/installer/output/VillageLifeSetup.exe`. Test on a clean Windows x64 VM before sending it to any player.

## Current limitation: save storage

The legacy toolchain still assumes its root is writable (`play-settings.json`, `backend/private_state`, `analysis/runtime_inputs`, `backups`, `experiments`). This early installer therefore chooses **per-user** `%LOCALAPPDATA%\Programs\VillageLifeRevival` rather than `Program Files` to avoid access-denied failures. A production-ready upgrade should move mutable data into `%LOCALAPPDATA%\VillageLife\Data` using a copy-first migration with rollback; it must never erase older saves. The installer currently does not implement that migration.

## Required tests before publishing

- Clean install on an account that has never installed Python or .NET.
- Existing BlueStacks 5 on nonstandard install path; auto-detection.
- Fresh Pie64 and existing protected Pie64, including Asian-character display name.
- Wi-Fi enabled and disabled; local route and external guest probes.
- Port 80 occupied; specific `VL-PORT-IN-USE` message.
- ADB unavailable, slow boot, repeated timeouts, changed serial or missing ADB setting.
- Launch, stop, restart, save, restore, update and uninstall without changing existing saves.
- Export Diagnostics support bundle; review for PII/secret leaks.
- Windows security and licensing review prior to any general distribution.
