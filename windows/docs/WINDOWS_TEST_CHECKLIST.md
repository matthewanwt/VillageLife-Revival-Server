# Windows development-only acceptance checklist (2.11)

Use **a new test instance**, **a backed-up disposable save** and a non-production
Windows account. Do not alter the original v2.11 player's folder.

1. Compile test installer (`Build-TestInstaller.ps1`) and confirm exactly one
   `VillageLife-TestSetup.exe`. Verify it contains no APK/XAPK/OBB or saves.
2. Install to the separate `VillageLifeRevivalTest` location. Confirm it does
   not override or remove the old 2.11 installation.
3. Open **Instance Manager**, create a dedicated Pie64 using BlueStacks GUI,
   enable ADB, close VM and select this exact VM in **Set Up Game**.
4. With `Pie64` and `Pie64_4` existing, confirm selection never guesses;
   renamed instance is still matched by its internal ID. A changed ADB port
   must produce a clear validation error rather than targeting another VM.
5. Run setup using a personally supplied, verified original XAPK. Check that
   user files are generated in the test install only. Do not upload the archive.
6. With backend running, confirm `10.0.2.2:80` reaches the local health check.
   If port 80 is occupied, confirm an actionable error; no port reassignment.
7. With Wi-Fi enabled, run external guest connectivity tests and isolate the
   actual VM traffic path. **Do not declare the instance safe on the basis of
   blocked probes alone.** Never bypass `VL-NET-EGRESS` to test gameplay.
8. Only on a network setup with a verified enforceable restriction, test
   launch, loading a village, saving, stopping, restarting and exporting a save.
9. Trigger a documented *unimplemented* service on a disposable test village;
   confirm `Export Missing Requests` produces a ZIP with an operation name,
   status code and no player data. An unimplemented response can still cause a
   client-side connection error, which this feature does not fix.
10. Restart Windows and the emulator, verify network policy persistence and
    repeat startup. Test Unicode Windows profile paths, different BlueStacks
    install paths and slow ADB startup on a second PC.
11. Uninstall the development test version and verify the original 2.11
    installation and its saves are intact. Confirm no shared BlueStacks
    instances were deleted or modified.

**Blocking release issue:** Wi-Fi-on guest isolation remains unverified. The
installer build is therefore an isolated developer artifact, not a beta build
for general distribution.
