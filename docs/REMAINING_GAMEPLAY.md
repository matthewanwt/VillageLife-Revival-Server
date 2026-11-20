# Current source and remaining restoration work

The published community download remains 0.3.6. Main now includes the accumulated
save-performance/reliability fixes, the redesigned launcher and merged PR #9 for
custom-drive BlueStacks detection. A new release has been deferred at the owner's
request; these changes are source updates, not a new published installer.

## Remaining checks and features

- Continue checking missing-request reports against real gameplay, particularly
  less-common authored quests, area-specific buildings and long-running villages.
- Expand event/seasonal coverage and original-rule verification. Do not invent
  original event rules or present unimplemented operations as successful.
- Recheck full play sessions on slower PCs and different BlueStacks builds.
  Backend fixture timings measure server work, not rendering frame rates.
- Launcher text is currently English; the original client's language is separate.
- A Windows publisher certificate is not configured. Optional signing support
  exists, but previous installers remain unsigned.
- Guest network isolation is not certified. Diagnostics collect observations and
  do not enforce or establish a complete IPv4/IPv6/DNS/UDP policy.

## Save compatibility in current source

Current-format villages adapt on Play, with a full backup before enabling the
new history format. Completed history is preserved. Schema-2 databases require
the newer code. To return to an older launcher, stop the server and use the
pre-migration recovery copy, rather than the migrated database.
The 0.2.6 importer copies original profile/save files. Keep the original backup
and BlueStacks instance separate until the imported village is checked.

## Validation

The integrated regression run passes 165 tests, including PR #9's 29 discovery
tests. Prior private desktop checks cover the new launcher pages, setup/chooser
cancellation, village selection, backups, invalid gem input and error recovery.
Release gating also checks large-save budgets, source privacy/size and pinned
build dependencies. These do not substitute for every gameplay interaction or
clean-PC installer test. Packaging/publication will be revisited separately.
