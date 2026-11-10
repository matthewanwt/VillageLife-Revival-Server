# Launcher integration status — 10 November 2026

## Implemented in this checkout

- The Windows launcher restores the normal **Play / Restart**, **Stop**, **Set Up Game**, **Connection**, **Save Backups**, **Logs**, and **Help** controls. Diagnostics are separate from the ordinary workflow.
- Setup requires explicit Pie64 selection and saves only the exact BlueStacks binding. It prepares a separate signed copy of a user-selected XAPK, verifies it did not modify the archive, installs that copy and its OBB into the bound instance, and retains all private files in `%LOCALAPPDATA%\VillageLifeRevivalNext`.
- Play starts only the new backend with `--game-tables`, `--xapk`, `--obb`, and `--inventory` on port 80, checks `/health`, validates the exact instance, waits for ADB, probes `10.0.2.2`, then requests the Village Life Android launch.
- Client preparation, installation, guest probe, and Android launch have explicit `VL-*` failures. No legacy Python modules or executables are imported, executed, or packaged as fallback.

## Still unverified / not release-ready

- Real-XAPK launch, tutorial, gameplay, save/reload, migration semantics, and all non-implemented original RPCs still require on-device evidence.
- The guest probe proves only guest-to-local-backend HTTP. It does **not** prove guest egress isolation, DNS/IPv6/UDP restrictions, or Wi-Fi-on safety. The launcher labels this condition explicitly; it must not be presented as a public release or a completed installer.
- `prepare-original-client` currently requires the development preparation tool to be included with the server build. The packaging pipeline must include that component before a distributable installer is unblocked.
