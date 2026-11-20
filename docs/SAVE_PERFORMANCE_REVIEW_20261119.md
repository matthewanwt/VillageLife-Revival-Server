# Save performance review — 19 November 2026

Status: first source changes implemented; no community installer published in this pass.

## Findings

The current payload is updated in place, rather than appending an entire village
for every action. However, SQL replay receipts accumulate response snapshots, and
several gameplay history collections inside the payload accumulate independently.
Every mutation parses, validates and serializes the complete payload. Consequently,
history growth makes subsequent mutations progressively more expensive.

The tested village database was 8,318,976 bytes, with one village, 721 SQL replay
receipts, a 965,620-byte payload and 5,642,239 characters of stored receipt responses.
Large internal sections included work history, consumption history and completed
quests. Raising the import/archive size limit did not optimize these structures.
Database file size alone does not measure the live world: SQLite free pages, replay
responses and extra villages also contribute. Backup files consume separate disk
space and are not loaded as additional world history by the mutation path.

## Changes

- New food/water consumption receipts omit the two inventory snapshots which
  their replay code already replaces with current inventory. Login compacts those
  same fields in existing consumption receipts. IDs, completion times, reward
  protection, relationships, current inventory and unknown fields remain intact.
- When a login rotates a session token, discard only RPC response bodies belonging
  to that exact invalidated token, retaining their keys and request digests. A call
  authenticated just before rotation could still be in flight: these tombstones
  prevent it from applying the same reward twice. This includes repeated login to an explicitly
  selected village within the same running server. Active-session retries,
  migrations, other devices and gameplay histories remain intact.
- If serialized payload is unchanged, update revision/time and record the response
  without assigning the large payload column again. All commits remain atomic,
  WAL-backed and synchronous=FULL. No delayed autosave window is introduced.
- Added `tools/audit_save_performance.py DATABASE`, a read-only, consistent-view
  audit reporting sizes, counts, fixed-allowlist section sizes and serialization
  timings. It exports no village identifiers, device hashes, names or save values.

## Measurements

Local measurements are illustrative, not community-device frame rates or full
HTTP response timings. Serialization timing includes two encodes, one parse and
validation; it excludes game rules and storage I/O. Three samples per payload.

| Input | Payload before | Payload after | Processing before | Processing after |
| --- | ---: | ---: | ---: | ---: |
| Copy of existing test village | 965,620 B | 717,850 B | 50.48 ms | 37.23 ms |
| Synthetic 5,000-consumption history | 24,524,639 B | 4,054,639 B | 1,512.94 ms | 250.43 ms |

For an unchanged 1 MB synthetic village, the revised mutation generated 12,392 B
of WAL, including replay-receipt bookkeeping. Explicitly assigning the unchanged
payload as before generated 1,017,672 B, even without that bookkeeping. A held
connection and checkpoint between operations isolated each WAL measurement.

## Validation and remaining work

Regression checks cover consumption replay after upgrading old-shaped records,
preservation of unknown fields and inventory, active-session replay, exact-token
cleanup, explicit village login, unchanged-payload updates and read-only audit.
The full 126-test suite passed after the final source changes.

This is not a complete lag fix. Work/quest history and other internal receipt maps
still grow and need a versioned history-storage design. Old SQL receipts from
sessions abandoned before this change are not globally swept: some selected-village
sessions live only in memory, so a database-only token scan cannot safely identify
every active session. A server restart also loses the previous in-memory selected
token. Do not indiscriminately delete receipts or villagers to shrink a save.

Next pass:

1. Reproduce with an affected long-running community save on a separate copy.
2. Measure request time split between rules, JSON handling, lock wait and commit;
   distinguish backend delays from emulator rendering/audio and dense-world costs.
3. Move completed-action response history out of the frequently rewritten village
   payload, preserving cross-session duplicate-reward protection and old imports.
4. Define bounded retention only where replay safety is demonstrable, then test
   repeated harvesting, purchases, quests, weddings and save/reopen cycles.
5. Offer backed-up offline compaction if physical database files have large free
   page counts. Deleting rows makes pages reusable but does not itself shrink the
   file. Avoid VACUUM or whole-database backups on individual gameplay actions.
6. Verify shutdown/power-loss durability and package a private gameplay retest
   before any community release. Existing published installers are unchanged.

Manual retest for a candidate build: feed/drink, repeat a collection click, change
areas, close/reopen and verify quantities, gems, villagers and current tasks.
