# Villager collection acknowledgement

The original Android client's `Script_2299_ServerCollectVillager` formats the integer request field `VillagerBaseId` and enqueues `ClientVillagerService/CollectVillager` with no response listener. Current backend main does not route this service and returns per-call 501. A successful birth can therefore be recorded while its subsequent collection acknowledgement cannot be persisted.

The local collection model is separate from villager creation:

- `Script_1907_GachaVillagersModelAwardedVillager` changes an empty status from 0 to 1.
- `Script_1908_GachaVillagersModelCollectVillager` changes status 1 or 2 to 3; other states are left alone.
- The backend already records awarded special villagers with collection status 2 and returns that map through `GetUserGachaVillagers`.

The fix acknowledges an existing awarded collection entry by persisting status 3 and returning an empty response. It never spawns a villager, spends gems, awards rewards, or changes birth/pregnancy records. Unknown, locked and malformed entries are rejected; an already collected entry succeeds without changing it. Existing repository receipts provide same-call replay protection.

Read-only reference: original `libpdandroid.so`, SHA-256 `066a8fe3b0d90473c9138fba2aa3a3fcf3c22c55f977c567d4c0016966d2edb9`. ARM symbol entry addresses: awarded model `0x3c0334`, collected model `0x3c03a0`, server call `0x3dc7c0`. The collected model compares against 2 and 1 before storing literal 3; the server call passes a zero listener to `Script_2237_ServerAddCall`. No original library, authored tables or player data are included here.

Synthetic tests cover status transitions, replay, invalid/locked inputs, unknown-state preservation, authenticated routing, SQLite reopen and unchanged currency/roster. The authenticated test fails with 501 on unchanged main and passes with this route. These tests do not establish physical-client UI acceptance or investigate any reported currency-display discrepancy.
