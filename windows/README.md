# Windows new-backend-only test manager

This module is **not the original Android game's launcher**. It is a developer UI for the NEW modular server and BlueStacks **instance diagnostics only**. The old 2.11 backend, local-play scripts, signing utilities and APK installer are intentionally absent. The game cannot run on this backend until the original binary login/process RPC is independently implemented.

## Build on Windows (developer only)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e . pyinstaller
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\windows\installer\Build-TestInstaller.ps1
```

Requires installed .NET 10 SDK and Inno Setup 6. Output in `windows\installer\output\VillageLife-NextBackend-TestSetup.exe`.

PyInstaller creates `VillageLifeServer.exe` (NEW server) and Inno Setup packs that plus a self-contained .NET manager in a single installer. Python and .NET do **not** need to be installed on the testing machine. Proprietary game files, old server and player saves are excluded.

**The build script has not been executed on Windows in this environment.** If it fails, preserve its exact error output so we can fix the build without touching the original 2.11 installation.

## Test manager capabilities

- Start/stop/check NEW `/health` HTTP API at 127.0.0.1:8765
- List BlueStacks Pie64 VMs; bind an explicitly selected internal ID; detect stale VM/port/name/install path
- Start and ADB-check the selected VM, and open official BlueStacks Multi-instance Manager GUI
- Show read-only network metadata with an explicit `policy_verified: false`
- Dry-run import of old saves using a selected source **copy**
- Export missing-request summary and minimal support bundle

Real import requires a deliberate CLI `--apply`, never an automatic UI action.
