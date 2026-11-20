# Village Life — performance, reliability and OWASP review

Date: 19 November 2026, Australia/Brisbane.

## Outcome

The strongest demonstrated performance problems are repeated whole-save parsing,
history retained inside the frequently rewritten payload, and a durable diagnostic
transaction for every RPC. Larger saves magnify these costs even when the game is
only reading settings. This supports the save-growth hypothesis but does not prove
that every report of animation stutter has the same cause.

There are **21 findings**: ten performance/efficiency findings, six reliability and
release findings, and five security/hardening findings. Six are P1 priorities.
No P0 finding was established within this scope. Security recommendations assume
the existing single-computer, loopback-only deployment; this backend should not be
treated as a production Internet service.

This pass produced an audit and reproducible probes. It did not change gameplay,
player saves, BlueStacks configuration, Git commits or published installers.
Earlier save-efficiency changes are included in the audited source and are clearly
distinguished below from work still outstanding.

## Scope, provenance and limits

- Primary source: `C:/Users/matti/Documents/Github/VillageLife-Revival-Server`.
- Local HEAD: `a4c4760` (`Link to latest and past community downloads`), with 21
  pending/untracked entries before this report. This is a working-tree audit,
  not a claim about exactly what is inside a published EXE or GitHub main today.
- Frozen snapshot: `experiments/Code Audit 20261119/source` in the restoration
  workspace. Manifest: `source-manifest.json`, including per-file hashes.
- Current tree inventory: 122 code/configuration files, 13,925 lines: 75 source
  files, 23 test files, 12 tools, 11 Windows files and one CI workflow.
- Syntax parsing covered all 109 Python files in that snapshot. Detailed review
  focused on save transactions, RPC dispatch, game-history retention, definitions,
  world projection, authentication, HTTP parsing, assets, imports, launcher
  lifecycle, setup, installer construction and release checks.
- An additional 120 legacy backend/tool/launcher files (10,159 lines) were screened;
  all 117 legacy Python files parsed. The retired updater and transport paths were
  spot-reviewed. This is not a full behavioral retest of the retired backend.
- Archived EXEs, duplicate release folders, extracted proprietary assets, the
  BlueStacks implementation and native game rendering were not independently
  audited. No production penetration test or CVE certification was performed.
- Current source, the separate retest tree, and public release binaries are
  different artifacts. R01 documents the verified source/test discrepancy.

## Validation and measurements

| Check | Result |
| --- | --- |
| Frozen current working-source regression suite | **119 passed**, 24.566 s |
| Windows launcher Release build | **Passed**, zero warnings/errors |
| Existing source-release audit on actual checkout | **Passed** |
| Existing diff whitespace check | **Passed** |
| Python syntax checks, current + legacy | **226 files passed** |
| Isolated security/performance probes | Completed; fixture DBs only; ephemeral localhost server closed |

The earlier 126-test result belongs to the separate retest tree. It must not be
described as 126 tests passing in the current GitHub working tree. The five new
save-efficiency tests are present in both trees; other parity gaps remain.

### Read amplification

Fixture: one village, empty normal scene, synthetic padding to vary payload size,
and successful read-only settings RPCs. Three samples per configuration; median
wall time. Padding is invented data, not an actual player's inventory/history.
These are backend request timings, not frame-rate measurements.

| Padding | Calls in one request | Full village reads | Diagnostic transactions | Median |
| --- | ---: | ---: | ---: | ---: |
| 0.1 MB | 1 | 2 | 1 | 16.22 ms |
| 0.1 MB | 50 | 51 | 50 | 485.96 ms |
| 1 MB | 10 | 11 | 10 | 171.30 ms |
| 1 MB | 50 | 51 | 50 | 832.15 ms |
| 10 MB | 10 | 11 | 10 | 362.13 ms |
| 10 MB | 50 | 51 | 50 | 1,897.90 ms |

A separate comparison of the same 10 MB / 50-call fixture measured 1,993.94 ms
normally, 1,455.14 ms with diagnostic recording disabled **only in the probe**,
and 1,606.40 ms with normal diagnostics but a database connection held open.
These experiments demonstrate contributions, not additive or guaranteed savings.
Disabling diagnostics is not the proposed product fix.

Warm authored-table reads also allocate and parse repeatedly: 100 calls to
`rows('reward_set_item')` decoded 3,841 rows each and took 820.60 ms locally.
The SQL result cache was already warm. No proprietary table contents were exported.

Evidence: `run_audit_probes.py`, `probe-results.json`, `regression-tests.txt`,
`launcher-build.txt`, `source-tree-differences.json`.

## Priorities

