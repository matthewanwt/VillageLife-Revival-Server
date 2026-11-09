# System coverage from uploaded backend.zip

**Status date:** 9 November 2026. This is a porting map, **not** a claim of original-client parity.

Preserved original backend modules: **28**. Preserved original test files: **40**.

The new implementation includes generic storage/time/identity capabilities, not original game rules.

| Original module | New location / current status |
|---|---|
| `areas.py` | AreaService + scenario RuleProvider (unlock/transfer not ported) |
| `buildings.py` | BuildingService interface; original construction/work not ported |
| `charms.py` | Legacy reference only (not ported) |
| `codec.py` | legacy_codec.py (format implementation isolated) |
| `collection.py` | Legacy reference only (not ported) |
| `community.py` | SocialRepository friend consent; original social RPC not ported |
| `family.py` | FamilyService interface; original birth/genealogy not ported |
| `fortune.py` | Legacy reference only (not ported) |
| `fun.py` | Legacy reference only (not ported) |
| `habitats.py` | Legacy reference only (not ported) |
| `interactive.py` | Legacy reference only (not ported) |
| `learning.py` | Legacy reference only (not ported) |
| `marriage.py` | FamilyService interface; original marriage rules not ported |
| `native_identity.py` | core/identity.py basic UUIDs; legacy ID mappings not ported |
| `needs.py` | Legacy reference only (not ported) |
| `placement.py` | Legacy reference only (not ported) |
| `player_access.py` | AccountTokens new API; old invitation file auth not ported |
| `prerequisites.py` | Legacy reference only (not ported) |
| `progression.py` | Legacy reference only (not ported) |
| `quests.py` | Legacy reference only (not ported) |
| `relationships.py` | FamilyService interface; original partner logic not ported |
| `server.py` | transport/http_api.py new API only; legacy RPC/asset servers missing |
| `session.py` | SQLite saves, importer, ActionDispatcher; original login/process missing |
| `shop.py` | Legacy reference only (not ported) |
| `social.py` | SocialRepository (new account friendship), old RPC missing |
| `starter_tools.py` | Legacy reference only (not ported) |
| `tasks.py` | JobService time-state infrastructure; original task economy missing |
| `world.py` | core/model.py, AreaService; original authored world generator missing |

## Coverage and compatibility rules

- `Implemented foundation` means the new framework works with synthetic tests, **not** that the original client is supported.
- `Interface` means original rules must still be recovered and tested.
- `Legacy reference only` means original existing code is preserved but not yet ported.

Each migration should identify the original service handler, use-case inputs, state mutation, save format, response serialization, error cases and regression fixture.

## External dependencies currently missing from the upload

`session.py` and `world.py` refer to `analysis/private/game_tables.sqlite`; `server.py` expects the original XAPK and `analysis/runtime_inputs/*.obb`, plus the OBB inventory. The ZIP intentionally excludes those. They are runtime resources for later local integration tests, not GitHub source dependencies.

## Special blockers

- Background building production needs source-verified rules (not simply timer state changes).
- Riverside/Mountain initialisation needs full scenario and entity identity parity, not just unlocking area IDs.
- Cross-device and multiplayer transfers require a proven identity and conflict policy.
- The original client calls binary endpoints not yet provided by the new HTTP transport.
