# Original client operation coverage (code-audit inventory)

This inventory was generated from names referenced by the supplied 2.11 Python modules. It is not a complete capture of all operations that the Android APK might call.
No historical backend modules are included in or executed by this project. Names below are compatibility targets, not copied implementations.

- Named operations referenced by historical implementation: **101** (including login and process endpoints).
- New backend exposes original HTTP login/process endpoints: **2**.
- Operation names with a dispatch path in the new backend: **65**.
- Dispatch paths explicitly known to be incomplete or scenario-limited: **32**.
- Named operations without a dispatch path in the new backend: **34**.

Having a dispatch path does **not** mean the result is gameplay-complete or verified against the real APK. Some optional operations are deliberately empty; some supported operations are tutorial-only.

## Latest supplied missing-request capture

The supplied `missing-requests (3).json` contains 27 distinct RPC names. All 27 have at least one recorded HTTP-style RPC result code 200, and `records` is empty. `ClientVillagerService/SetName` also has an earlier 501 entry, but later entries for the same operation are 200. This means each operation observed in this capture has a dispatch path; it does not prove every argument variant or gameplay mutation is complete. `object{}` request shapes imported from earlier diagnostics are unknown historical shapes, not proof that the client sent an empty object.

The observed calls are accounted for by `OPTIONAL_EMPTY`, `NORMAL_READ`, the tutorial handler, achievement response, or explicit mutation branches in `original_client/services.py`. This is the current in-capture audit:

- Analytics and optional content: `ClientAnalyticsService/Event`, `Install`, `Tutorial`, `Visit`; `ClientAdvertisement/PuppetShow`; `ClientData/GetBannerData`, `GetEmbedVideoData`, `GetGemSaleData`.
- Achievement: `ClientAchievement/GetUserAchievements`.
- Tutorial/session/settings: `ClientUserHashService/GetUserHash`, `SetActiveSequence`, `SetVillagerName`; `ClientSettingService/GetUserGameSettings`, `SaveGameSetting`; `ClientUserShelterService/ResetHappinessTimer`.
- Startup and world: `ClientStartupService/GetStartupInfo`, `GetAreaContent`; `ClientUserService/ProgressArea`.
- Village reads: `ClientMaterialService/GetUserMaterialTypes`; `ClientQuestService/GetQuests`; `ClientUserBundleService/GetUserBundles`; `ClientUserService/GetUserPayments`, `GetUserNotifications`; `ClientVillagerService/GetUserGachaVillagers`; `ClientWant/AllWants`; `ClientRequestService/GetPaginatedSentRequests`, `GetPaginatedReceivedRequests`.
- Villager mutation: `ClientVillagerService/SetName`.

The full legacy list below still contains operations that have not been dispatched or have only limited rules. Those still need porting as the tutorial and later gameplay reveal them.

## Known incomplete/conditional dispatches