- **P1:** address in the next performance/reliability pass or before packaging a
  public candidate. P1 is not a claim of critical security exposure.
- **P2:** confirmed implementation weakness or a credible cost/risk needing
  measurement, with the confidence stated individually.
- **P3:** lower-priority optimization/hardening, particularly inactive paths.

## Performance and efficiency findings

### P01 — P1: Growing histories remain in the hot village payload

**Evidence:** `src/villagelife/persistence/sqlite_store.py:201` parses, validates and
serializes the complete payload for mutations. `protocol/original_client/work.py:257`
retains completed jobs plus response snapshots; `quests.py:118` retains completed
quests plus inventory responses. Habitat, fun, interactive and other receipt maps
also retain gameplay history. `services.py:387` updates activity time, so the new
unchanged-payload fast path will not avoid most genuinely changing writes.

**Effect:** old villages become expensive even when their visible scene is small.
The previous consumption compaction and expired-session response retirement help,
but do not bound the remaining histories or eliminate full-payload serialization.

**Recommendation:** separate active world state from completed-action history in
versioned SQLite tables, with atomic transactions and indexed replay lookups.
Preserve request digests, historical relationships and duplicate-reward protection.
Migrate on a backup copy and prove replay safety before retiring any history.
Do not prune arbitrary completed records or weaken synchronous durability.

**Confidence:** confirmed structure; measured serialization cost in the preceding
save-efficiency review. Affected-player save validation remains required.

### P02 — P1: N+1 whole-village reads in RPC batches

**Evidence:** `services.py:200`, `:251` and `:281` load the initial snapshot,
reload before subsequent calls and reload at the end. Even a batch containing only
read-only settings calls performs N+1 full JSON parses. The probe measured 51
reads for 50 calls and approximately 1.9 s at 10 MB.

**Recommendation:** retain one request-scoped snapshot for consecutive reads;
refresh after a committed mutation or a detected revision change. Return/use the
committed mutation snapshot rather than immediately fetching it again. Preserve
call ordering, concurrent-write behavior and cross-village isolation.

**Confidence:** reproduced and counted.

### P03 — P1: Ordinary diagnostics force a durable transaction per call

**Evidence:** `services.py:276` calls `support.py:251` for each RPC; recording opens
an independent `BEGIN IMMEDIATE` transaction. Fifty read-only calls generated 50
diagnostic transactions. Temporarily disabling recording in the fixture reduced
the comparison from 1,993.94 to 1,455.14 ms.

**Effect:** reads become competing writers and slower disks pay repeated commit
costs. Gameplay and diagnostic writers share SQLite's single writer lock.

**Recommendation:** aggregate outcomes per HTTP batch and persist them in one
diagnostic transaction, or use a bounded queue with explicit flush before report
export. Preserve current-run scoping, errors and visible dropped-record counts.
Gameplay commits must remain immediate and durable.

**Confidence:** reproduced; actual community SSD/HDD impact not yet measured.

### P04 — P2: Cached definitions are reparsed into thousands of dictionaries

**Evidence:** `catalog.py:28` JSON-decodes every row on every `rows()` call;
`item()` also decodes a cached string on every lookup. Work/building/family code
repeatedly filters complete reward and requirement tables. The warm-table probe
decoded 384,100 rows in 100 calls, taking 820.60 ms.

**Recommendation:** cache immutable parsed definitions and indexes keyed by reward
set, requirement set, recipe, area and parent. Return copies only where callers
need mutable data. Invalidate by source database identity/hash; never allow cached
definitions to become shared mutable player state.

**Confidence:** measured primitive cost; end-to-end saving needs profiling.

### P05 — P2: Repeated scene parsing and identity/projection work

**Evidence:** `world.py:88` reparses authored XML each time; `world.py:295` calls
authored loading during area projection. `services.py:253` reconstructs native ID
mappings for individual calls; `native_ids.py:43` scans active and retired actors
and hashes identifiers. Projection intentionally copies wire objects.

**Recommendation:** cache immutable authored scenes, build request-scoped identity
indexes, and reuse rule providers. Keep canonical save objects and wire projections
separate. Do not remove required roster members merely to reduce response size.

**Confidence:** confirmed repeated work; contribution not isolated in a benchmark.

### P06 — P2: Active-task checks scan all completed history

**Evidence:** `work.py:172` traverses every historical work record when checking a
worker/source. Workshop concurrency performs another scan. World/bed/entity and
some relationship lookups also repeatedly traverse lists.

**Recommendation:** index active tasks by villager/source and entities by stable ID;
maintain indexes transactionally or derive them once per request. Historical jobs
should not participate in the active-task search. Profile large decoration and
building populations before claiming this fixes emulator frame-rate lag.

