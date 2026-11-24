# Community ticket review — 21 November 2026

> Status: the source changes described below shipped in 0.4.1. This review text
> is retained as written at the time of the pass.

This was a source-only update at the time of the pass. No installer, release tag, or public download
was published in this pass. The 35 accessible numbered tickets contained 265
messages, including follow-ups and duplicates. Private messages, media, and
diagnostic archives remain outside the repository.

## Changes in this pass

- **Long-running villages:** building placement/movement, plot capacity checks,
  transfers and removal checks use active work rather than loading every archived
  task. Completed-foundation cleanup uses a direct saved job reference. Travel
  reconciliation maintains six story references instead of reading all completed
  quest responses on every area change.
- **Feeding:** an index of the most recent receipt per villager/material replaces
  repeated scans through consumption history. Existing receipts are indexed once;
  exact receipt replays and cooldowns remain intact. Receipts are not deleted.
- **Riverside tools:** the original `material_mastery` mapping supplies everlasting
  markers for the five free, uncraftable starter tools. It does not give mastery
  of craftable tools, unlock arbitrary recipes, or charge gems.
- **Hero housing:** the eight known Woodland hero homes retain the two-bed
  compatibility layout in new villages as well as imported villages. Existing
  occupants and bed IDs survive reconciliation. Other scenery and unknown shelter
  capacities still do not receive guessed slots.
- **Multiple workshops:** a separate workshop keeps its own foundation location
  and identity. It no longer replaces an existing workshop and inherits that
  workshop's position. Explicit upgrades still replace their selected target.
- **Skills:** reads/training accept all three known skill-ID field spellings.
  Adult charm awards distinguish paternal, maternal and professional shields and
  arrive with their existing profession selected. Proven adult charm awards and
  matching six-star hero appearances can recover missing authored ranks, without
  removing purchased ranks or changing an explicit player choice. Recorded births
  can restore missing inherited shields from their saved conception record.
- **Starting skills:** proven ordinary starters receive the expected two inherited
  slots and, for starting adults, a professional slot. Existing choices remain.
  Children with known parents use those parents' professions. The original random
  starter-skill distribution is absent from the extracted tables: missing unknown
  ancestral choices use a stable uniform Woodland-skill restoration fallback.
  This distribution is explicitly unverified, and no family links are invented.
- **Pregnancy:** a durable active pregnancy plan prevents a second conception even
  when its old display flag is missing. The plan and gem balance remain intact;
  stale baby wishes clear. String-form legacy baby material IDs also clear.
- **Regional wishes:** food and housing requests follow the current area instead
  of defaulting to Woodland strawberries/basic shelter. A food fallback comes
  from authored local gathering sources. An outstanding local wish remains stable
  if its stock runs out; travelling can replace an incompatible regional wish.
- **Deterministic rewards:** zero-chance or zero-quantity alternatives no longer
  make a deterministic task fail as "unrecovered randomness". This covers a
  disabled row in an original wounded-deer reward set. Positive random rewards
  still require their verified rule; this change does not silently award them.
- **Diagnostics:** fixed, value-free timings now distinguish harvest, task starts,
  inventory, transfers, area loading, feeding and happiness collection. These use
  the existing batched diagnostic write, without adding a database commit per RPC.

The habitat migration version was advanced. Skill repair has a separate durable
migration receipt. New village construction and later shelter operations use the
same habitat rules, so a repaired home is not cleaned up again as scenery.

## Deduplicated disposition

"Existing" means the current unreleased source already contains a relevant fix;
it does not mean every report from public 0.3.6 has been reproduced or cured.

