# Windows / BlueStacks 5 compatibility integration (2.11 source)

This folder was reconstructed from the **user-uploaded 2.11 `tools.zip`**, not from the older community release. It contains updated **source files** for the original Windows launcher and locally-running legacy server, alongside the **separate** redesigned backend in `../src/villagelife`.

**Do not overwrite the working v2.11 folder with this integration.** The new backend in this repository is still alpha, and the original Android client cannot use its API yet. The Windows integration is a candidate patch to evaluate on a copy of the working v2.11 folder.

## Layout

```text
windows/
  tools/
    play_local.py                 existing session flow, safer startup/backups/logs
    setup_local.py                dedicated-instance setup, bounded ADB boot retries
    network_check.py              original strict guest isolation assessment
    export_diagnostics.py        allowlisted, redacted player support bundle
    runtime_errors.py            specific VL-* error codes
    platforms/bluestacks/
      discovery.py                find installed BlueStacks 5 binaries
      instances.py                parse Pie64 instance IDs and validate last binding
      adb.py                      bounded ADB operations and boot retries
      net_assurance.py            fail-closed Wi-Fi-on network probes
      ports.py                    explicit port-80 preflight and informative candidates
  launcher/                       WinForms .NET 10 C# source (diagnostic button, UTF-8)
  tests/                          synthetic compatibility tests + original tools tests
  installer/                      Inno Setup source and Windows build script
  docs/                           network acceptance, installer build checklist
```

The rest of `tools/` consists of source-only scripts retained from the user upload for eventual merge/reference. The `tools.zip` included original compiled WinForms binaries; **those binary outputs are intentionally not committed**. Compile `launcher/` on Windows using .NET 10; use the resulting binaries during player-release staging.

## Main improvements

1. **Adaptive ADB**: per-attempt timeout grows from short checks to capped longer checks, governed by a 300-second monotonic overall startup deadline. A hung individual `adb connect` does not immediately abort the entire startup. Only the configured serial is addressed.
2. **UTF-8**: the C# UI starts Python subprocesses with explicit UTF-8 output/error encodings and `PYTHONIOENCODING=utf-8:replace`. Python prints are reconfigured where available.
3. **Discovery**: BlueStacks binaries are located via an explicit override, registry hints and common program directories. No hard-coded `C:\Program Files` assumption is needed in the active play/setup path.
4. **Instance consistency**: on setup, `play-settings.json` records a binding for instance ID, ADB port and install directory. Later launches compare it against current BlueStacks configuration and fail visibly rather than silently using a different instance. Existing settings without a binding still work if their saved instance/port match.
5. **Port preflight**: precise `VL-PORT-IN-USE`. **The current patched APK requires port 80**; the available-port scanner is informational until APK repatching to a different port has been validated.
6. **Wi-Fi checks**: local host route and guest external connectivity are checked independently. No code was added to bypass isolation or to change system-wide firewall rules. A real Wi-Fi-on isolation fix is **not yet verified**; see `docs/WIFI_AND_ROUTING.md`.
7. **Support**: the launcher adds an Export Diagnostics button; failures have stable `VL-*` codes. Support ZIP contains only selected, redacted configuration/error reports, not saves, APKs, original game assets, passwords or raw Android logs.
8. **Size control**: new sessions take one pre-play save backup instead of two; Android and backend session logs are limited to approximately 8 MiB each. Old sessions, backups and the source folder are **never deleted**.
9. **Installer source**: build a single player-facing EXE with Inno Setup once a complete, verified Windows player stage is available, following `docs/INSTALLER.md`. The installer uses a per-user writable directory in this interim version.

## Tests

Run from the repository root (Python 3.11+):

```powershell
$env:PYTHONPATH = "windows/tools"
python -m unittest discover -s windows/tests -p test_bluestacks_adapter.py -v
```

To run the source-tool tests that don't need original data:

```powershell
$env:PYTHONPATH = "windows/tools"
python -m unittest discover -s windows/tests -p test_network_check.py -v
python -m unittest discover -s windows/tests -p test_setup_local.py -v
```