**Confidence:** confirmed complexity; no dense-scene timing measured in this pass.

### P07 — P2: Database connection churn adds overhead

**Evidence:** `sqlite_store.py:117` opens/configures/closes a connection for each
read or transaction. Closing the last WAL connection can require cleanup/checkpoint
work. Holding a connection open reduced the 10 MB / 50-call comparison from
1,993.94 to 1,606.40 ms, with normal diagnostics retained.

**Recommendation:** first reduce redundant transactions and reads. Then evaluate
owned per-thread connections or a small managed connection lifetime, with explicit
shutdown and backup behavior. Do not share a normal SQLite connection unsafely
across HTTP threads or assume WAL makes writers parallel.

**Confidence:** measured comparison; a production connection-lifetime design is
still required, especially for Windows file handles.

### P08 — P2: Background game monitoring repeatedly launches backend/ADB tools

**Evidence:** `GameMonitoring.cs:7` schedules five-second checks; `:33` starts a new
backend tool with a 25-second limit. `original_client.py:215` fetches the activity
dump, while `_adb()` also reconnects/verifies the selected instance.

**Recommendation:** measure polling CPU and latency, reduce dump frequency, and
prefer a lightweight status query or a long-lived bounded monitor. Preserve the
distinction between unknown, disconnected and genuinely closed; never stop a
healthy game because one slow probe timed out.

**Confidence:** confirmed behavior; contribution to community stutter unmeasured.

### P09 — P2: Launcher output grows without a bound

**Evidence:** `Program.cs:52` continually appends text; background server readers
queue UI log updates. There is no line/byte retention limit or append batching.

**Recommendation:** retain a bounded recent log in the UI, batch updates, and use
size-limited rotating files for longer support history. Preserve useful errors and
avoid logging private request values.

**Confidence:** static finding; long-session UI memory growth not load-tested.

### P10 — P3: Prototype scheduling does repeated full scans

**Evidence:** `services/jobs.py` scans villages/jobs and commits due transitions
individually; `simulation/runner.py` can repeat that scan every five seconds.
The community original-client serve path does not start this prototype scheduler.

**Recommendation:** use an indexed due queue and batched transitions if this path
becomes active. Do not attribute current original-client lag to an inactive service.

**Confidence:** confirmed design limitation, currently low operational relevance.

## Reliability and release findings

### R01 — P1: Tested and packaged source trees are not yet aligned

**Evidence:** current checkout HEAD is `a4c4760`; the frozen checkout passes 119
tests. The separate retest tree passes 126. After normalizing line endings, seven
paths differ: collection, family and world modules; a retest-only
`collection_projection.py`; retest-only `test_collection_presentation.py` and
`test_original_gem_debits.py`; and differing `test_original_collection.py`.

**Recommendation:** reconcile the working tree with reviewed merged changes while
preserving local edits. Establish one build source and run its exact tests.
Record commit plus dirty-source hashes, version, tool versions and payload hashes
in a build manifest; smoke-test the packaged server. Do not label a release verified
using another tree's test count. Archived root backend/tool copies remain retired.

**Confidence:** verified file comparison and executed test counts.

### R02 — P1: Launcher ownership is process-local while settings are shared

**Evidence:** `Program.cs:97` only checks this window's `backend` field. Settings
and the BlueStacks binding live at shared per-profile paths. No named launcher
mutex or shared setup/save-selection ownership lock was found. The installer has
`CloseApplications=no` (`VillageLifeCommunity.iss:28`). Exclusive port binding
correctly blocks a second backend listener, but does not lock setup/settings.

**Effect:** a second launcher can attempt selection/setup while another launcher
owns a running game. Its binding changes can affect the first launcher's monitor.
In-use upgrade/abort behavior also needs a dedicated installer test.

**Recommendation:** introduce per-data-profile launcher/setup ownership and an
explicit handoff; reject conflicting changes. Test installer updates while the
launcher/backend is running, including rollback. Do not kill unrelated port owners.

**Confidence:** confirmed missing coordination; simultaneous-instance scenario
inferred from shared paths, not exercised against real BlueStacks here.

### R03 — P2: Closing during setup does not own/cancel all child tools

**Evidence:** `Program.cs:38` returns from closing logic when no gameplay backend
exists. `Once()` at `:67` owns a tool only inside its asynchronous call and has no
form-lifetime cancellation. The busy wrapper also disables Stop during operations.

**Recommendation:** cancel and await owned setup/check processes on close, use a
Windows job object where appropriate, and expose cancellation for long steps.
Keep completed prepared files and roll back incomplete files safely.

