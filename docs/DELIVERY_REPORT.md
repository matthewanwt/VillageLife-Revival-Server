# Delivery report | New-backend-only Alpha | 10 November 2026

## Completed in uploaded source ZIP

- Removed `legacy_reference/` (28 old source modules and 40 original tests), old backend/server launcher paths, old runtime/asset packaging scripts, and old Windows test scripts that depended on historical server data. No current executable or build script loads the 2.11 backend.
- Rebuilt Windows packaging to use a PyInstaller **new** `villagelife` server executable and separate C# WinForms test manager; neither uses an old 2.11 runtime kit.
- Fixed SQLite backup target connection leakage and read-only game catalogue connection disposal; updated catalogue fixture commit. Added backup cleanup and integrity-check regression tests.
- Changed new database default to `%LOCALAPPDATA%\VillageLifeRevivalNext` to avoid original saves/installs. Stores instance bindings separately from accounts/game worlds.
- Added exact BlueStacks instance-ID binding, per-instance ADB port discovery, mismatch/rename/install-path checks, no default fallback, and ADB check.
- Added read-only network evidence report with explicit `policy_verified: false` and no firewall changes.
- Added privacy-minimised `404/501` HTTP endpoint summary and export tool; unknown original APK calls return explicit error and do not call an old backend.
- Added synthetic tests for separate 2.11-format profiles, multiple native villages, portable exports, extra unknown nested fields, import conflict detection, instance-switch prevention, and distinct independent SQLite databases.
- Added a source-only release audit and safe dry-run archival utility for obsolete files in older Git checkouts.
- Updated GitHub Actions to run Python tests on Linux and Windows and compile the C# test manager on a Windows runner.

## Verification completed in this environment

- `PYTHONPATH=src python -m unittest discover -s tests -q`: **29 tests passed**.
- `PYTHONPATH=src python tools/smoke_new_backend.py`: **passed** (real localhost HTTP process and throwaway SQLite DB).
- `python tools/release_audit.py`: **passed**.
- Python `compileall`: passed.
- ZIP integrity and forbidden-item audit: checked during packaging.

## Not completed / not claimed

- .NET compilation and Inno Setup installer compilation require a Windows host and have **not** been run in this environment.
- **Original APK is not playable with this new server**: binary login/process RPC and original gameplay rules are not implemented. No historical server fallback exists.
- Migrated historical saves are opaque; the real 2.11 field mapping, game startup, building production, Riverside/Mountain behaviour and player save parity are not verified.
- Wi-Fi-on network isolation remains unverified. Current Windows manager never starts the old client, changes firewall policy, or installs game assets.
- Automatically creating BlueStacks VMs via unsupported internal APIs is not implemented. Use the official Multi-instance Manager GUI, then bind exactly one instance.
- Exact-ID/name/port/path matching cannot guarantee a replaced VM has not reused all the same metadata. A stronger VM fingerprint requires validation on a real Windows installation.
- Windows-only `WinError 32` and clean-upgrade/uninstall scenarios must still pass actual Windows tests.

## Next acceptance step

Run the 29 tests on Windows Python 3.14, then `windows\installer\Build-TestInstaller.ps1`. Inspect the installer build stage, launch the NEW manager, start `/health`, test the separate `VLTest1` binding and ADB status, and import **copies only** of real 2.11 saves after a database backup. Do not invite real-player gameplay beta testing until original-client protocol and isolation are verified.
