# Handoff for Codex or future Work sessions

## Immediate aim

Port original game behaviour into the new architecture while preserving all
current data and keeping original-client compatibility in a separate adapter.
Do not refactor by guessing: migrate one verified service at a time.

## Where the reference lives

`legacy_reference/backend/` contains 28 original source modules. Read
`docs/SYSTEM_COVERAGE.md` for the full mapping and
`docs/legacy_function_inventory.csv` for function/class locations.
40 original tests are under `legacy_reference/tests/` but require old
private game-table/asset inputs; they are not automatically run.

## Next implementation sequence

1. Create a read-only `GameDefinitionCatalog` port for original game tables
   supplied outside Git. Verify hashes and table schema.
2. Port original `/web/ClientService/Login` and `/web/ClientService/Process`
   through a `LegacyRpcHandler`, preserving the codec and error behaviour.
3. Integrate the legacy save conversion with the original authenticated
   identity and stable villager IDs. Do not rewrite opaque imported saves.
4. Port world/area creation and scenario hydration for all three original areas.
5. Port tasks/buildings with input deduction, work timing, reward claim,
   idempotency and offline progression. Verify passive vs manually-started work.
6. Port families/lifecycle/marriage and reciprocal relationship validation.
7. Add friend visits, hosted session security and portable account migrations.

## Required regression cases

- Exact client payload shapes and compressed response byte conventions.
- New save, login, reconnect, save/restart, historical save import.
- Task start, timeout, ready, claim, duplicate claim, restart, offline catch-up.
- Riverside and Mountain unlock/visit/travel/move, return home, reload.
- Villager transfer without broken beds, tasks or family tree.
- Hosted social requests with authorisation and cross-player consistency.
- Missing resource and corrupted save behaviour, with no silent data loss.

## Coding standard

- Typed, documented Python 3.11+ modules with small classes and service ports.
- No global mutable game state. Use DB transactions and revision checks.
- Keep source evidence comments near recovered game rules, not unfounded guesses.
- Never include personal state, historical logs, binary game data or tokens.
- New API and legacy APK protocol must not depend on each other's models.
- Maintain synthetic tests without external game assets; integration tests
  use a private local fixture bundle only.

**Do not advertise this alpha as a working replacement for the existing 0.2.6 game.**