**Confidence:** static lifecycle gap; no destructive close-during-install test run.

### R04 — P1: Prepared-client readiness does not verify the installed APK

**Evidence:** `GuidedSetup.cs:207` can return early on `Ready(settings)` plus
`GameInstalled('--prepared', '--obb', ...)`. That CLI branch calls
`original_client.py:83`, which checks package presence and OBB size, not whether the
installed APK matches the prepared locally patched APK. A separate hash checker
exists but is not used by this successful early-return path.

**Effect:** after an app replacement/reset or equal-size OBB corruption, readiness
can be reported incorrectly, leading to failed sign-in or asset problems.

**Recommendation:** verify installed APK identity/version/hash on relevant changes,
and verify OBB integrity when installing/repairing or when corruption is suspected.
Cache verification against trustworthy file/installation identity to avoid a full
450 MB hash on every Play.

**Confidence:** confirmed code-path mismatch; real reset/corruption retest pending.

### R05 — P2: Save import limits differ across entry points

**Evidence:** the guided legacy importer bounds saves at 128 MiB; portable ZIP
import bounds village JSON at 64 MiB (`portable.py:60`). Generic CLI
`legacy_import.py:49` uses unrestricted `read_bytes()` and bypasses the guided
entry point's size/depth validation path. Existing upper bounds are not save
growth management.

**Recommendation:** centralize documented size/depth/count limits, perform bounded
reads before parsing, align user-facing errors and support previews for large
saves. Keep format-specific limits intentional; do not simply remove all limits.

**Confidence:** confirmed inconsistent policies and unbounded CLI read path.

### R06 — P2: Performance/release failure coverage is incomplete

**Evidence:** tests cover killed-process atomicity, backups and replay, but CI has
no long-running save-growth budget or measured large-batch latency threshold.
Diagnostics record shapes/counts, not per-stage timings or lock waits. The
community installer build script does not itself run tests/release checks before
packaging; separate CI builds source but does not validate the finished EXE payload.

**Recommendation:** add representative old/imported saves as private fixtures,
synthetic long-session workloads, p50/p95 timings, lock/commit measurements and
bounded-growth checks. Add disk-full, backup failure, concurrent import and
interrupted-update scenarios. Make exact-source tests and packaged smoke tests a
release gate. Preserve current-run diagnostic scoping and redact all timing metadata.

**Confidence:** test/build inventory gap, not evidence that existing atomic saves
are broken.

## OWASP security findings — secondary priority

