# Architecture and invariants

## Design goal

A data-driven backend that can eventually support the original ARM32 Android
client through a legacy adapter and future Godot / mobile / desktop clients
through documented APIs, using the **same** authoritative gameplay code.

```
          Legacy APK                 Future Godot/other clients
              |                              |
    legacy protocol adapter             versioned JSON API
              \                              /
                  application command bus
                            |
         domain services + verified original-rule providers
         (families, tasks, areas, buildings, world, economy)
                            |
                    versioned save port
                            |
                    SQLite implementation
        accounts / villages / receipts / social / legacy imports
```

### Dependency direction

`transport` or `protocol` → `services` → `core` / `persistence` ports.
A domain service must not import BlueStacks, HTTP request objects, the launcher,
Windows paths or a game-specific DB connection. It may depend on a *port*.
Concrete adapters hold protocol, file paths, SQLite and platform assumptions.

### Hard invariants

1. Account identity is not a BlueStacks device ID. Village IDs are distinct from
   account IDs; villagers keep stable IDs. Device binding is a separate future port.
2. A save update is transactional, increments a revision, and has an idempotency key.
3. No unverified game rule silently awards materials or changes family relations.
4. Legacy 0.2.6 saves are **opaque** until a deliberate, tested conversion is written.
5. No cross-account action occurs without permissions and atomic state changes.
6. All original client RPCs must preserve byte-level response contracts and error
   behaviour when the compatibility layer is implemented.
7. Local and hosted worlds use the same deterministic time progression. The local
   client can catch up from persisted timestamps without a permanently running task.
8. Runtime files live outside Git and are never embedded in the package.

### Why SQLite first

On one host it gives crash-safe ACID transactions and WAL readers, plus a single
writer. This is a practical starting point; it is **not** an unlimited shared
multiplayer database. A future Postgres implementation can honour the same save
port, with per-village concurrency and atomic cross-village operations.
Avoid active DB files on OneDrive or network shares; backups/export archives can
be copied to synced storage only after the DB produces a consistent snapshot.

### Time progression

`JobService.schedule` requires a rule provider with verifiable original evidence.
`JobService.advance` transitions verified jobs from `working` to `ready`; it
**does not** manufacture rewards. A hosted scheduler and offline catch-up call
`WorldTickCoordinator`. At larger scale, migrate the O(N) scan to an indexed
`due_jobs` table with atomic claims.

### Legacy transport

`legacy_codec.py` implements the original observed XOR/zlib wire format.
`legacy_adapter.py` deliberately requires a supplied RPC handler. We have **not**
yet ported the `session.login` / `session.process` handlers, proprietary asset
responses, or complete original client service endpoints. Do not change the
original game client's destination URL to this new API until integration parity
is proven.

### Expected future interfaces

- `GameDefinitionCatalog`: read-only definitions and scenario data, versioned by hash.
- `WorldRepository`: villages, characters, objects, timers, identity references.
- `AreaRules`: authored Riverside, Mountain and future area initialization.
- `BuildingRuleProvider`: work, production, collection, upgrades and costs.
- `FamilyRuleProvider`: genealogy, partnerships, pregnancies, travel and consent.
- `ClientProtocol`: map original RPC calls and future JSON actions to services.
- `AssetSource`: original-client manifests/OBB served through a separate static adapter.
- `DeviceBinding`: associate many signed-in devices with one account.
- `WorldScheduler`: same verified behaviour for offline catch-up or hosted ticking.

These are contracts. They do not indicate all implementations are already working.
