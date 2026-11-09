# Rule recovery standard

We must not confuse an *existing protocol response* with an understood *game rule*.
A feature can be marked implemented only when its transitions, preconditions,
output schema, persistence and failure cases are backed by the original client,
original resource tables, observed gameplay or independently tested legacy code.

## Evidence status labels

- **Verified:** input/output, timing, prerequisites and state changes evidenced
  and covered by regression tests.
- **Inferred:** plausible from data or code structure, but unverified behaviour.
- **Missing:** no reliable implementation; must fail with `NotImplementedRule`.

## High-priority missing verification

| Domain | What must be proved |
|---|---|
| Buildings | Work availability, villager assignment, input consumption, completion, rewards, passive production, upgrades, occupancy, cross-area persistence |
| Riverside | Scenario IDs, unlock prerequisites, entity placement, travel, family persistence, farming/quests, startup/load cycle |
| Mountain | Same as Riverside, plus any region-specific tools, hazards, quests and production requirements |
| Villagers | Identity, body/age/gender stages, stamina/needs, movement, death, birth, pregnancy, partners and genealogy |
| Families | Persistent family-tree links, permissions and multi-player cross-village relationships |
| Tasks | Duration, modifiers, material costs, success conditions, cancellation, replay behaviour, reward claim |
| Economy | Original currency, item IDs, crafting, inventory and progression consistency |
| Quests | Prerequisite graphs, activation, reward grants, repeatability, interaction with areas |
| Networking | Original login, process calls, offline/local/hosted differences, asset manifests |
| Social | Friends, visits, consent, gifts, relationships, account ownership and privacy |

### Timed jobs

The existing 0.2.6 backend demonstrates work timestamps and manual collection.
The redesign keeps `working → ready` independently of the UI, so an offline
return and a hosted scheduler get the same state. It **does not** grant rewards,
repeat productions or simulate unattended buildings without verified rules.

`VerifiedTaskRule` carries a required `evidence` field so future implementers
can't add arbitrary seconds or rewards without provenance. Example test rules
are explicitly synthetic and must never be used in player worlds.

### Unknowns remain visible

`UnverifiedAreaRules`, `UnverifiedBuildingRules`, and `UnverifiedFamilyRules`
raise explicit exceptions. The new server returns `501` for unimplemented
client actions rather than pretending they succeeded.
