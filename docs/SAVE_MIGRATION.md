# Non-destructive save migration

## What the uploaded 0.2.6 source actually uses

`legacy_reference/backend/session.py` stores a hashed-device profile as
`backend/private_state/<sha256>.json`; gameplay data is stored in the paired
`<sha256>.tutorial.json`. Legacy social and invitation data are separate.
Original files may contain player information and are not included in this repo.

## Stage A: Verified copy-only ingestion — implemented

`LegacySaveImporter` searches for these pairs, parses JSON, stores an SHA-256
of both original byte streams, and creates:

- a new stable account ID and a new village ID;
- one record tagged `legacy.v0_2_6` containing the original profile and save;
- a legacy-key mapping and content digests to prevent unintended duplicate
  imports or overwriting changed source files.

All unknown keys, entity IDs, relationships and future version fields are kept.
History JSONL and invitation/access credentials are **not** imported yet.
This is a **preservation import**, not conversion into native game logic.

The CLI uses **dry run by default**. `--apply` copies data into the new database
and NEVER alters the original saves or changes the 55 GB folder.

## Stage B: Schema mapping — NOT implemented

Must validate old and new fields, including:

- account/user ID versus device/session ID;
- stable villager and family IDs, relationships and parent/child references;
- world entities across Woodland, Riverside and Mountain;
- buildings, crafting, timed jobs, quests, inventories, unlocked areas;
- exact original time units and derived countdowns;
- resource ID catalog version and original scenario content hash;
- online friendships, invitation codes and hosted player accounts.

Run round-trip tests on anonymised synthetic examples, *then* real saves copied
into private test storage. Implement an explicit `legacy.v0_2_6 → native.v1`
conversion function with rollback evidence and a complete migration report.
Until then, the engine rejects gameplay actions on opaque imported saves.

## Portability and multi-device policy

Portable archives include the tagged format, schema version, revision, state,
and checksum. Import always creates a **new village ID**, never silently
replaces the currently hosted village. This is intentional: the exact offline-
versus-hosted save-sync policy and conflict rules are not yet agreed.

An eventual sync engine must handle revision conflicts, server-owned event IDs,
duplicate work collection, concurrent visits, mutually linked marriages and
family relations. Never use 'last write wins' on shared game-state changes.

## Safe commands

```powershell
python -m villagelife import-legacy "D:\Archive\backend\private_state"
python -m villagelife import-legacy "D:\Archive\backend\private_state" --apply
python -m villagelife list-villages ACCOUNT_ID
python -m villagelife export VILLAGE_ID "D:\Backups\village.vl-save.zip"
python -m villagelife import-portable NEW_OWNER_ACCOUNT_ID "D:\Backups\village.vl-save.zip"
python -m villagelife backup-db "D:\Backups\worlds-before-upgrade.sqlite3"
```

Exported saves can contain private user data; back them up securely and don't
commit them. Stop the old game or take a stable snapshot before importing so the
source doesn't change midway.
