# Development handoff report | Independent original-client compatibility | 10 November 2026

## Source status

- New, standalone `src/villagelife` backend. The historical 2.11 `backend/` and `legacy_reference/` code are absent from the output and cannot be used as runtime fallbacks.
- Transactional SQLite accounts, saves, session binding and one-way non-destructive legacy import.
- Original compressed/XOR transport, original login and per-call process envelope, authentication and session rotation.
- Original tutorial checkpoints, authored bridge into initial normal village, initial startup and area content, guarded initial Riverside/Mountain operations, limited deterministic source-derived work rules.
- Optional local original-resource manifest/OBB read APIs and source-XAPK endpoint preparation helper; supplied original game bytes remain outside the output.
- Strict BlueStacks instance ID selection, port validation and missing-request diagnostics. Network report is evidence only, not a network firewall.
- No finished Windows game installer; both Inno Setup build scripts are intentionally gated until the requested end-to-end release is possible.

## Verification performed

- **39 Python unit tests** in the new backend: passed in Linux container.
- New API localhost HTTP smoke: passed on throwaway database.
- Original-client-format wire/login/checkpoint/startup/initial-area HTTP smoke using actual extracted original game definitions: passed.
- One-way import of a copied preserved old-format save: new backend login, tutorial/startup/area-content response, original player ID continuity and source SHA-256 preservation: passed.
- Local original APK native library: four known endpoint constants patched in memory, with unchanged library length; original APK unchanged. Signed Android install was **not** verified.

## Missing before a complete installer is honestly possible

- Of 101 named historical operations, 55 lack new dispatch paths and 12 of the 44 existing dispatches are known to be partial. See `ORIGINAL_OPERATION_COVERAGE.md`.
- Construction and building production, full quests/farming and family/social/marriage mechanics and Riverside/Mountain game parity remain incomplete.
- No original-XAPK login/gameplay/save/reload acceptance performed on a real BlueStacks Windows VM.
- No guided BlueStacks instance creation, signed APK/OBB targeting or self-contained playable setup proven on Windows.
- No tested guest Wi-Fi-on external egress restriction; an IPv4 route towards the internet exists on the observed VLTest1.
- Cross-machine, two-active-instance save transitions, real live 2.11 migration semantics, updates and uninstall preservation still require live test.

**Do not distribute this source as a playable game release or copy the private game definitions/XAPK into a public repository.** Preserve the working 2.11 installation untouched. This source ZIP is an engineering handoff to finish and validate the new backend.
