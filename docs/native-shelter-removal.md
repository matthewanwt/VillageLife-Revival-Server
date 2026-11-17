# Native shelter removal

The original client removes residents from a selected shelter with `EmptyBed`
calls, then submits `ClientUserShelterService/DeleteUserShelter` with
`userShelterId`. Returning 501 for that last call makes the client reload even
though preceding bed changes may already have succeeded.

The handler removes only the validated shelter. It does not remove villagers,
grant refunds, change inventory, or invent relocation rules. A durable
`deletedShelters` entry prevents authored reconciliation from restoring it.
An already-removed, receipted identifier is a no-op.

Validation follows the observed native shelter eligibility rule: template 19 is
protected and other templates must have authored `immovable=0`. Ambiguous IDs,
another area's house, occupied beds or remaining villager bed claims, and active
task references reject removal. An unrelated null task snapshot is valid;
unknown task layouts reject without mutation.

The server groups preceding bed changes for the same shelter with its deletion.
The group and its replay receipts commit in one transaction. A failed deletion
rolls back the matching bed changes, including when another bed is still occupied.
An `EmptyBed` already committed in a separate request remains saved.

Validation:

- The full synthetic suite passes: 96 tests, including six new removal tests.
- The original Android client completed edit mode, its removal confirmation,
  `EmptyBed` and `DeleteUserShelter`, with successful native completion and no
  connection-loss reload, against an isolated QA copy using the shared handler.
- That test retained the roster, relationships, inventory/currency, owner profile
  and retained hybrid SQL records. Only the deleted shelter's bed links cleared.
- A fresh backend process and native login/startup/area reload retained the
  deletion and passed SQLite integrity/foreign-key checks. The reopen comparison
  used a stable post-deletion baseline to separate unrelated ordinary gameplay.

This does not establish general gameplay, physical-iPhone, mouse-input, or
rendering stability coverage. No private saves, assets, native libraries, cloud
configuration, or custom port adapters are included in this change.