- `ClientBuildingService/CreateUserBuildingTask` (foundation placement only; linked construction tasks are incomplete)
- `ClientBuildingService/DeleteUserBuildingTask`
- `ClientBuildingService/DeleteUserFunBuildingType`
- `ClientUserDecorItemService/CreateUserDecorItem` (single-currency and free placement persist in the area save, with automated replay coverage. The original client's response parsing and dual-price purchase behavior need live verification.)
- `ClientRequestService/GetPaginatedReceivedRequests`
- `ClientRequestService/GetPaginatedSentRequests`
- `ClientStartupService/GetAreaContent`
- `ClientTaskService/HarvestTask`
- `ClientTaskService/InstantCompleteTaskCurve` (authored gem curve; original client timing and all task variants still need regression verification)
- `ClientTaskService/StartBuildingTask` (table-driven construction and upgrade path; response variants need original-client verification)
- `ClientTaskService/StartCraftingTask`
- `ClientTaskService/StartFarmingTask`
- `ClientTaskService/StartGatheringTask`
- `ClientQuestService/AddQuest` (authored target validation; only material and interactive quest completion recovered)
- `ClientQuestService/CompleteQuest` (material and interactive activity objectives only)
- `ClientUser/CompleteTutorial` (local FTUE completion state only)
- `ClientUser/IncreaseLevel` (authored XP thresholds, rewards, population cap, and local wheel prize)
- `ClientWant/GenerateBirthWants`, `GenerateFireWants`, `GenerateFunWants`, `GenerateInteractiveWants`, `GenerateRelationshipWants`, `GenerateRetirementWants`, `GenerateShelterWants` (current wants preserved; event selection deferred)
- `ClientWant/GenerateFoodWants`, `GenerateWaterWants` (authored interval and material mapping; life-stage exceptions are limited)
- `ClientUserBundleService/CreateUserBundle` (commercial offers are recorded as ignored; no offer contents are granted)
- `ClientVillager/Consume` (food and water consumption only; equipment interactions are deferred)
- `ClientVillagerService/PerformFunActivity` (authored eligibility, wear, XP, energy, guaranteed rewards, and persistent weighted reward selection; live-client response variants still need verification)
- `ClientVillagerService/GetVillagerRelations` (local village family history only)
- `ClientVillagerService/GetVillagerSkills` (locally stored skill records only)
- `ClientUserService/UnlockArea`
- `ClientVillagerService/MoveVillagers`
- `ClientUserFireService/StartFire`, `OilFire` (authored fire costs/rewards; live response and timer behavior need client verification)
- `ClientUserShelterService/AssignBedToVillager`, `EmptyBed` (bed state is handled and covered by regression tests; current source fixes the bed-lookup binding; live client verification is still required)
- Shelter bed counts are generated only for templates with a recovered capacity; authored bed arrays are preserved, and unknown templates no longer receive a guessed two-slot layout.
- `ClientUserShelterService/CollectShelterHappiness`, `ResetHappinessTimer` (authored reward/timer rules; live response variants need verification)

## Not yet dispatched (return original-call 501)

- `ClientDeviceService/Push`
- `ClientFortune/ConsumeGacha`
- `ClientFortune/Gacha`
- `ClientFriendService/GetApplicationFriends`
- `ClientFriendService/GetFriendStartupInfo`
- `ClientFriendService/GetFriendStartupInfoForExtras`
- `ClientFriendService/GetFriends`
- `ClientNotification/ProcessAcceptedProposal`
- `ClientRelationship/PrepareWedding`
- `ClientRequest/AcceptDatingRequest`
- `ClientRequestService/DeleteUserRequests`
- `ClientRequestService/SendMarriageRequest`
- `ClientUser/TrackMarriageAchievement`
- `ClientUserDecorItemService/DeleteUserDecorItem`
- `ClientUserService/HandleUserMessages`
- `ClientUserService/HandleUserNotification`
- `ClientUtilityService/UpdatePosition`
- `ClientVillager/Birth`
- `ClientVillager/CanConcievePregnancy`
- `ClientVillager/CommunityDateReceived`
- `ClientVillager/DesignPregnancy`
- `ClientVillager/GetCommunityVillagers`
- `ClientVillager/ReleaseXp`
- `ClientVillager/SkipRetryConcievePregnancy`
- `ClientVillagerService/Breakup`
- `ClientVillagerService/CollectVillager`
- `ClientVillagerService/CreateGachaVillager`
- `ClientVillagerService/GetNeighborVillagers`
- `ClientVillagerService/GetPartnerVillager`
- `ClientVillagerService/OptIntoCommunity`
- `ClientVillagerService/PerformInteractiveActivity`
- `ClientVillagerService/SkipPregnancy`
- `ClientWant/GenerateChildWants`
- `ClientWant/SatisfyRelationshipWant`

## Other routed operations (require client-side regression verification)

- `ClientAchievement/GetUserAchievements`
- `ClientBuildingService/GetUserBuildingTasks`
- `ClientAdvertisement/PuppetShow`
- `ClientAdvertisement/SyncVideoWatchedCount`
- `ClientAnalyticsService/Event`
- `ClientAnalyticsService/Install`
- `ClientAnalyticsService/Tutorial`
- `ClientAnalyticsService/Visit`
- `ClientData/GetBannerData`
- `ClientData/GetEmbedVideoData`
- `ClientData/GetGemSaleData`
- `ClientMaterialService/GetUserMaterialTypes`
- `ClientQuestService/GetQuests`
- `ClientSettingService/GetUserGameSettings`
- `ClientSettingService/SaveGameSetting`
- `ClientStartupService/GetStartupInfo`
- `ClientStartupService/GetStartupInfoForExtras`
- `ClientUser/KeepActive`
- `ClientUserBundleService/GetUserBundles`
- `ClientUserHashService/GetUserHash`
- `ClientUserHashService/SetActiveSequence`
- `ClientUserHashService/SetVillagerName`
- `ClientVillagerService/SetName`
- `ClientUserService/GetUserNotifications`
- `ClientUserService/GetUserPayments`
- `ClientUserService/ProgressArea`
- `ClientUserShelterService/ResetHappinessTimer`
- `ClientWant/AllWants`

## Required acceptance evidence

1. Capture consented, redacted original-XAPK startup and gameplay sequences against the **new** server; list each operation and expected response shape.
2. Implement uncovered rules in independent new services; verify persistence, replay protection and cross-account isolation.
3. Exercise building production, tutorial completion, area transitions, family/social interactions, world reload and save migration in an actual VM.
4. Verify a narrowly scoped guest network policy with Wi-Fi enabled before allowing general beta distribution.
