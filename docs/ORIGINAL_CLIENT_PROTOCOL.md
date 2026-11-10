# Original Village Life client compatibility (independent new backend)

This document distinguishes tested implementation from unverified behavior. Nothing in this project starts or imports the historical 2.11 server, its game modules, or its save handling code. Historical code and user-supplied definitions were examined as **reference material only**.

## Implemented and tested

- `/web/ClientService/Login` and `/web/ClientService/Process` accept the recovered original compressed/XOR-encoded wire format, retaining response envelope and call IDs. Login creates persistent, isolated player/village identities in the **new** SQLite database. Re-login rotates session credentials, so repeated client-generated call IDs after restarting do not cause false duplicate conflicts.
- Initial tutorial state, active-sequence changes, villager name edits, selected settings, and the original first-world bridge around checkpoint 217. Startup and area-1 content responses are reconstructed from the user-extracted authored game tables.
- New tutorial saves select the opening adult appearance/name from each role's authored starting variations. The choice is saved with a per-player SHA-256 counter generator, so reconnects and restarts do not reroll it. This currently uses a uniform choice because the authored rows expose no weights; the original game's exact selection distribution remains unverified.
- The original villager-collection summary read returns its compact collection map and acquired base-ID list from the saved world.
- Partial area definitions and state for Woodland (1), Riverside (2) and Mountain (3), including unlock gates and guarded villager transfer where all prerequisites are known.
- Limited gathering/crafting/farming task starts and harvests when the original authored reward is deterministic. Unrecovered randomness and cost/rule variants fail explicitly; reward claims are transactionally protected from duplicate execution.
- Read-only environment/manifest/resource endpoints from *local user-provided* APK/OBB + resource-offset inventory. No external resource fetching.
- Per-call 501 errors for unsupported gameplay, with anonymised missing-operation reporting. Malformed requests get errors rather than success-looking fake data.
- An optional XAPK preparation tool in `tools/prepare_original_client.py`: stream-extract local APK/OBB, patch known native endpoint strings, disable the optional Google Play Games integration present in this client build, and sign a local copy. Google achievements/leaderboards may be unavailable. Original archive remains unchanged. Signing is not a network-isolation mechanism.
- Original RPC outcomes are aggregated by service, response code, and response-object keys/types for diagnostics. Reports contain no request body, response values, call ID, session token, or player identifier, so a village-entry disconnect can be traced to an error or a malformed successful response without exporting a save.
- Two-player/account separation, session rotation, persistent saves, restart, replay rejection, source-preserving old-save import, original wire HTTP smoke. These are exercised by synthetic tests and user-supplied real definitions.

## Verified with actual private reference material (not shipped)

We ran a localhost HTTP sequence against the extracted original `game_tables.sqlite`: original-formatted login, tutorial state, checkpoint change, bridge to first normal world, startup info, first-area content and inventory response. A second login retained the player identity and rotated the session. An imported **copy** of a preserved 2.11 save answered login and startup without changing any original source file. Four known native library endpoint constants were located uniquely and patched in-memory in the separately supplied original Android APK.

These tests establish protocol and data-path behavior. They do **not** demonstrate that an actual BlueStacks/XAPK client can render a village, perform full gameplay, or connect safely with Wi-Fi on.

## Developer smoke test: private definitions, throwaway database

From the repo root, after `pip install -e .`:

```powershell
.\.venv\Scripts\python.exe tools\smoke_original_client.py --game-tables "C:\path\to\game_tables.sqlite"
```

Optionally include `--legacy-saves "C:\path\to\backup\private_state"` to test one-way import into the throwaway database while verifying the source JSON hashes are unchanged. This command produces no player IDs, save contents or private paths in its success output. The real save source may contain personal data: never attach it to public bug reports.

To start the original-protocol service manually for local testing, the following flags are available; **this is not authorisation to bypass the existing guest-network isolation checks**:

```powershell
.\.venv\Scripts\python.exe -m villagelife --db "$env:LOCALAPPDATA\VillageLifeRevivalNext\worlds.sqlite3" serve --port 80 --game-tables "C:\private\game_tables.sqlite" --xapk "C:\private\VillageLife.xapk" --obb "C:\private\main.obb" --inventory "C:\private\obb_tcf.inventory.csv"
```

Host port 80 is distinct from BlueStacks' dynamically selected ADB port. The original patched client currently uses `10.0.2.2:80`. The server binds to loopback, and does **not** in itself prevent the Android guest from accessing external networks.

## Behaviors not established

Building construction and autonomous production; full task reward/loot and timing formulas; all shop items/purchases; original quests/progression; full family/marriage/pregnancy/relationship actions; habitat assignments; all Riverside/Mountain rendering and gameplay; original community/friends network; complete original manifests/asset patch/signed installation with BlueStacks; account recovery and cross-device synchronization; verified guest egress isolation; finished single-file setup wizard/installer. See `REMAINING_GAMEPLAY.md`.

## Investigating a disconnect at village entry

After reproducing the disconnect, use **Advanced diagnostics** in the launcher. The exported missing-request report includes `call_outcomes`, aggregated by original RPC name, response code, request key/type shape, and response key/type shape. A `501` identifies an unported operation; `400` indicates a rejected request; a `200` with an unexpected response shape points to a response-contract mismatch. An empty outcome at the failure point suggests the guest did not reach the local server or the client closed before an RPC was decoded. The report includes JSON field names and types but never request/response values, save data, call IDs, session tokens, or player identifiers. Share the ZIP from `LocalAppData\\VillageLifeRevivalNext\\reports`.
