# Migration and development roadmap

## Gate 0: Preserve and test the reference (current)

- Keep original 55 GB project untouched.
- New repository contains clean source plus private code reference, no player data.
- Baseline original running server and save are **not** replaced by the alpha.
- New foundation tests pass without original XAPK or secret data.

## Gate 1: Original-protocol parity

Extract a recorded, privacy-sanitised set of original client login and Process
calls. Port a thin HTTP adapter that decodes requests and sends the exact wire
responses through domain services. For every service, compare request/response
structures with the known working version and record unknowns. Validate legacy
protocol on the original APK (local only) before any community release.

## Gate 2: Save conversion and identity

Develop explicit legacy-save field mapping, schema migrator and cross-client ID
translation. Add device binding and per-account auth. Preserve every villager,
relationship, region and task. Verify round trips and no loss of progress.

## Gate 3: World/area lifecycle

Recover original authored areas and static world rules from the verified
resource catalog. Complete startup, enter, unlock, leave, resume and transfer
flows for Woodland, Riverside and Mountain. Compare original client rendering
and task availability in each area. Preserve stable entity IDs.

## Gate 4: Buildings, tasks and passive time

Port verified original building rules from `legacy_reference/backend/buildings.py`
and `tasks.py`; extend the domain for production and task completion based on
original data. Define precisely which tasks reward automatically and which
require player collection. Add pause/resume, long-offline catch-up and double
claim regression tests. Hosted scheduler must match local time progression.

## Gate 5: Families and multiplayer

Port villager lifecycle/needs/family/relationships. Implement consent-based
online friendship, visits and cross-world actions with transactional ownership
checks and optional self-hosted community service. Defer unsupported social
features rather than faking original results.

## Gate 6: Hardening + deployment

Load testing, crash recovery, schema migrations, privacy audit, reproducible
installer, portable Windows launcher, eventual embedded Android server,
PostgreSQL adapter if needed. All scripts and large assets stay separate.

**Definition of a releasable replacement:** complete original-client startup,
play, timed work, progression, multi-area persistence and save/restart checks
pass on multiple Windows machines/BlueStacks versions, with explicit known
deviations and safe rollback. We are not there yet.
