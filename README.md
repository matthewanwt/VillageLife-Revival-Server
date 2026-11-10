# Village Life Revival Server — architecture redesign (alpha)

A **new, modular Python backend** for the community preservation project, based on the
user-provided Village Life backend (reported by the project owner as v2.11). The original playable backend **has not
been modified**. Its 28 source modules and 40 original test files are retained under
`legacy_reference/`, *without* private state, compiled outputs, the APK/XAPK or assets.

> **Important:** This is an **architecture and migration foundation**, **not yet a
> drop-in replacement for the playable 2.11 server**. The original game's RPCs,
> economy rules, world generation, buildings, family logic and much of multiplayer
> still need to be ported and validated. Unknown behaviour explicitly fails rather
> than silently inventing rewards, family members or scenarios.

## What works today

- Clean Python package with documented, tested service boundaries and optional HTTP transport.
- New SQLite repository using transactions, per-village revisions and idempotency receipts.
- Separate account and village identity; revocable, hashed API tokens for the new API.
- **Copy-only** legacy profile/save migration that preserves all unknown fields verbatim
  in a tagged `legacy.v0_2_6 (historical internal label; the uploaded source was v2.11)` payload, plus dry-run, checksums and conflict detection.
- Portable save export/import with SHA-256 integrity checks; imports create a **new** village.
- Deterministic timed-job readiness and offline catch-up, with **no unverified reward grants**.
- Consent-based new-API friendship persistence (not yet exposed to the original APK).
- Legacy XOR/zlib protocol encoding isolated behind an adapter.
- A loopback-only development HTTP API; not an original-client endpoint replacement.
- A set of new synthetic-fixture regression tests. Legacy tests are retained for future parity work.

## Why this repository is separate

The goal is portable logic and state, *not* preserving Windows/BlueStacks dependencies
in the core domain. Future original-APK compatibility, local-server launchers,
Godot/native clients and hosted multiplayer can each have distinct adapters using the
same gameplay services and persistence contracts.

## Setup on Windows

Using Python 3.11 or newer, inside a **copy or clone of this repository**:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m unittest discover -s tests -v
```

The implementation uses the Python standard library. Package installation requires
setuptools (a standard packaging tool).

Initialize a fresh database in your local user data directory:

```powershell
python -m villagelife init-db
python -m villagelife create-account --name "Development Tester"
# Use the account ID printed by the previous command:
python -m villagelife issue-token YOUR_ACCOUNT_ID
python -m villagelife create-village YOUR_ACCOUNT_ID
python -m villagelife serve --port 8765
```

The diagnostic endpoint is at `http://127.0.0.1:8765/health`.
Authenticated API requests use `Authorization: Bearer YOUR_TOKEN`.
The development village is an **empty fixture**, not a recreation of the original tutorial.

### Import saves from your current working version (non-destructive)

1. **Preserve your entire old project; do not delete or move it.**
2. Stop your old Village Life game/server and make a separate backup of
   `backend/private_state/` before taking a stable save snapshot.
3. Prefer running the import against that backup or a read-only copy.
4. Preview the import:

```powershell
python -m villagelife import-legacy "D:\VillageLife-Old\backend\private_state"
```

5. When happy with the preview, add `--apply`:

```powershell
python -m villagelife import-legacy "D:\VillageLife-Old\backend\private_state" --apply
```

**This copies data into the new SQLite database and never changes the original files.**
The imported save is protected as opaque until its fields have been mapped against
original-client behaviour. **Do not point the old launcher at the new server yet.**
Details: [`docs/SAVE_MIGRATION.md`](docs/SAVE_MIGRATION.md).

## Code map

```text
src/villagelife/
  core/           models, clocks, IDs, interfaces, validated original rules
  persistence/    SQLite repository, hashed tokens, social graph, import/export
  services/       areas, buildings, jobs, families, command dispatcher
  simulation/     optional background ticking (same logic as offline catch-up)
  protocol/       original wire codec and legacy RPC adapter boundary
  transport/      authenticated NEW API (loopback-only)
  cli.py          database, test accounts, backups, migration and local server
legacy_reference/
  backend/        untouched original Python source modules (reference ONLY)
  tests/          original tests; depend on generated game databases
  README.md       scope/limitations
  docs/           architecture and migration design notes
  tests/          runnable synthetic tests for the redesigned foundation
  tools/          audits and migration helpers
```

## For GitHub Desktop

Copy this ZIP's contents into the cloned **`VillageLife-Revival-Server`** repo,
review the file changes, run the test command, then commit and push. The `.gitignore`
is protective, but **inspect the staged file list** for secrets or private saves.
Do not copy your original `backend/private_state`, `analysis/private`, APK, OBB,
XAPK, backups or 55 GB experiments into Git.

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — dependency rules and adapters.
- [`docs/SYSTEM_COVERAGE.md`](docs/SYSTEM_COVERAGE.md) — mapping of every original module.
- [`docs/SAVE_MIGRATION.md`](docs/SAVE_MIGRATION.md) — copy-only import, identity and later schema conversion.
- [`docs/GAME_RULES.md`](docs/GAME_RULES.md) — provenance standard and missing game rules.
- [`docs/API.md`](docs/API.md) — new API and security boundaries.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — milestones to restore original-APK parity.
- [`docs/SECURITY.md`](docs/SECURITY.md) — privacy, hosting, licensing and distribution.

No redistribution rights to the original commercial game, client, graphics or music are implied.

## Current verification

See [`docs/DELIVERY_STATUS.md`](docs/DELIVERY_STATUS.md) for test results and
limitations. The new source includes `catalog/` read-only original-table access,
world-object identity and exact inventory helper services in addition to the
core modules listed above.

## Windows launcher, BlueStacks and EXE installer (separate integration)

The `windows/` directory contains a **source-only Windows compatibility update** prepared from the uploaded 2.11 tools, a dedicated `tools/platforms/bluestacks/` adapter, a WinForms launcher with support-bundle export, synthetic regression tests, and an Inno Setup project. It does **not** replace the redesigned backend with the legacy server and is **not yet a verified installer EXE**. See [`windows/README.md`](windows/README.md).

## Windows BlueStacks development test update

The `windows/` folder contains the version 2.11 launcher/compatibility update,
including separate-instance selection, local ADB binding, read-only Wi-Fi
network diagnostics, and **Export Missing Requests** for unimplemented
original-client RPCs. The compatible legacy code remains distinct from the
future modular `src/villagelife` implementation.

On Windows, a **separate test installer EXE** can be built from a clean 2.11
player kit using `windows/installer/Build-TestInstaller.ps1`, .NET 10 SDK and
Inno Setup 6. See [Windows installer instructions](windows/docs/INSTALLER.md).
A runnable Windows EXE is not included in this source ZIP; Windows compilation
and BlueStacks acceptance testing are still required. The user's working 2.11
folder and saves remain untouched by this source update.
