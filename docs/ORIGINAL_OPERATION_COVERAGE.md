# Original client operation coverage (code-audit inventory)

This inventory was generated from names referenced by the supplied 2.11 Python modules. It is not a complete capture of all operations that the Android APK might call.
No historical backend modules are included in or executed by this project. Names below are compatibility targets, not copied implementations.

- Named operations referenced by historical implementation: **101** (including login and process endpoints).
- New backend exposes original HTTP login/process endpoints: **2**.
- Operation names with a dispatch path in the new backend: **45**.
- Dispatch paths explicitly known to be incomplete or scenario-limited: **12**.
- Named operations without a dispatch path in the new backend: **53**.

Having a dispatch path does **not** mean the result is gameplay-complete or verified against the real APK. Some optional operations are deliberately empty; some supported operations are tutorial-only.

## Known incomplete/conditional dispatches

- `ClientBuildingService/CreateUserBuildingTask` (foundation placement only; linked construction tasks are incomplete)
- `ClientBuildingService/DeleteUserBuildingTask`
- `ClientBuildingService/DeleteUserFunBuildingType`
- `ClientRequestService/GetPaginatedReceivedRequests`
- `ClientRequestService/GetPaginatedSentRequests`
- `ClientStartupService/GetAreaContent`
- `ClientTaskService/HarvestTask`
- `ClientTaskService/StartCraftingTask`
- `ClientTaskService/StartFarmingTask`
- `ClientTaskService/StartGatheringTask`
- `ClientUserService/UnlockArea`
- `ClientVillagerService/MoveVillagers`

## Not yet dispatched (return original-call 501)

- `ClientDeviceService/Push`
- `ClientFortune/ConsumeGacha`
- `ClientFortune/Gacha`
- `ClientFriendService/GetApplicationFriends`
- `ClientFriendService/GetFriendStartupInfo`
- `ClientFriendService/GetFriendStartupInfoForExtras`
- `ClientFriendService/GetFriends`
- `ClientNotification/ProcessAcceptedProposal`
- `ClientQuestService/AddQuest`
- `ClientQuestService/CompleteQuest`
- `ClientRelationship/PrepareWedding`
- `ClientRequest/AcceptDatingRequest`
- `ClientRequestService/DeleteUserRequests`
- `ClientRequestService/SendMarriageRequest`
- `ClientTaskService/InstantCompleteTaskCurve`
- `ClientTaskService/StartBuildingTask`
- `ClientUser/CompleteTutorial`
- `ClientUser/IncreaseLevel`
- `ClientUser/TrackMarriageAchievement`
- `ClientUserBundleService/CreateUserBundle`
- `ClientUserDecorItemService/CreateUserDecorItem`
- `ClientUserDecorItemService/DeleteUserDecorItem`
- `ClientUserFireService/OilFire`
- `ClientUserFireService/StartFire`
- `ClientUserService/HandleUserMessages`
- `ClientUserService/HandleUserNotification`
- `ClientUserShelterService/AssignBedToVillager`
- `ClientUserShelterService/CollectShelterHappiness`
- `ClientUserShelterService/EmptyBed`
- `ClientUtilityService/UpdatePosition`
- `ClientVillager/Birth`
- `ClientVillager/CanConcievePregnancy`
- `ClientVillager/CommunityDateReceived`
- `ClientVillager/Consume`
- `ClientVillager/DesignPregnancy`
- `ClientVillager/GetCommunityVillagers`
- `ClientVillager/ReleaseXp`
- `ClientVillager/SkipRetryConcievePregnancy`
- `ClientVillagerService/Breakup`
- `ClientVillagerService/CollectVillager`
- `ClientVillagerService/CreateGachaVillager`
- `ClientVillagerService/GetNeighborVillagers`
- `ClientVillagerService/GetPartnerVillager`
- `ClientVillagerService/GetVillagerRelations`
- `ClientVillagerService/GetVillagerSkills`
- `ClientVillagerService/OptIntoCommunity`
- `ClientVillagerService/PerformFunActivity`
- `ClientVillagerService/PerformInteractiveActivity`
- `ClientVillagerService/SkipPregnancy`
- `ClientWant/GenerateBirthWants`
- `ClientWant/GenerateChildWants`
- `ClientWant/GenerateInteractiveWants`
- `ClientWant/GenerateRelationshipWants`
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
