# Village Life Revival | Independent Backend Development Build

This repository contains a **new server implementation** with an original Android-client compatibility layer under `src/villagelife/protocol/original_client/`. It **does not** ship or invoke the old 2.11 backend. Original client materials are read from local, user-supplied files outside Git.

**Current milestone, 10 November 2026:** original-format HTTP login, tutorial checkpoint and bridge, initial village startup, limited area and deterministic work operations, and independent SQLite saves have passed local automated/smoke tests. **It has not been verified to play the original XAPK on Windows.** The original game still requires many RPCs and world rules that are documented in `docs/ORIGINAL_OPERATION_COVERAGE.md` and `docs/REMAINING_GAMEPLAY.md`.

## Develop and test on Windows

Open PowerShell in your cloned project:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools\smoke_new_backend.py
```

For the original-wire smoke test, supply the **locally extracted** original definitions database. Do not add it to Git:

```powershell
.\.venv\Scripts\python.exe tools\smoke_original_client.py --game-tables "C:\VL-Private\game_tables.sqlite"
```

You may add `--legacy-saves "C:\VL-Private\save-backup"` to test a *copy* of old profile/tutorial saves. The source hashes are checked unchanged. This verifies import and request response structure, **not** full gameplay semantics.

## Run the new backend with original-client endpoints

```powershell
.\.venv\Scripts\python.exe -m villagelife --db "$env:LOCALAPPDATA\VillageLifeRevivalNext\worlds.sqlite3" serve --port 80 --game-tables "C:\VL-Private\game_tables.sqlite" --xapk ".\private-assets\VillageLife.xapk" --obb "C:\VL-Private\main.obb" --inventory "C:\VL-Private\obb_tcf.inventory.csv"
```

This is for isolated developer analysis only. The original client is patched for `10.0.2.2:80` and separate game resources may be needed. **Running this server does not prove BlueStacks guest isolation** and does not grant permission to distribute the game. Never disable network protection merely to reach the local server.

The private XAPK can live under `private-assets/` (Git-ignored). Run `tools/prepare_original_client.py --help` to inspect local extraction/patch/signing options. It does **not** automatically install the APK or verify network egress restrictions. Keep a stable local signing identity for upgrades.

## Save migration

```powershell
.\.venv\Scripts\python.exe -m villagelife import-legacy "C:\VL-Private\save-backup"
```

This is a read-only dry run. Use `--apply` only on a **backup copy** with a new, separately backed-up database. Existing save payloads and unknown fields are retained as opaque data and are not yet fully translated into verified playable game semantics. See `docs/SAVE_MIGRATION.md`.

## Windows installer

**The Inno Setup build is deliberately blocked** with `VL-INSTALLER-NOT-READY` until the real original APK completes launch, gameplay and save/reload against the new backend, the guided BlueStacks/XAPK setup is implemented, and safe Wi-Fi-on guest network isolation is established. You requested no incomplete installer, so an API-only EXE is not presented as a finished product.

The future single installer must use the **new** backend, offer first-run instance selection/creation guidance and XAPK installation, and keep user saves in `%LOCALAPPDATA%` across updates. The previous 2.11 server is neither included nor a fallback.

## Repository and preservation

Do not commit APK/XAPK/OBB, extracted artwork, game tables, player saves, device IDs, secrets or logs. Keep your preserved 55 GB project and working 2.11 installation untouched. Use this repository for new code only. Source compatibility testing used locally supplied reference files; those private/proprietary reference bytes are **not in the source release**.

Read `docs/ORIGINAL_CLIENT_PROTOCOL.md`, `docs/ORIGINAL_OPERATION_COVERAGE.md`, and `docs/REMAINING_GAMEPLAY.md` before treating this build as playable.
