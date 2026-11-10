# Legacy save import into the NEW backend

This tool reads the **old file format**; it does not run or import any old server Python modules. It is designed to accept profile files named as 64-hex `.json` and their matching `.tutorial.json` saves from the historical `backend/private_state/` directory. The importer treats the payload as opaque because precise 2.11 gameplay field semantics have not all been proven.

## Safest workflow

1. Close the old game/server. Back up your original save directory; **never import the live, actively changing files**.
2. Copy the backed-up `private_state` folder to a temporary location outside Git.
3. Run a dry run against the new empty database:

   ```powershell
   .\.venv\Scripts\python.exe -m villagelife import-legacy "C:\VL-TestCopies\private_state"
   ```

4. Check that every player you expect has a profile and a matching save (`has_save: true`). Missing saves are reported, not invented. If expected entries are absent, stop and inspect your backup.
5. Create a second backup of your new database (if it contains anything you want to keep), then import a copy:

   ```powershell
   .\.venv\Scripts\python.exe -m villagelife import-legacy "C:\VL-TestCopies\private_state" --apply
   ```

6. Confirm that separate source IDs produced separate account/village IDs, that the reported counts match, and that repeat imports report `already-imported`. If the original source bytes change, the importer raises a conflict status rather than silently overwriting.
7. Export/import a sample using `villagelife export` / `import-portable` into a **separate test account**. Check original object IDs, family trees, unknown fields, inventory and area fields remain structurally identical.

## What is NOT done

- No game-state translation to native `native.v1`. Imported data is stored as `legacy.profile+tutorial.v1` and is **readable/exportable but not yet playable** through the new action dispatcher.
- No cross-device auto-sync, conflict merging or account takeover mechanism.
- No overwriting an existing save or silently switching a BlueStacks instance.
- No storage of plain old device IDs in public diagnostics; the imported private payload does contain the old profile fields and must be protected.

**For current 2.11 saves, test on copied, sanitised examples before any community migration.** The tests use fictional profiles and cannot certify the correctness of every original 2.11 field or all previously released formats.