Frameworks: [OWASP Top 10:2025](https://top10.owasp.org/) and
[OWASP ASVS 5.0.0](https://asvs.owasp.org/). This is a relevant-category source
review with selected local probes, not exhaustive ASVS compliance or certification.

### S01 — P2: Loopback HTTP does not reject untrusted Host/Origin envelopes

**Evidence:** a fixture request with `Host: untrusted.example` and an untrusted
Origin returned 200 from health. A `text/plain` browser-shaped POST to the original
login route also returned 200. `http_api.py` has no Host/Origin admission checks.

**Risk:** other local software can reach the service; malicious-page requests and
DNS-rebinding scenarios deserve defenses. A successful local probe is not proof of
a complete remote browser exploit. Modern browser private-network restrictions
were not evaluated. Loopback binding materially limits ordinary network exposure.

**Recommendation:** allow only required local/emulator hosts, reject browser
Origins on native-only routes, and add a launcher session secret where the native
protocol can carry it. Preserve compatibility with the emulator's host address.
Do not solve this by exposing the service on all network interfaces.

**OWASP:** A01 access control, A02 configuration, A07 authentication.

### S02 — P2: Native community fallback relies on numeric player ID alone

**Evidence:** `community.py:29` falls back to the globally stored latest identity
when session/device credentials are absent. A credential-free fixture `User/Get`
using that active numeric ID returned a user object with call code 200. Mutating
dating services use the same identification result.

**Risk:** knowledge of the active player ID can become sufficient authority for a
local caller; switching active identities between requests also introduces a
cross-instance concurrency risk. No arbitrary filesystem access was demonstrated.

**Recommendation:** bind the compatibility channel to one explicit active village
and transport capability, or isolate it per instance/session. Retain safe empty
read replies where required, but do not extend ID-only trust to future hosted play.

**OWASP:** A01 access control, A07 authentication.

### S03 — P2: HTTP resource handling and malformed-input errors need bounds

**Evidence:** `ApiServer` uses a thread-per-connection server; the handler timeout
is `None`, with no application worker cap. Body length limits exist, but body read
time is not bounded. A malformed compressed request returned 500: `zlib.error`
escapes the decode-specific rejection path. Deep JSON can also reach recursive
parsing/translation before a bounded mutation validation runs.

**Recommendation:** enforce read/idle timeouts, bounded simultaneous work and JSON
depth/container limits; reject truncated/malformed encoding as 400. Close rejected
connections with unread bodies and test partial uploads. Retain decompression
limits already implemented in the codec.

**OWASP:** A06 insecure design, A10 exceptional conditions. In this deployment this
is primarily a local availability/reliability concern.

### S04 — P2: Archive/data preparation trusts some large nested inputs

**Evidence:** `tools/prepare_original_client.py` bounds outer APK/OBB members, but
`make_unsigned()` reads inner APK entries without an aggregate expanded-size bound.
`ClientAssets` loads the nested APK into memory and reads its manifest without the
same preparation limits. Generic import has the unbounded path described in R05.
The community build verifies its original XAPK hash, lowering normal exposure.

**Recommendation:** validate known packaged assets by hash; bound inner members,
aggregate expansion, entry counts and manifest sizes for user-selected archives.
Keep fixed output paths and existing traversal protections. Do not remove support
for legitimate large saves in the name of archive security.

**OWASP:** A06 design, A08 integrity, A10 exceptional conditions.

### S05 — P3: Release dependency/provenance assurance is incomplete

**Evidence:** community `Build-Installer.ps1:47` disables NuGet auditing; CI has no
explicit dependency-advisory/SBOM step. Build dependencies/toolchains are not locked
as one reproducible set; workflow actions use version tags. No Authenticode signing
step is present in the Windows installer pipeline.

**Recommendation:** add an advisory check and a versioned bill of materials for
Python, SQLite, .NET, Java and build tools. Pin reviewed workflow/build dependencies,
publish checksums/build provenance, and consider a Windows publisher signature.
Local APK signing is a separate mechanism and is already implemented. No specific
dependency CVE or malicious package was established by this audit.

**OWASP:** A03 supply chain, A08 integrity.

## Existing protections worth preserving

- Loopback-only server binding and exclusive Windows port ownership.
- Parameterized save/auth SQL; no confirmed SQL injection or shell-injection
  path was established in the reviewed current runtime.
- Cryptographic session/token generation; hashed API tokens and explicit village
  ownership checks on the new API.
- Atomic save transactions, WAL with `synchronous=FULL`, request-digest replay
  protection and actual killed-process recovery tests.
- SQLite-consistent backups, temporary files and refusal to overwrite existing
  backups/imported villages silently.
- Guided import fingerprint checks, bounded guided reads, fixed archive filenames
  and path checks. Legacy updater path traversal/junction checks are also present.
- Bounded legacy decompression and conservative gem validation/balance limits.
- Diagnostics aggregate structures rather than raw player requests, and fresh
  server runs reset their capture scope.
- Source release checks exclude original game binaries, saves and runtime data.
- Network diagnostics explicitly do not certify guest isolation. No complete
  emulator egress/firewall policy was established in this pass.

The retired root `backend/server.py` can retain raw request documents in private
logs outside summary mode. Keep those logs private and do not revive that backend
in a community package. Its manual updater verifies per-file integrity and safe
paths, but an unsigned colocated manifest is not publisher authentication.
These are legacy observations, not additional current-runtime findings.

## Recommended implementation order

1. **Align the build source and missing regression tests (R01).** Preserve local
   gameplay/storage fixes and reconcile reviewed PR content; record exact hashes.
2. **Reduce batch reads and diagnostic commits (P02, P03).** These are measured,
   relatively contained improvements. Add before/after timings and read/write counts.
3. **Cache/index immutable definitions and active-task lookups (P04–P07).** Verify
   copies never leak changes across players, areas or requests.
4. **Design/migrate cold history storage (P01).** Test months of actions, old-save
   imports and duplicate claims without changing balances or removing family data.
5. **Harden launcher ownership/readiness/lifecycle (R02–R04, P08–P09).** Test on a
   second PC with slow storage and repeated setup/open/close cycles.
6. **Align import handling and release validation (R05–R06).** Include failure
   injection, exact-built-artifact smoke tests and performance budgets.
7. **Apply local security hardening (S01–S04), then release provenance (S05).**
   Lightweight admission/timeouts can be included alongside HTTP changes, but a
   hosted multiplayer redesign is outside this audit's immediate priority.

Manual release-candidate checks should include repeated resource collection,
dense buildings/decorations, travel among all areas, charms/skills/birth/weddings,
Add Gems, restarting and forced closure. Compare quantities, villagers and tasks
before/after. Automated performance wins do not replace a real lagging-save retest.
