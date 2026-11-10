# Village Life Revival | New Backend Alpha

**This is a new, independent backend and Windows development test manager.**

The historical 2.11 server, its Python gameplay modules, private saves, and original client binaries are **not shipped or executed**. A one-way, non-destructive importer reads *copies* of old profile/tutorial saves. This is not yet a playable replacement for the original Village Life Android APK: its binary `ClientService` protocol and much gameplay remain unimplemented.

## Local Python tests (Windows PowerShell)

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The test suite runs on **synthetic** save fixtures and mock BlueStacks configs; it never reads your real saves, modifies a BlueStacks VM, or changes network restrictions.

To test the actual new backend locally:

```powershell
.\.venv\Scripts\python.exe -m villagelife init-db
.\.venv\Scripts\python.exe -m villagelife serve --port 8765
```

In another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

By default the new database is in `%LOCALAPPDATA%\VillageLifeRevivalNext\worlds.sqlite3`. It's deliberately distinct from old player saves. To test two completely separate profiles, add `--db "C:\SomeTestFolder\A.sqlite3"` / `--db "...\B.sqlite3"` **before** the command. You can create accounts and villages using the CLI, then test their APIs. Tests must not use real player data without an independent backup.

## Build the single EXE installer on Windows

Requires Windows x64, **.NET 10 SDK**, **Inno Setup 6**, and Python 3.11+ with PyInstaller installed in the local `.venv`.

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\windows\installer\Build-TestInstaller.ps1
```

The builder creates a standalone `VillageLifeServer.exe` with PyInstaller, publishes the WinForms manager as a self-contained .NET application, then creates `windows\installer\output\VillageLife-NextBackend-TestSetup.exe` with Inno Setup. **No old 2.11 runtime kit is needed.** Python is only required on the developer build computer, not on the testing computer. Build and actual installer execution require Windows; this source ZIP was **not** compiled into a Windows installer in the Linux validation environment.

The installed manager can start/stop the **new** API, check its health, enumerate and explicitly bind a BlueStacks Pie64 instance, revalidate its ADB port, generate a read-only network evidence report, and perform an old-save migration **dry run**. There is deliberately no button to run the original APK: no honest compatibility claim can be made until its RPC is ported and gameplay verified.

## Saved instance behaviour

Selection is by exact BlueStacks internal ID (`Pie64_4`, for example), not by display name or hardcoded ADB port. A deleted, renamed, or reconfigured selected instance generates an explicit error rather than defaulting to `Pie64`. Instance preferences are stored under `%LOCALAPPDATA%\VillageLifeRevivalNext`. The launcher never changes BlueStacks VM files or firewall rules.

**Wi-Fi-on game isolation is not solved.** Guest routing and a few failed external TCP probes are not evidence that all UDP, DNS, IPv6 or other egress is blocked. See `docs/READINESS_AND_GAPS.md`.

## Save migration

`python -m villagelife import-legacy <copy-of-private_state>` only reports what would be imported. `--apply` copies the original profile and tutorial save into opaque versioned records in the NEW database, preserving unknown fields. It never changes the source files. It **does not** translate legacy gameplay into playable native state yet. See `docs/SAVE_MIGRATION.md`.

## Repository policy

Keep XAPK/APK/OBB in a **Git-ignored** local folder (e.g. `private-assets/VillageLife.xapk`); none is required to build the new-backend test manager. Never commit real player saves, credentials, extracted game content or report ZIPs. A source-only installation is not permission to redistribute the original APK.

## Updating an existing checkout

**Copy-overwriting is not the same as removing obsolete files.** Commit or back up first. After extracting this ZIP into the GitHub repository, explicitly remove from the *new checkout only* any stale `legacy_reference/`, old `windows/tools/`, old `windows/tests/`, and previous `backend/` source folder. First inspect each for local player data, then move that data to a safe backup **outside Git**. Do not remove or alter the original 55 GB working installation. Keep `.git` intact. Inspect `git status` and the tracked-file list before pushing. This release archive intentionally contains no legacy backend source at all.

### Optional safe cleanup of previous repository-only files

To preview old source files left behind by copying ZIPs over an existing checkout:

```powershell
.\tools\Archive-ObsoleteRepositoryFiles.ps1 -ArchiveDir "C:\VL-Archive\OldRepoFiles"
```

After reviewing the list, commit your checkout, choose a new/empty external archive folder, then add `-Apply` to **move** those obsolete sources outside the repository. It never deletes, never touches `.git`, and deliberately leaves any `backend/` folder alone because it might hold live saves. Do not point it at the preserved 55 GB original project.

### Portable end-to-end smoke test

```powershell
.\.venv\Scripts\python.exe tools\smoke_new_backend.py
```

This runs the new API with an ephemeral localhost port and throwaway SQLite database, checks `/health`, verifies an old client endpoint correctly returns `501` rather than silently invoking 2.11, and verifies missing-request exports contain no submitted body or query string.
