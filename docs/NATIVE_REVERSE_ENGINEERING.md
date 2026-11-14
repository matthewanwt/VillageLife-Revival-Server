# Native client reverse-engineering inventory

The supplied Android package includes a native `libpdandroid.so` with the
game's request wrappers and much of its client-side game logic. Ghidra's
headless analyzer identified it as 32-bit ARM and exported string-to-function
references. The extracted game tables provide authored content and numeric
rules. These are complementary evidence sources: the native routines show
what the client sends and expects; they do not reveal the unavailable server's
implementation by themselves.

## Current inventory

- **117** exact service/operation route strings were identified in the native
  library: **100 `Client...` RPC operations**, two `ClientService` transport
  endpoints (login/process), and 15 user/social platform routes.
- **130** distinct route-to-function pairs map to **129** native functions.
  Of those, **111** pairs are `Script_*_Server` request wrappers (110
  functions); **83** of those have additional request or format strings
  referenced by the wrapper. These strings are useful field clues, not a
  complete JSON schema.
- **37** of the 100 exact client RPC route names currently appear literally in
  the new backend's `original_client` source. The other **63** need an explicit
  compatibility decision (implement, safely ignore, or reject with evidence).
  The two transport endpoints are handled outside RPC dispatch.
- The existing [`ORIGINAL_OPERATION_COVERAGE.md`](ORIGINAL_OPERATION_COVERAGE.md)
  counts operations named in the historical Python modules. Its 101-name
  baseline and this 100-route native RPC baseline are different inventories;
  neither count should be treated as the total game API by itself.
- The native strings are not a complete operation universe: dynamically
  assembled endpoints, library calls, and data-driven behavior can add
  operations or variants. The packaged tables contain 131 tables and 50,601
  rows, so rule discovery must inspect data as well as route strings.
- [`GAME_TABLE_INVENTORY.csv`](GAME_TABLE_INVENTORY.csv) indexes all 131 tables
  by row count and field names, without copying the original table contents.
  Generate it from a local parsed table database with
  `tools/reverse_engineering/build_game_table_inventory.py`.

JADX decompiled the embedded APK's 6,864 DEX classes into 8,529 Java source
files (with three decompilation errors). The app entry point is a thin Android
activity extending Playdemic's `PDMainActivity`; the request and game logic of
interest is primarily in the native library and packaged scenario/table data,
not the small app-specific Java wrapper.

The full per-operation mapping is in
[`NATIVE_CLIENT_OPERATION_INVENTORY.csv`](NATIVE_CLIENT_OPERATION_INVENTORY.csv).
The CSV is generated from local Ghidra exports with
`tools/reverse_engineering/build_native_operation_inventory.py`; private APK,
DEX, native library, and extracted asset files stay outside the repository.

The latest available `missing-requests (10).json` capture adds runtime
evidence: it contains 120 outcome aggregates across 52 RPC names, representing
684 calls. Its value-free, per-operation request/response shapes are in
[`LATEST_CAPTURE_OPERATION_SUMMARY.csv`](LATEST_CAPTURE_OPERATION_SUMMARY.csv).
It has four
still-missing records: `ClientUserBundleService/CreateUserBundle` (501, twice),
`ClientVillager/Consume` (501, twice), `ClientUser/CompleteTutorial` (501),
and `ClientVillagerService/GetVillagerRelations` (501). Those four routes have
dispatch code in the current checkout, so their capture failures indicate
unsupported request/state variants or a capture from an earlier build; the
sanitized diagnostic does not include the values needed to decide which.
Calls to `ClientTaskService/StartBuildingTask` also include 10 HTTP-style 400
outcomes and six 501 outcomes, with only three successes. At least some 400
building failures are labeled `task_material_requirement`. Preserve those as
separate validation and missing-rule work; the request shape alone cannot
identify the cause. `ClientTaskService/HarvestTask` has two 400 outcomes and
two `InstantCompleteTaskCurve` calls are 501. `GetAreaContent` succeeded 20
times with world entities in this capture, which appears to be the post-
tutorial Woodland scene; it does not establish how the tutorial's scenario-1,
area-0 Strawberry entity was loaded.

Three reported 501 operations—`CompleteTutorial`, `CreateUserBundle`, and
`GetVillagerRelations`—have branches in the current source; the captured shapes
do not contain enough request values or save state to explain their failures.
`Consume` is explicitly limited to known food/water/material interactions and
can still reject other consumption categories. Before changing these rules,
confirm the running backend build matches the working tree and preserve the
rejected call's values in a locally protected diagnostic if available.

## What the evidence says about the recent gameplay reports

The authored FTUE table has an explicit Strawberry Bush (`material_source`
ID 7), which produces material type 107 using Gather Strawberries task 14.
Tutorial sequence 142 enables the `Strawberries` entity; sequence 145 targets
it; sequence 150 associates it with the food work area. The tutorial scenario
contains the bush at `(2950, 3550)`, but its packaged `position.areaId` is **0**.
The normal Woodland scenario's authored entities use area ID **1**. Therefore
an area filter that treats the tutorial entity as normal-area content can drop
it. The next live diagnostic should establish whether the game asks the server
for tutorial area content or whether this entity is expected to be loaded
solely from local scenario data; that distinction determines the correct
fix.

Starting adult variants are authored in `villager_starting_variation` (four
Steve and four Jill records with differing names/genetics/equipment), and the
backend's new-tutorial path selects and persists one variant for each. This
means a blonde-only result is evidence to inspect the actual saved
`variationId`/`genetics` and the `GetUserHash` payload on the affected account;
the source data does not prescribe blonde as the only appearance. Random
selection is not re-applied to an existing save.

The `user_level` table has per-level XP thresholds, population caps, and
villager XP capacities. The server should derive each level transition from
that row and return/persist all affected fields together. Native function
references also show explicit `WheelOfFortuneTypeID` and `IsPaid` fields in
level-up calls, so the level-up UI path must be captured alongside the table
rules.

## Suggested implementation order

1. Keep expanding the request/response inventory from the native wrappers and
   correlate it with consented runtime captures. For each call, record the
   request, response keys, state changes, and replay behavior.
2. Reconstruct common rules from tables first: task costs/timers/rewards,
   level progression, wants, buildings, resources, recipes, and authored
   scenes. Treat each table as data, with small domain services enforcing
   invariants.
3. Implement grouped operations as cohesive services (world/buildings,
   villagers/family, task/work, progression/economy, social). Keep unknown
   cases explicit rather than returning fabricated success.
4. Use the old backend as a behavioral reference only where its behavior can
   be checked against the APK, tables, or observed game traffic. Record each
   inference and confidence level; do not copy assumptions as if they were
   original-server facts.
5. Re-run the same save through transitions and reloads after each change.
   Compare game-visible state and diagnostics, especially tutorial completion,
   area content, building placement, level capacity, naming, and character
   editing.

## Limits

No server binary or source is present in the supplied package. Client code and
tables can establish client protocol and authored rules, but server-only
validation, hidden event selection, anti-cheat behavior, and live response
variants require runtime observations or independent evidence. The native
operation inventory is a high-coverage starting point, not proof that every
possible request has been enumerated.