Some retained original tools tests import original game modules and require the locally generated `analysis/private/game_tables.sqlite`. They must be run against a private, disposable fixture and are not part of the synthetic Windows checks. Do not add this database to Git.

## Field testing sequence

Use a copy of an existing 2.11 player installation. **Never use a real player's live save as a test fixture.** Copy the changed Python tools and `tools/platforms/` to the copied installation, rebuild the WinForms launcher, and verify startup. Test a clean Pie64 instance before testing any upgrade path.

Run checks in this order: (a) no BlueStacks, (b) correctly installed BlueStacks, (c) intentionally invalid/changed instance port, (d) slow/hung ADB, (e) port 80 occupied, (f) backend startup crash, (g) local guest route, (h) **Wi-Fi enabled with external guest probes**, (i) normal game launch/restart/save/stop. Check the Support ZIP before sharing it with developers.

**Release criteria:** no full community release until a Windows test confirms the latest code boots the original APK and the Wi-Fi-on external isolation tests are passed. The source currently does **not** guarantee that result.

## Latest Wi-Fi/instance mapping update (non-invasive diagnostic)

The new `tools/diagnose_network.py` and `platforms/bluestacks/host_network.py`
collect sanitised process, network adapter and connection categories on Windows
without changing firewall rules or emulator settings. `tools/platforms/bluestacks/instances.py`
now verifies `status.adb_port` against the configured ADB port; a mismatch fails
with `VL-BS-PORT-DIVERGED`. The WinForms source has a **Network Check** button;
`Export Diagnostics` can include the resulting redacted report.

**No Wi-Fi isolation mechanism has been implemented or tested on a real BlueStacks VM.**
See `docs/NETWORK_TOPOLOGY_DIAGNOSTICS.md` for exact commands, limitations and
the dedicated-VM test sequence. These additions do not make the Alpha backend
APK-compatible and do not constitute a compiled Windows installer.

## 2.11 separate test-installer and unimplemented-RPC update

- **Instance Manager** now opens `HD-MultiInstanceManager.exe` (BlueStacks' GUI)
  for guided instance creation. VM management still uses `BstkVMMgr.exe` only
  where the existing verified setup already did so. The launcher never chooses
  between multiple instances without the player's explicit selection or a
  previously verified ID. For VLTest1, that internal ID is `Pie64_4`, with
  port `5595` at the time of the user's diagnostic.
- **Export Missing Requests** invokes `tools/export_missing_requests.py`. The
  instrumented 2.11 compatibility backend logs bounded metadata for unknown
  endpoints, failed RPC services and explicit server errors, without raw
  payloads. See `docs/MISSING_REQUEST_REPORTS.md`.
- **Build-TestInstaller.ps1** generates a separate development-only installer
  on Windows from a clean prior 2.11 player kit and the current source.
  See `docs/INSTALLER.md`. The EXE has not been compiled or tested here.
- Wi-Fi-on safety **is not yet fixed**. Android's route to external `1.1.1.1`
  goes via `10.0.2.2` on the observed `VLTest1` environment. Existing
  fail-closed checks remain in place; do not bypass them.

## Stale BlueStacks selection guard (additional regression fix)

The original 2.11 scripts sometimes silently selected a default instance when
`play-settings.json` contained an outdated selection. The new play path **never
uses a default VM or port**. It validates the selected internal ID, configured
and live ADB port, BlueStacks installation location, and any previously saved
human-readable display name. A missing/changed selection or unexpected rename
is an actionable error, not permission to play on the default instance.
`Set Up Game` explicitly lists the available instances and requires a user
selection. No running VM or saved game is automatically changed by this guard.

Current limitation: a deleted VM recreated with the *same* internal ID, port,
name and installation path cannot be reliably distinguished using these fields
alone. Add an independently verified VM identity receipt before promising
complete reinstall detection. Do not rely on display names as unique IDs.

Developer XAPK placement: `windows/VillageLife-Original.xapk` is accepted by
these older tools because they search the `windows/` runtime root for a single
`*.xapk`. `.gitignore` excludes XAPKs and `play-settings.json` from Git.
The installer deliberately excludes game assets; player setup imports a
user-provided XAPK separately.
