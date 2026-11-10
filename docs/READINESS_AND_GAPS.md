# Implementation ledger | 10 November 2026

This ledger separates implemented code from *real original-APK and Windows verification*. The supplied original 2.11 code was consulted as a **reference only**; it is neither included nor callable as a runtime fallback.

| Area | Evidence | Still unverified or missing |
|---|---|---|
| Original compressed/XOR wire protocol | `/web/ClientService/Login` and `/web/ClientService/Process` pass real localhost HTTP round trips | Full client call coverage and live Android execution |
| Original login/session | Separate account identities, session rotation and request replay tests pass | BlueStacks guest compatibility and in-game login |
| Tutorial and world start | Authored original data drives tutorial state, checkpoint 217 and initial village startup | Actual scene rendering, complete tutorial and all world rules |
| World/area requests | Initial-area projection, conditional Riverside/Mountain seeds, guarded movement | Full areas, progression and client-visible positioning |
| Gather/craft/farm jobs | Limited deterministic authored rules and transaction protection | Building production, all task types and reward variations |
| Original resources | Read-only manifest and OBB inventory-offset handler; local native endpoint patch constants verified in original APK copy | Signed APK launch and complete real OBB/manifest response validation |
| Old-format saves | One-way source-preserving import; copied preserved save read on new server | Semantic gameplay translation and save/reload in actual client |
| Persistence | SQLite transactions, backups, revision checks and explicit connection close | Windows 3.14 regression run, multi-PC stress/upgrade test |
| Multiple players | Separate device/login IDs, account-bound state and separate DB fixtures | Shared live multiplayer interactions and synchronization |
| BlueStacks selection | Exact-ID, name, port and installation-path validation; fail-closed on drift | On-Windows first-run wizard and fully targeted APK installation |
| Missing request reporting | Sanitised aggregate endpoint misses and original RPC response-code counts, with report export | Full coverage of client calls including unknown transport forms |
| Installer | Source/build stubs present, intentionally blocked by release gate | A complete, playable, permitted installer with XAPK and guided setup |
| Wi-Fi safety | Guest routing was inspected; outward route was present | Verified enforced guest isolation while Windows remains online |

**Coverage inventory:** see `ORIGINAL_OPERATION_COVERAGE.md`. It lists 101 historical operation names, 44 new dispatch paths (some partial) and 55 missing operations, excluding two original HTTP entrypoints from the operation count.

**Validation completed here:** 39 automated unit tests, independent HTTP API smoke test, original-format wire/login/tutorial/startup smoke using the supplied extracted definitions, copied preserved-save readback with unchanged source hashes, and native endpoint patching on an unchanged copy of the supplied original APK. No live Windows emulator access was available.

**Release gate:** not a playable game build and **not** a beta candidate. Both Windows installer entry scripts deliberately stop with `VL-INSTALLER-NOT-READY`; that is intentional until all real-client, save, setup and network acceptance tests pass.
