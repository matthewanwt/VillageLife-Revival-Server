# Delivery and test status (9 November 2026)

## What this ZIP is

A non-destructive **architecture redesign alpha** based on the user's uploaded
`backend.zip`, intended for the new `VillageLife-Revival-Server` GitHub repo.

- 28 old Python source modules preserved as **reference only**, unchanged.
- 40 old test source files retained for later original-client regression work.
- New object-oriented services, ports, versioned SQLite storage, import/export,
  account authentication, deterministic job timing and new local HTTP API.
- Comprehensive docs, source inventory, security guidance, and a clean ignore file.
- No original APK, XAPK, OBB, original graphics, private data or player saves.

## Test execution

Command:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

**14 synthetic-fixture tests passed** on Python in the analysis container, covering
transaction rollback, duplicate action replay, optimistic revision conflicts,
copy-only legacy migration, preservation of unknown fields, import conflict
protection, consistent database backup, portable saves, token-authenticated
new API, ownership restrictions, unknown-rule failures, world/job progression,
friend acceptance, resource catalog reads and world/inventory invariants.

This does **not** mean the old game is playable through the new API. Actual
BlueStacks/APK integration and legacy test suite were **not run**.

## Still missing before replacing original 0.2.6

- Original APK HTTP routes, login/process data and asset serving parity.
- Original save schema conversion and account/device linking.
- Complete original task/building, farming, family, quests and economy rules.
- Full Riverside and Mountain scenarios and client-side transitions.
- Player-to-player visits and multiplayer domain transactions.
- Launcher, Android packaging and server lifecycle integration.
- Community load tests and compatibility verification against the old game.

The old 55 GB folder should remain preserved and operational until these gates
pass. Do not migrate original game clients to this alpha API yet.
