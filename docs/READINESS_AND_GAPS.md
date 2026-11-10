# Implementation ledger | 2026-11-10

This ledger distinguishes **code implemented**, **automated checks run**, and **Windows/gameplay behaviour not yet verified**.

| Area | Status | Evidence or remaining work |
|---|---|---|
| Legacy 2.11 backend removed | Done in this ZIP | No `legacy_reference`, `backend/server.py`, or code path launching historical backend |
| Windows SQLite handle cleanup | Fixed and tested on Linux | Backup target uses explicit `closing()`, catalogue handle uses context manager, test fixture commits before close; **must rerun on Windows** |
| Transactional native saves | Implemented | Revision checks, atomic mutation, idempotency receipts, consistent backups |
| Old-save import | Opaque one-way import implemented | Dry-run, no overwrite on conflicting source, synthetic two-player/multi-area tests; field-by-field 2.11 gameplay verification remains |
| Unique BlueStacks instance choice | Implemented in new manager and tests | Exact ID, no fallback, detect name/port/install change, only selected VM must be healthy; actual Windows integration pending |
| Dedicated BlueStacks VM creation | Guided GUI only | Fully automatic creation uses undocumented mechanisms; not implemented |
| ADB test | Implemented in adapter | Explicit `-s 127.0.0.1:PORT`; Windows execution pending |
| Missing-request recorder/export | Implemented for new HTTP API | 404 and 501 aggregation, sanitised export. Does not decode unimplemented binary RPC actions |
| New backend Windows manager | Source implemented | Can manage API, select instance, diagnostic, migration dry-run. C# Windows compile and UI acceptance **not run here** |
| One-file installer | Inno Setup script + Windows build automation | Must compile on Windows with PyInstaller, .NET SDK and Inno Setup, then test clean installation |
| Original client login & process binary RPC | **NOT implemented** | Must be independently reimplemented and tested against original client behaviour; legacy server not bundled or callable |
| Building production | **NOT implemented** | Rules and background event semantics still to be verified |
| Riverside / Mountain complete gameplay | **NOT implemented** | Rules, travel, loading, persistence and client presentation tests outstanding |
| Full social/multiplayer | **NOT implemented** | Identity/saves foundation exists; consent-based friendship engine only partial |
| Wi-Fi-on isolation | **NOT verified** | Need actual egress policy at BlueStacks/VM boundary, not a routing-table assumption |
| Save migration ready for real users | **NOT verified** | Only synthetic migrated data tested, no confirmed end-to-end gameplay parity |

**Release classification:** engineering alpha for backend/installer smoke tests. Not a game update or community beta.

## Recommended Windows acceptance sequence

1. Run `python -m unittest discover -s tests -v` under the user's Python 3.14 and check for no WinError 32.
2. Verify PyInstaller and .NET build. Inspect stage and EXE using `tools/release_audit.py`. No original/game or save data may be present.
3. Install test manager in its **new**, separate folder. Check it starts/stops **only** `VillageLifeServer.exe` and `/health` returns JSON.
4. Select `VLTest1` and verify it binds `Pie64_4`, current port 5595. Rename temporarily only if prepared for it and check it refuses reuse until explicit rebind; never edit BlueStacks VM files to force this.
5. Stop/disable the selected VM and confirm no fallback to `Pie64` port 5555. Restore normal VM state manually.
6. Use copied, synthetic or anonymised saves, dry-run and then opt-in import. Compare pre/post SHA-256 on source files, player account counts, exported payload and ID preservation.
7. Re-run with two independent villages/accounts and test that one player's actions or files cannot alter the other's state.
8. Only after completing original binary RPC and network isolation can real gameplay, Wi-Fi-on player testing or public release be considered.
