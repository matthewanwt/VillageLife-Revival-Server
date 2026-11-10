# Change summary: 2.11 isolated Windows test build source

Baseline: `VillageLife_Revival_Server_2.11_WiFi_Topology_Update.zip`.

## User-facing changes

- Added **Instance Manager** launcher button. It opens the official BlueStacks
  Multi-instance Manager GUI for creating a separate Pie64 instance. This is
  **guided** creation, not undocumented automatic VM manipulation.
- When several Pie64 instances exist, setup requires an explicit selection
  unless a previously saved ID is still valid. Stable instance IDs are saved;
  ADB ports are discovered and validated per launch, not hardcoded.
- Added **Export Missing Requests** launcher button. It creates a redacted ZIP
  summarising unsupported legacy RPCs and unknown routes. It never exports raw
  POST bodies, villagers, saves, authentication headers or network addresses.
- Extended the original 2.11 compatibility backend with a bounded,
  best-effort recorder. Unimplemented calls still return their original
  response/error semantics.
- Added `Build-TestInstaller.ps1` to build a single Windows installation EXE
  from a fresh, private-data-free stage. The test installer has a separate
  AppId and per-user directory to protect historical 2.11 installs.

## Network status

No firewall or VM isolation policy was added. VLTest1 (Pie64_4) has a route to
`10.0.2.2` and another to external IPv4 destinations via that gateway.
This is evidence of routing, **not** proof that egress succeeds or that a guest
is isolated. Existing fail-closed checks are preserved. Wi-Fi-on gameplay
remains an unresolved release blocker.

## Validation

- 14 redesigned-backend regression tests passed on Linux.
- 7 missing-request tests (including a live local HTTP 404/501 test) passed.
- 4 instance-manager selection and GUI-launch tests passed.
- The full Windows Python suite ran 80 tests: 13 fixture-dependent cases were
  blocked by an absent generated original-game SQLite DB. The other 67 passed.
- No Windows, .NET 10 WinForms, Inno Setup or real BlueStacks test was run in
  this environment. **The EXE itself was not compiled here.**

## Instructions

1. Preserve your working old 2.11 folder and commit the current repository.
2. Extract the full source ZIP into a separate folder, then copy its contents
   over your cloned repo. Review the diff and commit on a test branch.
3. On Windows, supply a clean extracted 2.11 *player kit* with bundled Python
   and .NET runtimes, install .NET 10 SDK + Inno Setup 6, and run:

   ```powershell
   .\windows\installer\Build-TestInstaller.ps1 -PlayerKitRoot "C:\Path\To\Clean-2.11-Kit"
   ```

4. If the build succeeds, the development installer appears at
   `windows/installer/output/VillageLife-TestSetup.exe`.
5. Do not distribute until local installer/network/gameplay tests pass.

See `INSTALLER.md`, `WINDOWS_TEST_CHECKLIST.md` and
`MISSING_REQUEST_REPORTS.md` for details.
