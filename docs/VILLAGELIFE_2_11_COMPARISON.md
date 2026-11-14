# Village Life Revival Server | Comparison with the 2.11 backend

**12 November 2026, Brisbane time**

The current working folder, `C:\Users\matti\Documents\Github\VillageLife-Revival-Server`, runs an independent Python backend for the original Android client. The main changes are transactional SQLite saves, a separate original-client compatibility layer, rebuilt Windows setup and launch tooling, and more detailed request diagnostics. The older backend still has broader gameplay coverage in areas such as family, relationships, and community. The current build has reached live gameplay, with confirmed crafting, decor, and shelter failures still being investigated or awaiting retest.

## Comparison baseline

The old side is the preserved 2.11 source in Git commit `1d2fee8`, under `legacy_reference/`, plus that commit's Windows tooling and changelog. The reference README identifies the backend modules as copies from the supplied `backend.zip`; the Windows changelog names `VillageLife_Revival_Server_2.11_WiFi_Topology_Update.zip` as its baseline. This compares source and documented behavior. The separately preserved live installation may have local changes beyond that snapshot.

The new side is the working tree based on `e95655a`, including modified and untracked source visible on 12 November. The comparison covers application source, tools and behavior. Generated binaries, private saves, and large asset extractions are outside the file-by-file comparison.

## Backend, protocol, and data

| Area | 2.11 reference | Current folder |
| --- | --- | --- |
| Server structure | `backend/server.py` and `session.py` coordinate HTTP, login, file-backed state, and the gameplay modules. | `src/villagelife/` separates transport, persistence, identity, platform integration, simulation, and rules. The original Android client's compatibility handlers live in `protocol/original_client/`. |
| Original client | Original login/process routes and compressed/XOR protocol, plus local asset and manifest serving. | Reimplemented `/web/ClientService/Login` and `/web/ClientService/Process`, per-call dispatch and replies, session binding, and local manifest/OBB reads. The running new server has no 2.11 runtime fallback. |
| Developer API | Original-client and diagnostic server flow with a hosted invitation option. | Separate developer API and CLI with account/village operations. A feature implemented there still needs a matching original-client RPC before the Android client can use it. |
| Saves | Device-derived profile filenames and paired tutorial/world JSON in `backend/private_state/`, with atomic file writes. | Accounts, villages, sessions and mutation receipts in SQLite. Replay handling protects selected actions from duplicate charges or rewards. Windows state defaults to `%LOCALAPPDATA%\VillageLifeRevivalNext`; the default DB is `worlds.sqlite3`. |
| Migration | Existing profiles and saves are the source material for migration. | Dry-run by default, explicit apply, repeat-import detection, conflict reporting, backup/export, and portable import. Old payloads and unknown fields are preserved. Full conversion into a playable migrated village remains unverified. |
| Identity and hosting | Device/profile lookup, hosted access and community tooling in the historical source. | New session/account identity and local save handling. Exact emulator instance binding and player identity are distinct. Old hosted invitation, relay, and original-client social parity remain open. |
| Game data | Legacy modules use original definitions and extracted resources through local analysis inputs. | The new runtime takes explicit paths to the user-supplied table DB, XAPK, OBB and inventory. Authored tables drive many gameplay rules. Original assets and private runtime data are local inputs. |

## Gameplay coverage

| System | Current changes and remaining differences from 2.11 |
| --- | --- |
| Tutorial, startup and areas | Rebuilt tutorial checkpoints, saved starting villager variations, tutorial completion state, authored Woodland startup/overlay, and initial area unlock/transfer paths. Tutorial strawberry visibility, bridge transitions, Riverside/Mountain, and reload still need live parity checks. |
| Work and construction | Rebuilt gathering, crafting, farming, construction and upgrade starts, harvest, resource requirements, and gem-curve instant completion. Several task/reward variants and recurring building production remain incomplete. The latest crafting patch accepts the native coordinate-only request and resolves a recipe-compatible workshop. |
| Buildings and placement | Foundation placement/removal, construction results, and some building removal are routed. Decor placement persists supported single-currency/free purchases and accepts negative X within bounds. The live decor 400 still needs an item-specific retest. Decor deletion, dual-price rules, and broader position/placement parity remain open. |
| Fire, shelter and beds | Fire lighting/oil, bed assignment and emptying, and shelter happiness/timers have new handlers. Authored beds are preserved; generated slots are restricted to known built shelter capacities. The latest live bed assignment still failed with an unknown bed ID. |
| Fun, progression and economy | Added fun activity eligibility, energy/wear/XP and persisted weighted rewards for supported activity tables; table-driven XP, level/population changes and wheel rewards; basic buying, selling and inventory support. Earlier fun 501s need a live retest. The old fortune/gacha, charms, learning, starter tools and broader shop paths still need parity work. |
| Wants and quests | Food/water generation and consumption, selected quest progress/completion, and several want routes now exist. Several want handlers preserve current state while the original event-selection rules remain pending. Commercial bundle offers are recorded as ignored. |
| Villagers, family and community | Naming, local family-history reads, limited skills/collection reads, and guarded movement are available. Old code includes broader relationship, pregnancy, birth, wedding, community, social-request and interactive paths. Most of that behavior still needs implementation or verification in the new Android-client path. |
| Coverage counts | The legacy-name audit records 101 names including two HTTP entrypoints, with 65 RPC dispatch paths and 34 without a dispatch path. The audit is a snapshot, and a routed operation can still be partial. The separate native inventory found 100 exact client RPC strings and should be used alongside runtime captures. |

