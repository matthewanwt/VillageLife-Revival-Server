# Audit remediation — 19 November 2026

## Result

Implemented the code changes for all 21 audit findings. The source includes the
previous gameplay/storage fixes and the reviewed PR 5/6 changes. Local main was
fast-forwarded to reviewed commit `ed24f78`, with existing edits preserved. New
work remains uncommitted and unpublished for review.

The candidate is a **private test build**, not a replacement public release.
It installs separately and defaults to `%LOCALAPPDATA%\VillageLifeAuditPrivate`.
The original game XAPK is bundled; the OBB is extracted during guided setup.
Neither supplied community save archive was changed.

## Implemented findings

| Finding | Implementation |
| --- | --- |
| P01 — Growing history | Completed actions move atomically into indexed, lazily loaded SQLite history. Large records use bounded, lossless compression. Active tasks remain in the hot payload. No history or replay protection is discarded. |
| P02 — Repeated reads | Consecutive reads reuse a request snapshot; revision checks detect other writers, and committed mutation snapshots are reused. |
| P03 — Diagnostic commits | RPC outcomes aggregate into one bounded transaction per request batch; gameplay still commits each action immediately with FULL durability. |
| P04 — Definition reparsing | Parsed definitions and grouped lookups are cached. Callers receive independent copies; work rewards use grouped indexes. |
| P05 — Scene/mapping work | Authored scene parsing is cached, native identity mappings are reused while the revision is unchanged, and request-owned entity indexes avoid repeated searches. |
| P06 — History scans | Busy-task/overlay checks examine active work only. Direct villager/object lookups use scoped indexes, while Farewell/story checks retain access to required completed history. |
| P07 — Connection churn | One thread-owned connection serves a request scope. Actions retain independent atomic commits; no connection is shared unsafely between HTTP threads. |
| P08 — Monitoring | Polling interval is 15 seconds; a lightweight process check precedes the activity-dump fallback. Slow/inconclusive probes remain distinct from a closed game. |
| P09 — Logs | Bounded log queue, batched UI updates, a capped display and three rotating local log files. |
| P10 — Prototype scheduler | Indexed due-job selection and one transaction for each batch of due transitions. It remains separate from original-client gameplay. |
| R01 — Source parity | Reviewed PR changes and missing tests are aligned. Release gates record exact source hashes, reject edits during validation, and verify the source again during manifest generation. Public builds require clean committed source; private builds are explicitly marked. |
| R02 — Ownership | A per-profile Windows mutex prevents competing launchers. An installer marker and in-use checks block updates while launchers are open. Existing exclusive port binding remains. |
| R03 — Cancellation/cleanup | Setup steps and form closure cancel owned tools. A Windows job object removes owned descendants even after abrupt launcher termination. New signing identities publish atomically, and a preparation receipt prevents partial setup being mistaken for completion. |
| R04 — Readiness | Installed APK identity is checked, expansion transfers are hashed, and startup verifies expansion integrity with an in-launcher cache. Capability and preparation receipts must agree. |
| R05 — Import consistency | Shared 128 MiB save limits, bounded generic imports, finite/depth validation and consistent portable import rules. Oversized portable exports fail clearly and direct users to whole-database backups. |
| R06 — Verification | Large-save budgets, read/write-count checks, disk-full and backup-failure tests, interrupted hot/cold transaction recovery, stage timings in diagnostics and packaged-server smoke checks. |
| S01 — HTTP admission | Required local hosts only; browser Origins, browser fetch envelopes and ambiguous framing are rejected. Prepared native routes require a private installation capability. |
| S02 — Community binding | The compatibility channel is protected by that capability; owner identities are tracked separately and checked against current sessions rather than a mutable latest-player identity. |
| S03 — Resource/error limits | Bounded worker concurrency, socket timeouts, JSON depth/node limits, consistent malformed-compression rejection and rejected-body connection closure. |
| S04 — Archives | Nested APK entry/count/expanded-size and manifest limits; streamed nested APK access instead of retaining the whole archive in memory. Existing traversal protections remain. |
| S05 — Supply chain | Fixed Action commit hashes, pinned build requirements, Python/NuGet advisory checks, Dependabot configuration, source/payload hashes, a tool/runtime SBOM, checksums and optional Authenticode signing support. |

## Save migration and rollback

Before history storage is enabled, a consistent full database recovery copy is
created under `backups`, named `*-before-history-v1-*.sqlite3`. Migration cannot
proceed if that backup fails. History and hot state commit together; no delayed
autosave window was added.

The migrated database is marked storage schema **2**. Older launchers reject that
database layout rather than silently ignoring its reward/replay history. To roll
back intentionally, stop the candidate and use its **pre-migration recovery copy**
with the older launcher. Do not open a migrated database with an older build.

`compact-db OUTPUT` creates and verifies a compacted copy without replacing the
active database. The active save is never automatically vacuumed during gameplay.
Whole-database backups include all history and do not have the portable JSON
archive's 128 MiB limit.

## Measurements and validation

- **136 regression tests** pass in the aligned source. The launcher compiles, and
  exact-source private release validation includes the large-save performance budget.
- A representative 10 MB / 50-read batch went from approximately **1.9 seconds**
  in the audit to approximately **36–40 milliseconds** in local retests. Full
  payload reads fell from 51 to 1, and diagnostic transactions from 50 to 1.
  These are backend fixture timings, not game frame rates or a promise for every PC.
- Copies of the two supplied community archives retained exactly the same complete
  logical contents after migration. Their hot payloads fell from **15,042,759 to
  126,534 bytes**, and **16,287,854 to 115,120 bytes**, retaining **2,450** and
  **3,033** historical records respectively. Originals remained untouched.
- Both real-copy databases passed integrity checks. Export/re-import, changed
  historical records, replay and rollback are covered by tests.
- Windows process cleanup passed normal-parent-exit and forced-parent-death checks.
- The packaged server passed private-capability rejection, login, inventory after
  archival, historical record preservation, malformed-request rejection, restart
  and port-release checks. No test listener was intentionally left running.
- Pinned build dependency audit returned **no known vulnerabilities found**.
  NuGet inspection found no declared package dependencies in the launcher project.

Audit evidence lives in the private `experiments/audit-remediation-20261119`
workspace. Only anonymized counts/timings appear here; player names, device IDs,
session tokens and save contents are not included.

## Remaining external/manual verification

1. Use a dedicated test BlueStacks instance. The updated native capability requires
   the candidate's guided setup to prepare its local APK once; the signing identity
   is retained across subsequent setup runs.
2. Test repeated gathering/collection, construction/decorations, all three areas,
   Add Gems, family/skills/charms and close/reopen behavior in the real game UI.
   Include a long-running village on the slower computer where lag was reported.
3. Test the complete installer while another launcher is open, and cancellation
   during actual emulator setup. Source/build/process checks do not substitute for
   every BlueStacks-version-specific UI interaction.
4. A trusted Windows publisher certificate has **not** been supplied. The pipeline
   supports `SigningCertificateThumbprint`, but this private installer is unsigned.
   Local Android signing is separate and is implemented. No OWASP certification or
   Internet-hosting security claim is made.

The native URL capability is generated per prepared installation and constrained
by the historical client's fixed URL slots. It is additional protection for local
compatibility traffic, not a replacement for Windows account security or a hosted
multiplayer authentication system. Network isolation remains explicitly unverified.
