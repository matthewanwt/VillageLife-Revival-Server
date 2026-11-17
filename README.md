# Village Life Revival

This repository contains a **new server implementation** with an original Android-client compatibility layer under `src/villagelife/protocol/original_client/`. It **does not** ship or invoke the old 2.11 backend. Original client materials are read from local, user-supplied files outside Git.

## Play on Windows

**[Download the latest Windows release](https://github.com/matthewanwt/VillageLife-Revival-Server/releases/latest)** · **[Browse all versions](https://github.com/matthewanwt/VillageLife-Revival-Server/releases)**

Open a release and look under **Assets** for the Windows setup EXE. It includes the game archive and expansion, launcher, and local server. Install BlueStacks with a Pie 64-bit instance, then open the launcher and click **Play** for guided setup.

Close the game and launcher before updating. Keep a copy of your save. Use **Choose Village** to select an existing local village, including after changing BlueStacks instances. For a 0.2.6 backup, use **Import 0.2.6 Save** and choose the extracted `private_state` folder.

Gameplay coverage and known gaps are documented in `docs/ORIGINAL_OPERATION_COVERAGE.md` and `docs/REMAINING_GAMEPLAY.md`.

## Develop and test on Windows

Open PowerShell in your cloned project:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools\smoke_new_backend.py
.\.venv\Scripts\python.exe tools\smoke_original_diagnostics.py
```

`smoke_original_diagnostics.py` creates a disposable synthetic original-client
save and exercises compressed/XOR framing, selected RPCs, replay handling,
account isolation, and the privacy-safe diagnostic export. It does not use
BlueStacks, the original APK, private game tables, or an existing save.

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

## Windows reliability-test installer

`windows/installer/Build-TestInstaller.ps1` builds a private **reliability-test** installer, not a finished game release. At your direction, the handoff bundle includes the supplied XAPK and required game table/inventory data, the new backend, launcher, and Java signing tools. The OBB is extracted from the XAPK on first setup to avoid a duplicate copy. The old 2.11 server is neither included nor a fallback.

First use requires a dedicated BlueStacks Pie64 instance. The launcher warns before replacing an installed original-signed app and keeps saves, prepared files, and the local signing identity in `%LOCALAPPDATA%\VillageLifeRevivalNext`. Guest network isolation has not been certified.

Build the private test installer from PowerShell with Python dependencies, .NET 10, Inno Setup 6, and the downloaded JDK:

```powershell
.\windows\installer\Build-TestInstaller.ps1
```

## Repository and preservation

Do not commit APK/XAPK/OBB, extracted artwork, game tables, player saves, device IDs, secrets or logs. Keep your preserved 55 GB project and working 2.11 installation untouched. Use this repository for new code only. Source compatibility testing used locally supplied reference files; those private/proprietary reference bytes are **not in the source release**.

Read `docs/ORIGINAL_CLIENT_PROTOCOL.md`, `docs/ORIGINAL_OPERATION_COVERAGE.md`, and `docs/REMAINING_GAMEPLAY.md` before treating this build as playable.
