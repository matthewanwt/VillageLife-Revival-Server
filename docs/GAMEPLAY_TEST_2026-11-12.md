# Gameplay test on 12 November 2026

Advanced Diagnostics ran at 10:45:51 Brisbane time on BlueStacks instance `Pie64_6`. The export has 172 aggregated RPC outcomes and five unresolved 501 markers. Outcome counters span multiple sessions and can include legacy rows without request fields. The table lists the latest observation per service and failure reason, since adding those counters could double-count an older call.

## Failures observed during the latest gameplay run

| Action | Evidence | Follow-up |
| --- | --- | --- |
| Assign a shelter bed | Four 400s at 10:45:08, `shelter_bed_unknown`. Happiness timer returned 200 at 10:45:09. | The saved Woodland snapshot shows a constructed Basic Shelter with two server-side beds and eight authored shelter objects with no saved beds. Capture which object and slot the client selected and compare the emitted bed identifier with the overlay. The export omits identifier values. |
| Place decor | One 400 at 10:45:16. The request supplied the expected fields. The export collapsed the reason into `request_rejected`. | The updated export reports fixed categories for decor definition, scenery, area, position, duplicate placement, unlock, and currency failures. Decor now accepts negative X coordinates within the placement bound, since authored Woodland positions extend west of the origin. A read-only replay against the saved snapshot accepted 11 affordable visible coin items at a representative position and rejected 81 behind the authored Bridge requirement. The export cannot identify the attempted item or position. Retry the same item and location, then check persistence and balance. |
| Start crafting | Three 400s by 10:45:38. The native request uses coordinates and has no source ID. | The server now resolves the nearest recipe-compatible workshop in the active area for this request shape, then applies the existing proximity, capacity, and inventory checks. Verify start, harvest, and reload in-game. |

Startup and area loading, gathering, instant completion, harvesting, and consumption all recorded a 200 during this run. Those outcomes establish server responses. They cannot establish correct animations, UI updates, or saved results.

## Network and setup

| Observation | Interpretation |
| --- | --- |
| `Pie64` and `Pie64_6` reported matching port configuration; `Pie64_6` was selected and ADB shell was available. | The instance could be queried. |
| External default-route and DNS probes returned `not_reachable`. | Record both observations for this run. The default-route probe checks for a default route in the reported table. |
| TCP/443 over IPv4 and IPv6 and UDP availability were unmeasurable because this guest lacks toybox nc. | External reachability and isolation remain unverified. |
| `guest_to_local_verified: false` | The previous Advanced Diagnostics command never ran the local HTTP probe. The updated launcher passes its configured port and records reachable, failed, or not tested. The fresh gameplay RPCs establish that the client reached a backend during this session. |
| Earlier setup reported `VL-SIGNER-MISSING`. | Desktop TestMode setup expects the JDK under `signing-tools/jdk` relative to the test folder. This gameplay export cannot confirm a complete fresh install. |

## All services with errors in the export

Dates and times are Brisbane time. A 200 for a service records a successful server response for some input. Earlier failures still warrant targeted retests, especially fun activities, emptying beds, and tutorial completion, which remain in the unresolved 501 list alongside bed assignment and decor.

| Service | Latest observation for each error | Latest success |
| --- | --- | --- |
| `ClientTaskService/StartCraftingTask` | 400 validation_rejected (12 Nov 10:45:38) | None in export |
| `ClientUserDecorItemService/CreateUserDecorItem` | 400 request_rejected (12 Nov 10:45:16), 501 request_rejected (10 Nov 21:45:08) | None in export |
| `ClientUserShelterService/AssignBedToVillager` | 400 shelter_bed_unknown (12 Nov 10:45:08), 400 request_rejected (11 Nov 22:35:45), 501 request_rejected (10 Nov 21:44:49) | None in export |
| `ClientVillagerService/PerformFunActivity` | 501 request_rejected (11 Nov 22:30:38) | None in export |
| `ClientUserBundleService/CreateUserBundle` | 500 unspecified (10 Nov 21:45:21), 501 request_rejected (10 Nov 20:19:39) | 11 Nov 22:06:07 |
| `ClientUserShelterService/EmptyBed` | 501 request_rejected (10 Nov 20:30:58) | None in export |
| `ClientVillagerService/GetVillagerRelations` | 501 request_rejected (10 Nov 20:19:59) | 11 Nov 22:06:25 |
| `ClientVillager/Consume` | 501 request_rejected (10 Nov 20:19:33) | 12 Nov 10:45:47 |
| `ClientWant/GenerateFoodWants` | 501 request_rejected (10 Nov 20:02:42) | 12 Nov 10:45:21 |
| `ClientWant/GenerateWaterWants` | 501 request_rejected (10 Nov 20:02:42) | 12 Nov 10:45:21 |
| `ClientWant/GenerateFireWants` | 501 request_rejected (10 Nov 20:02:42) | 12 Nov 10:45:21 |
| `ClientWant/GenerateRelationshipWants` | 501 request_rejected (10 Nov 20:02:42) | 12 Nov 10:45:21 |
| `ClientWant/GenerateBirthWants` | 501 request_rejected (10 Nov 20:02:42) | 12 Nov 10:45:21 |
| `ClientWant/GenerateFunWants` | 501 request_rejected (10 Nov 20:02:42) | 12 Nov 10:45:21 |
| `ClientWant/GenerateRetirementWants` | 501 request_rejected (10 Nov 20:02:42) | 12 Nov 10:45:21 |
| `ClientWant/GenerateShelterWants` | 501 request_rejected (10 Nov 20:02:42) | 12 Nov 10:45:21 |
| `ClientWant/GenerateInteractiveWants` | 501 request_rejected (10 Nov 20:02:35) | 12 Nov 10:45:21 |
| `ClientUser/CompleteTutorial` | 501 request_rejected (10 Nov 20:02:35) | None in export |
| `ClientUser/IncreaseLevel` | 501 request_rejected (10 Nov 20:01:38) | 10 Nov 20:19:05 |
| `ClientTaskService/StartBuildingTask` | 400 task_material_requirement (10 Nov 19:51:29), 400 uncategorized (10 Nov 19:42:49), 501 uncategorized (10 Nov 19:28:29) | 10 Nov 20:30:52 |
| `ClientQuestService/AddQuest` | 501 uncategorized (10 Nov 19:42:37) | 11 Nov 22:36:18 |
| `ClientTaskService/HarvestTask` | 400 uncategorized (10 Nov 19:27:49) | 12 Nov 10:45:43 |
| `ClientTaskService/InstantCompleteTaskCurve` | 501 uncategorized (10 Nov 19:27:48) | 12 Nov 10:45:32 |
| `ClientVillagerService/SetName` | 501 uncategorized (10 Nov 18:23:40) | 11 Nov 22:06:29 |
