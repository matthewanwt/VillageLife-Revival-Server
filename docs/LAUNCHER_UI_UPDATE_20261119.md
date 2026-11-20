# Launcher interface update — 19 November 2026

Reorganised the existing Windows Forms launcher into Play, My Villages,
Backups, Help and Settings. Retained familiar Windows controls and the existing
setup, import, gem validation and owned-process cleanup logic.

## Behaviour

- Play shows the selected village, saved BlueStacks selection and last recorded
  database save time. Connection is explicitly checked on Play; a saved selection
  is not presented as a verified live connection.
- Guided Play updates four explicit checklist checkpoints. Cancelling setup keeps
  the completed checkpoints visible and lets the player resume.
- My Villages lists the local villages and imported copies. Use selected village
  persists the chosen slot without starting the game or deleting another village.
- Back up now invokes the existing consistent whole-database backup operation.
  Success is displayed only after that operation succeeds. Recovery guidance and
  folder access are provided; this update does not add an automatic restore wizard.
- Errors appear inline with Retry, Help and Technical log. Failed detail reads do
  not claim that a save is missing. Successful retries remove the error message.
- Long operations show activity and elapsed time, rather than fabricated transfer
  percentages. Logs remain bounded and batched under Help.
- Village details refresh on opening/requested actions, with no new database
  polling loop during gameplay. Displayed save times are labelled as snapshots.
- Buttons wrap and pages scroll at smaller sizes. Standard Windows system colours
  and meaningful accessibility group names are used. Launcher language is English.

## Validation

- Existing repository regression suite: **136 tests passed**.
- Self-contained Windows launcher compilation/publish succeeded.
- Native desktop checks covered all five pages, normal and small windows, scrolling,
  guided Play opening the instance chooser, setup/chooser cancellation, manual
  backup, invalid gem input, direct village selection, technical log access,
  deliberate missing-server failure and successful Retry, and clean window close.
- The UI-created backup passed SQLite integrity checking and retained the same
  village payloads as its source. Invalid gem entry did not change those payloads.
- All interaction tests used a copied private test village. No BlueStacks instance
  was bound, installed into or modified. Full gameplay was not repeated in this pass.
- A NuGet advisory-service connection warning occurred during the cached build.
  There are no new package dependencies; this is not a fresh dependency audit.

## Delivery

Source changes are in `windows/launcher/Program.cs`, `GuidedSetup.cs` and the new
`Dashboard.cs`. They remain uncommitted and unpublished along with the existing
audit work. The public version label has not been advanced.

The runnable preview is under `experiments/Launcher UI Preview 20261119` in the
restoration workspace. Run `Try Updated Launcher.cmd` to use its separate save.
It includes the previously validated server/game payload and the newly built
launcher. The previous private audit installer is unchanged and does not contain
this interface update. No public installer/release was replaced.