## Windows, BlueStacks and packaging

| Area | What changed |
| --- | --- |
| Launcher and startup | The current WinForms launcher starts the independent backend, checks host health, validates the selected Pie64 instance, waits for ADB, probes the guest-to-host HTTP route, and opens Village Life. The old workflow used legacy launcher helpers and legacy server packaging. Exact instance selection and dynamic ADB-port checks already existed in the old Windows test tooling. |
| Instance identity | Current setup binds the exact internal instance ID and checks its saved fingerprint/configuration. For the 12 November run, the selected instance was `Pie64_6`. The patched client targets `10.0.2.2:80` in the standard setup. Guided instance creation and alternate configurations still need broader testing. |
| APK, OBB and signing | Setup prepares and signs a local copy of the supplied Android APK, extracts the OBB, and installs into the selected instance. The prepared files and local signing identity live under the new local state directory. TestMode setup expects the full JDK under `signing-tools/jdk`. Setting `JAVA_HOME` alone previously produced `VL-SIGNER-MISSING`. |
| Desktop TestMode | The current iterative workflow bundles the backend with PyInstaller, publishes the launcher with .NET, and runs `StartVillageLife/VillageLifeLauncher.exe` from the private TestMode folder. The existing `tools/Build-PrivateTest.ps1` creates a fresh folder but does not stage the full JDK required by current setup. The recent PowerShell rebuild command handles that JDK layout. |
| Private installer | `Build-TestInstaller.ps1` stages the independent backend, launcher, supplied XAPK, game table/inventory files and JDK into a private reliability-test installer. It extracts the OBB on first setup. The installer handoff was payload-tested in a temporary folder and remains unsigned. Production distribution is still gated by live acceptance. |
| Networking | Old tooling already included network topology diagnostics and hosted/offline helpers. Current diagnostics can probe local guest HTTP on the launcher port and report the result separately from external reachability. DNS, IPv4/IPv6 TCP and UDP isolation remain unverified. |

## Diagnostics, reverse engineering and verification

- **Diagnostics** moved from a bounded old missing-route recorder to SQLite aggregates of service, status, safe request/response shapes, failure category and latest occurrence. Advanced Diagnostics exports a ZIP without raw values, save contents or tokens. Counts can span multiple runs. Pair the export with the exact action, time and build.
- **Reverse engineering** now has a repeatable Ghidra ARM32 route/wrapper inventory, JADX inspection of the Android wrapper, and indexes of recovered game tables and runtime request shapes. These sources help establish client contracts and authored rules. Server-only behavior still needs evidence.
- **Latest live evidence** includes successful startup/area, gathering, instant completion, harvest, and consumption responses. It also includes four bed-assignment 400s, three crafting 400s, one decor 400, and five unresolved 501 markers across the accumulated report. The full error table and timestamps are in [GAMEPLAY_TEST_2026-11-12.md](GAMEPLAY_TEST_2026-11-12.md).
- **Latest source verification** passed the launcher compilation, synthetic diagnostics smoke check, and 13 focused tests. Full suite results were 43 passed and eight loopback connection errors in the restricted Windows session. Those checks establish source behavior for covered cases. A live retest of the latest build is still required.
- **Checkout state** includes local changes and untracked gameplay modules, tests and evidence files. A fresh checkout of `e95655a` alone will omit part of the behavior described here.

## Retest order

1. Rebuild the existing Desktop TestMode folder with both current binaries and its signing JDK. Open it through the launcher and capture Advanced Diagnostics while the game runs.
2. Retry the same crafting recipe, then harvest and reload to check persisted inventory and task state.
3. Retry the same decor item and location. Record its name and any lock indication. Verify placement, balance, and reload.
4. Try one slot in the constructed Basic Shelter. Record the shelter and slot if the server rejects the bed ID.
5. Retest fun activities, emptying beds, and tutorial completion. Then test a copied legacy save, a fresh setup, and the wider progression and networking paths.

## Source pointers

- Historical baseline in Git: `git show 1d2fee8:legacy_reference/README.md`, `git show 1d2fee8:docs/SYSTEM_COVERAGE.md`, and `git show 1d2fee8:windows/docs/CHANGELOG_TEST_BUILD.md`.
- Current technical references: [original client protocol](ORIGINAL_CLIENT_PROTOCOL.md), [operation coverage](ORIGINAL_OPERATION_COVERAGE.md), [native analysis](NATIVE_REVERSE_ENGINEERING.md), [save migration](SAVE_MIGRATION.md), and [remaining gameplay](REMAINING_GAMEPLAY.md).