| Report group | Disposition |
| --- | --- |
| Repeated clicking / uncollected tasks / construction rollback | Existing durable storage, history separation, collection acknowledgements and request batching, plus the new scan/index fixes. Full client-session retest remains necessary. |
| Happiness collection locks input | Backend scans reduced; action-specific timing added. Client animation/rendering stalls are not proved fixed. |
| Village temporarily appears reset or missing | Existing village selection/session binding and safe wire projections. No supplied affected save proves deletion; do not erase/recreate villages as a workaround. |
| Workers disappear during tasks | Existing task ownership/area/identity checks and the workshop correction apply. A remaining visual disappearance needs current-build reproduction. |
| Five-minute Reconnection #200 | No unique cause established by the supplied diagnostic archives. Retest with new timings; do not change network/security settings on speculation. |
| Storage counted across villages | Existing area-local quantities, explicit zero markers and inventory refresh notification; retain the already accepted native test. |
| Everlasting knife/palette/basket inaccessible | Fixed free starter mastery markers in this pass. Craftable mastery remains separate. |
| Hero housing 0/0 | Fixed the new-village/legacy distinction for the eight known Woodland hero homes. Unknown event homes remain separate. |
| Riverside Abode / Fishing Hut / completed buildings | Existing family-specific building/equipment projection and storage fixes; new workshop/reward changes also apply. Recheck on the private candidate. |
| Second workshop/table stops working or moves off-map | Fixed workshop identity/location replacement; archived work no longer affects ordinary capacity checks. |
| Boulder returns / moving list empty / machinery remains | Existing one-time travel reconciliation and boulder-foundation cleanup retained; travel history checks now use a small index. Visual machinery persistence still needs client confirmation. |
| Corann / Disenchant the Entrance | Original task 1403 started and harvested successfully in an isolated authored-data fixture, producing its result object. Native cutscene/interaction acceptance is not established by that rule-level check. |
| Solstice clothing, Red Flax navigation and missing requirement icon | Still incomplete seasonal/clothing client integration. This is a feature gap, not an optimization fix; no fake event completion or free requirements were added. |
| Missing inherited badges / old heroes / starter skills | Field aliases and evidence-based repair added. Unknown historical inheritance without a saved record is not fabricated. Starter random distribution uses the documented fallback above. |
| Skill bonus reverts on arrival | Existing native float32/truncation parity and saved-deadline tests retained; missing ranks/field aliases also addressed here. |
| Maxed-skill age-up screen | Existing automatic completion for fully mastered choices retained. The ticket follow-up itself reports improvement after 0.3.6. |
| Pregnancy wish repeats / twins or triplets | Active-plan/display reconciliation and stale-wish cleanup added. Existing design locking, population capacity and paid-design rules remain; the reports do not establish a new twins/triplets cause. |
| Birth without naming / baby disappears | Existing durable birth replay and ordinary/rare appearance-ID separation apply. Remaining naming/visibility needs a physical-client test and the affected save if it persists. |
| Wishes after transfer / Woodland requests elsewhere | Food/shelter targets corrected. Conception still requires the married pair to share a valid home after moving; transfer releases old beds. |
| Proposal fails / accepted relationship has no animation | Existing saved dating-to-marriage transitions retained. Animation-only failures require client confirmation. |
| Villager charm / collection-book purchase fails | Existing authenticated collection recruitment and acknowledgement retained. Adult award skill origins corrected here. Retest purchasing/recruitment separately from baby charms. |
| Dating candidates remain unchanged | Authored candidate expiry is 259200 seconds (three days), not one day. Candidates with relationships/pending requests are retained. No random daily reset added. |
| Babies ask for housing / food always strawberries / wedding happiness | Existing minimum shelter age and XP handling retained. Regional/rotating food choices improved here. Exact wedding happiness/animation expectations still need original-rule verification. |
| Incomplete signing identity | Existing atomic creation prevents future half-pairs. An already lost signing secret cannot be reconstructed; preserve backups and verify APK identity before any recovery. |
| Installation / ADB / white-screen startup | Existing guided readiness, package/OBB verification and PR #9 discovery fixes retained. Image-only/device-specific failures remain unconfirmed on the current source. |
| Disabled level-up spin | Existing authored XP/level/spin validation and replay handling retained. Current-build UI reproduction still needed. |
| Distorted audio | No backend audio code identified. Instance/client issue remains open; no speculative emulator-setting change made. |
| Distorted images behind gems | Existing ordinary/rare collection-ID projection fix is relevant, but visual confirmation remains open. |
| Empty inbox request badge | Existing zeroed unsupported offline-inbox summary retained, with persistent notifications handled separately. |
| Missing level-five river-baby event | Event availability/scheduling is not established. Do not promise that a historical time-limited event is active. |

## Validation

- All 180 synthetic regression tests pass, including the new ticket cases, save interruption,
  replay, migration, HTTP ownership and privacy tests.
- New tests cover starter/hero/inherited skill preservation, alternate skill
  fields, adult charm professions, local wishes, missing pregnancy flags, disabled
  rewards, separate workshops, hero beds, archived-history avoidance and diagnostic
  action timing.
- Isolated original-data village: six starting villagers have skill counts
  `2,2,2,3,3,3`; eight known hero homes have two beds each; the five starter mastery
  markers are present; all three areas seed; SQLite integrity check returns `ok`.
- Rule-level original-data Corann construction starts and completes successfully.
- Local 10 MB / 50-read benchmark: median 25.12 ms, slowest sample 29.67 ms. This is
  server work on this machine, not an emulator frame-rate claim.

No community save was edited. No public release, commit, push, or ticket message
was made as part of these source changes.

## What a 100 MB save becomes

A synthetic fixture contained 100.11 MB of JSON, about 10 MB of current data and
90 MB of repetitive completed-work responses. MB here means 1,000,000 bytes.

| Measurement | Bytes | Approximate MB |
| --- | ---: | ---: |
| Original database | 100343808 | 100.34 |
| Current-world JSON after migration | 10000123 | 10.00 |
| Compressed archived record payloads | 10482563 | 10.48 |
| Database after migration/checkpoint, without compaction | 122290176 | 122.29 |
| Reusable free pages inside that database | 100208640 | 100.21 |
| Separately compacted database copy | 22040576 | 22.04 |

All 5631 records survived a full JSON SHA-256 round trip. Migration took 3.29
seconds on the test machine. The fixture is deliberately repetitive; other saves
will compress differently. SQLite reuses freed pages, so a smaller live world does
not imply that the database file immediately shrinks. The live database is not
automatically vacuumed, and pre-update backups consume separate disk space.

## Next native test pass

1. Copy an affected old village; check occupants, old hero ranks and starter skills
   before/after login, then restart and verify they persist.
2. Gather in Riverside with everlasting starter tools; build/upgrade local stores
   in all areas, then transfer villagers and inspect their wishes.
3. Build a second workshop away from the first, craft at both, complete/collect
   construction, and restart.
4. Run a dense old village for longer than five minutes. Collect ordinary items,
   shelter happiness and villager happiness. Export new diagnostics immediately
   after a stall, before stopping the backend.
5. Check a baby charm, birth naming and a proposal animation separately. Track any
   remaining audio, sprite or input lock as a client reproduction, not a presumed
   database problem.
