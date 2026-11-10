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

## New: isolated test installer build (2.11 instance management + missing-RPC reports)

The source repository now includes `windows/installer/Build-TestInstaller.ps1`.
It stages from a **clean extracted 2.11 player kit** into a new temporary folder,
adds the current compatibility server from `legacy_reference/backend/`,
overlays current `windows/tools/`, compiles the WinForms launcher, and invokes
Inno Setup. **It never modifies the original player kit or live save.**

On **Windows** with **.NET 10 SDK** and **Inno Setup 6** installed:

```powershell
.\windows\installer\Build-TestInstaller.ps1 -PlayerKitRoot "C:\VillageLife\clean-2.11-player-kit"
```

The supplied clean player kit must have `runtime/python/python.exe` and
`runtime/dotnet/dotnet.exe`; it is needed only as the source of previously
prepared redistributable runtimes. It need not include the original XAPK,
player saves or game assets; the script does not copy them. Do **not** use the
55 GB working folder as your staging directory.

Result (after a successful Windows build):
`windows/installer/output/VillageLife-TestSetup.exe`.
The installer has a **separate test AppId and install folder** from old 2.11
and does not overwrite the existing portable game installation.

The launcher has an **Instance Manager** button to open BlueStacks' GUI for
creating a dedicated Pie64 instance, explicit instance selection when multiple
instances exist, and a persistent binding to the selected stable internal ID.
It discovers the ADB port on every launch and does not auto-edit VM files.
Creation cannot currently be automated using a documented supported BlueStacks CLI.

The **Export Missing Requests** button creates an allowlisted, anonymised ZIP
from the compatibility backend's 501 failures. This is not raw packet capture.
It is safe for developer triage but still requires a user to review it before
private sharing. Missing original game rules remain unimplemented.

**Not yet validated:** Windows compilation, a Windows installer run, a clean
BlueStacks first-run installation, game signing/startup, and Wi-Fi-on isolation.
The current routing evidence for VLTest1 shows Android has an external IPv4
route through `10.0.2.2`. Without a verified blocking policy, setup may
correctly reject the guest. This test installer must not be promoted to a
community release until the networking and gameplay acceptance checks pass.
