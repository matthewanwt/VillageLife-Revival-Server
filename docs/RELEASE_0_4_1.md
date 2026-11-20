# Village Life Community Update 0.4.1

This update brings the improvements developed since the last public release,
0.3.6, together with the latest community ticket fixes.

## What's changed

- Improved handling of long-running saves: completed action history is stored
  separately and compressed when appropriate, while active village data stays
  smaller. Routine building, transfer, feeding and travel checks avoid repeatedly
  scanning old completed actions. History and reward replay protection are retained.
- Reduced repeated data loading, definition parsing and diagnostic writes. Added
  action timing information to help investigate delays on affected computers.
- Updated launcher with separate pages for playing, villages, backups, setup and
  diagnostics, clearer progress and recovery actions, and bounded log display.
- More reliable setup and shutdown: verified game/expansion files, cancellation
  handling, protection against competing launchers, and cleanup of owned processes.
- Improved BlueStacks discovery, including custom installation locations.
- Restored the free starter tools' everlasting markers, including Riverside use.
- Fixed the two-bed layout for known Woodland hero homes in new villages as well
  as imported villages, and fixed separate workshops replacing an existing one.
- Improved skill compatibility and recovery from recorded charm/birth data.
  Starter skill restoration uses a stable fallback where the original choices
  were not saved. Existing recorded choices and purchased ranks are preserved.
- Food and shelter wishes now account for the villager's current village area.
- Fixed stale pregnancy state handling and disabled zero-chance rescue reward
  rows that could prevent otherwise supported tasks from completing.
- Added local-server request protections, bounded resource handling, and build
  provenance/checksums. This is not a network-isolation certification.

## Updating and keeping your save

1. Close the game and old launcher. Keep a separate copy of your save folder:
   `%LOCALAPPDATA%\VillageLifeRevivalNext`.
2. Run `VillageLife-Community-0.4.1-Setup.exe`, then open the launcher and click
   **Play**. Existing local villages adapt automatically after a full recovery
   backup is created. Follow guided setup if the Android client needs preparing.
3. Use **My Villages** to select an existing village, including after changing
   BlueStacks instances. For an original 0.2.6 backup, use **Import 0.2.6 Save**
   and select the extracted `private_state` folder. Keep the original backup.

The new history format requires this newer server. If returning to an older
launcher, use the pre-migration recovery backup, not the migrated database.
Migration does not automatically shrink the database file on disk; freed space
is reused. Backups are separate. No village reset is required.

## Download and known limits

The setup EXE includes the original game XAPK and its OBB expansion, the Windows
launcher, local server and signing tools. BlueStacks with a Pie 64-bit instance
is still required; no separate game archive download is needed.

The Windows installer is unsigned. Launcher text is currently English. Some
seasonal/clothing features, distorted audio on affected instances and reported
visual/input stalls remain under investigation. Server improvements do not
guarantee a particular frame rate or speed multiplier on every computer.

Validation includes 180 automated tests, large-save performance checks, dependency
audits and a packaged-server smoke check. These do not replace testing every
gameplay interaction on every BlueStacks version. If a problem remains, export
the latest session through **Diagnostics** and send the report privately.
