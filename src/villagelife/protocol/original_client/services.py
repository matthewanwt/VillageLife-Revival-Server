"""Original Village Life RPC compatibility without importing legacy runtime code.

Each verified operation is isolated as a service on the NEW SQLite repository.
Missing original-game mechanics return per-call 501 and appear in diagnostics.
"""
from __future__ import annotations
import copy
import hashlib
import logging
import time
import uuid
from typing import Any
from villagelife.persistence.sqlite_store import SqliteSaveRepository
from villagelife.protocol.original_client.sessions import OriginalClientSessions
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.tutorial import TutorialRules
from villagelife.protocol.original_client.world import OriginalWorldRules
from villagelife.protocol.original_client.areas import AreaRules
from villagelife.protocol.original_client.work import OriginalWorkRules
from .buildings import OriginalBuildingRules
from villagelife.protocol.original_client.economy import OriginalEconomyRules
from villagelife.protocol.original_client.randomness import new_state
from villagelife.protocol.original_client.inventory import OriginalInventoryRules, InsufficientGems
from villagelife.protocol.original_client.collection import read_collection
from villagelife.protocol.original_client.villagers import OriginalVillagerRules
from villagelife.protocol.original_client.progression import OriginalProgressionRules
from villagelife.protocol.original_client.quests import OriginalQuestRules
from villagelife.protocol.original_client.wants import OriginalWantRules
from villagelife.protocol.original_client.habitats import SERVICES as HABITAT_SERVICES
from villagelife.protocol.original_client.fun import OriginalFunRules
from .interactive import SERVICE as INTERACTIVE_SERVICE
from .community import CommunityRules
from .family import CONCEIVE, OriginalFamilyRules, SERVICES as FAMILY_SERVICES
from .timers import gem_price
from .life_stages import ACK_MESSAGE, ACK_NOTICE, CHOOSE_SKILL, OriginalLifeStages
from .charms import OriginalBabyCharmRules, SERVICES as BABY_CHARM_SERVICES
from .marriage import OriginalMarriageRules, READS as MARRIAGE_READS, SERVICES as MARRIAGE_SERVICES
from .relationships import OriginalDatingRules, SERVICES as DATING_SERVICES
from .learning import OriginalLearningRules, SERVICES as LEARNING_SERVICES
from villagelife.support import record_missing, record_original_call
from villagelife.core.errors import DuplicateActionConflict
from villagelife.protocol.original_client.native_ids import mappings, translate

LOG = logging.getLogger(__name__)
BIRTH_COST_CHECKS = BABY_CHARM_SERVICES | {
    CONCEIVE, 'ClientStartupService/GetStartupInfo', 'ClientStartupService/GetAreaContent',
}

OPTIONAL_EMPTY={'ClientAnalyticsService/Install','ClientAnalyticsService/Tutorial',
'ClientAnalyticsService/Event','ClientAnalyticsService/Visit',
'ClientDeviceService/SetDeviceInformation',  # Acknowledge push registration for offline play.
'ClientAdvertisement/SyncVideoWatchedCount','ClientAdvertisement/PuppetShow',
'ClientData/GetEmbedVideoData','ClientData/GetBannerData',
'ClientData/GetGemSaleData'}

TUTORIAL_SERVICES={'ClientUserHashService/GetUserHash',
'ClientUserHashService/SetActiveSequence','ClientUserHashService/SetVillagerName',
'ClientSettingService/GetUserGameSettings','ClientSettingService/SaveGameSetting',
'ClientUserShelterService/ResetHappinessTimer','ClientUser/KeepActive'}

NORMAL_READ={'ClientStartupService/GetStartupInfo','ClientStartupService/GetAreaContent',
'ClientBuildingService/GetUserBuildingTasks',
'ClientMaterialService/GetUserMaterialTypes','ClientQuestService/GetQuests',
'ClientUserBundleService/GetUserBundles','ClientUserService/GetUserPayments',
'ClientUserService/GetUserNotifications','ClientStartupService/GetStartupInfoForExtras',
'ClientWant/AllWants','ClientVillagerService/GetUserGachaVillagers',
'ClientRequestService/GetPaginatedSentRequests','ClientRequestService/GetPaginatedReceivedRequests'}
NORMAL_READ |= MARRIAGE_READS
NORMAL_READ|={'ClientVillagerService/GetVillagerRelations','ClientVillagerService/GetVillagerSkills'}

ECONOMY_SERVICES={'ClientMaterialService/BuyMaterialType',
                  'ClientMaterialService/BuyStoreItem',
                  'ClientMaterialService/SellMaterialType',
                  'ClientFortune/GetWOFSpinResult'}
USER_BUNDLE_SERVICES={'ClientUserBundleService/CreateUserBundle'}
QUEST_SERVICES={'ClientQuestService/AddQuest','ClientQuestService/CompleteQuest'}
PROGRESSION_SERVICES={'ClientUser/IncreaseLevel','ClientUser/CompleteTutorial'}
WANT_SERVICES={
    'ClientWant/GenerateWaterWants','ClientWant/GenerateFoodWants',
    'ClientWant/GenerateFunWants','ClientWant/GenerateFireWants',
    'ClientWant/GenerateShelterWants','ClientWant/GenerateRetirementWants',
    'ClientWant/GenerateInteractiveWants','ClientWant/GenerateRelationshipWants',
    'ClientWant/GenerateBirthWants','ClientWant/GenerateChildWants'}

BUILDING_SERVICES={'ClientBuildingService/CreateUserBuildingTask',
                   'ClientBuildingService/DeleteUserBuildingTask',
                   'ClientBuildingService/DeleteUserFunBuildingType',
                   'ClientUserDecorItemService/CreateUserDecorItem',
                   'ClientUserDecorItemService/DeleteUserDecorItem',
                   'ClientUtilityService/UpdatePosition',
                   'ClientFarmingService/PlaceFarmPlot'} | set(OriginalBuildingRules.AREA_EQUIPMENT)
FUN_SERVICES={OriginalFunRules.SERVICE}
SKILL_SERVICES={'ClientVillagerService/BuyVillagerSkill','ClientVillagerService/BuySkillsBundle'}

class OriginalClientGame:
    def __init__(self, repository:SqliteSaveRepository, definitions:OriginalDefinitions, *, selected_village=None):
        self.repo=repository
        self.defs=definitions
        self.sessions=OriginalClientSessions(repository, selected_village=selected_village)
        self.tutorial=TutorialRules(definitions)
        self.world=OriginalWorldRules(definitions)
        self.life_stages=OriginalLifeStages(self.world)
        self.areas=AreaRules(definitions)
        self.materials=OriginalInventoryRules(definitions)
        self.work=OriginalWorkRules(definitions,self.materials)
        self.learning=OriginalLearningRules(definitions,self.materials)
        self.economy=OriginalEconomyRules(definitions,self.materials)
        self.buildings=self.work.buildings
        self.villagers=OriginalVillagerRules(definitions)
        self.progression=OriginalProgressionRules(definitions)
        self.quests=OriginalQuestRules(definitions,self.materials)
        self.wants=OriginalWantRules(definitions,self.materials)
        self.dating=OriginalDatingRules(self.world,self.wants)
        self.marriage=OriginalMarriageRules(self.dating)
        self.community=CommunityRules(repository,self.sessions,self.dating)
        self.family=OriginalFamilyRules(self.world,self.materials,self.wants)
        self.baby_charms=OriginalBabyCharmRules(self.family,self.economy)
        self.habitats=self.buildings.habitats
        self.fun=OriginalFunRules(definitions,self.materials)

    def login(self, request:dict)->dict:
        try:
            ident,profile,stored=self.sessions.login(request.get('deviceId'))
        except PermissionError as exc:
            return {'code':403,'message':str(exc),'data':{'users':[]}}
        if stored.get('originalSave') is None:
            fresh=self.tutorial.fresh()
            def initialize(payload):
                if payload.get('originalSave') is None:payload['originalSave']=fresh
                return {'initialized':True}
            self.repo.mutate(ident.village_id,operation_key='original:init',
                             request={'action':'initialize'},change=initialize)
        snapshot=self.repo.read_village(ident.village_id)
        existing_save=snapshot.payload.get('originalSave')
        existing_world=existing_save.get('normal') if isinstance(existing_save,dict) else None
        if isinstance(existing_world,dict):
            def reconcile(payload):
                save=payload.get('originalSave')
                normal=save.get('normal') if isinstance(save,dict) else None
                changed=(self.world.reconcile_authored(normal,1,int(time.time()))
                         if isinstance(normal,dict) and normal.get('areaId')==1 else False)
                if isinstance(save,dict):
                    changed=self.progression.sync_script_assignments(save) or changed
                    if isinstance(normal,dict):
                        at=int(time.time())
                        changed=self.habitats.migrate(normal,at) or changed
                        changed=self.fun.migrate(normal) or changed
                        changed=self.habitats.sync(normal,at) or changed
                return {'authoredObjectsRestored':changed}
            self.repo.mutate(ident.village_id,
                operation_key='original:migrate:habitats-v4',
                request={'action':'restore-authored-world-sync-assignments-and-real-shelter-beds','version':4},
                change=reconcile)
            if snapshot.format == 'legacy.profile+tutorial.v1':
                def restore_legacy_beds(payload):
                    normal=payload['originalSave']['normal']
                    return {'bedsRestored':self.habitats.migrate(normal,int(time.time()),legacy_import=True)}
                self.repo.mutate(ident.village_id,
                    operation_key='original:migrate:legacy-woodland-beds-v2',
                    request={'action':'restore-legacy-woodland-beds','version':2}, change=restore_legacy_beds)
            def reconcile_farm(payload):
                normal=payload['originalSave']['normal']
                return {'removedObsoleteFarmFoundation':self.buildings.reconcile_farm_foundations(normal)}
            self.repo.mutate(ident.village_id,
                operation_key='original:migrate:completed-farm-foundations-v1',
                request={'action':'reconcile-completed-farm-foundations'},
                change=reconcile_farm)
            def on_login(payload):
                normal = payload['originalSave']['normal']
                self.materials.restore_starter_tools(normal)
                self.wants.clear_ineligible_shelter_wants(normal, int(time.time()))
                self.quests.reconcile_travel(normal, int(time.time()))
                self.buildings.reconcile_boulder_foundation(normal)
                self.wants.on_login(normal, int(time.time()))
                return {}
            self.repo.mutate(ident.village_id,
                operation_key=f'original:daily-login:{ident.session_token}',
                request={'action':'daily-login'}, change=on_login)
        self.community.active_identity = ident
        return {'code':200,'data':{'users':[profile]}}

    def process(self, request:dict)->dict:
        calls=request.get('data',{}).get('calls')
        if not isinstance(calls,list) or len(calls)>250:raise ValueError('calls array required, max 250')
        if any(not isinstance(c,dict) for c in calls):raise ValueError('Every original call must be an object')
        # Validate session once before inspecting any player's save or world.
        try:ident=self.sessions.authenticate(request)
        except PermissionError:
            return {'code':200,'currentTime':int(time.time()),'messages':[],
                    'data':{'calls':[{'id':str(c.get('id','')),'code':403,'data':{},
                     'message':'Original-client session mismatch'} for c in calls]}}
        self.community.active_identity = ident
        initial = self._resolve_blocked_birthdays(self.repo.read_village(ident.village_id))
        results=[]
        check_birth_cost = False
        for call in calls:
            if not isinstance(call,dict):raise ValueError('Invalid original call')
            service=call.get('service','')
            data=call.get('data',{})
            code=200;message='';response={}
            if not isinstance(service,str) or len(service)>160 or not isinstance(data,dict):
                code=400;message='Invalid service or request body'
            elif service in OPTIONAL_EMPTY:
                response={}
            elif service=='ClientAchievement/GetUserAchievements':
                response={'result':[]}
            elif service not in TUTORIAL_SERVICES|NORMAL_READ|ECONOMY_SERVICES|LEARNING_SERVICES|BUILDING_SERVICES|QUEST_SERVICES|USER_BUNDLE_SERVICES|PROGRESSION_SERVICES|WANT_SERVICES|DATING_SERVICES|MARRIAGE_SERVICES|FAMILY_SERVICES|BABY_CHARM_SERVICES|HABITAT_SERVICES|FUN_SERVICES|SKILL_SERVICES|{CHOOSE_SKILL, INTERACTIVE_SERVICE, 'ClientStartupService/ProcessOfflineConsumption', 'ClientUserService/ProgressArea', 'ClientUserService/UnlockArea', 'ClientVillagerService/MoveVillagers', 'ClientVillagerService/SetName', 'ClientTaskService/StartGatheringTask', 'ClientTaskService/StartCraftingTask', 'ClientTaskService/StartBuildingTask', 'ClientTaskService/StartFarmingTask', 'ClientTaskService/StartFishingTask', 'ClientTaskService/StartHuntingTask', 'ClientTaskService/HarvestTask', 'ClientTaskService/InstantCompleteTaskCurve', 'ClientVillager/Consume', 'ClientVillager/ReleaseXp'}:
                code=501;message='Original gameplay rule not implemented: '+service
            else:
                try:
                    snapshot=initial if not results else self.repo.read_village(ident.village_id)
                    world=(snapshot.payload.get('originalSave') or {}).get('normal')
                    outward,inward=mappings(world,ident.player_id) if isinstance(world,dict) else ({},{})
                    canonical=translate(data,inward)
                    response=self._execute(ident,call,service,canonical,snapshot.payload.get('originalSave'),
                                           legacy_import=snapshot.format=='legacy.profile+tutorial.v1')
                    response=translate(response,outward)
                    check_birth_cost |= service in BIRTH_COST_CHECKS
                except InsufficientGems as exc:
                    code=400
                    message=str(exc)
                    response=exc.reply()
                    LOG.warning('%s', message)
                except NotImplementedError as exc:
                    code=501;message=str(exc)
                except PermissionError as exc:
                    code=403;message=str(exc)
                except DuplicateActionConflict as exc:
                    code=409;message=str(exc)
                except (ValueError,KeyError,TypeError) as exc:
                    code=400;message=str(exc)[:200]
            if code==501:
                try:record_missing(self.repo,'RPC',service,501)
                except Exception:pass
            if isinstance(service,str):
                try:record_original_call(self.repo,service,code,response,data,message)
                except Exception:pass
            results.append({'id':str(call.get('id','')),'code':code,
                            'data':response,'message':message})
        now = int(time.time())
        latest = self.repo.read_village(ident.village_id) if calls else initial
        state = (latest.payload.get('originalSave') or {}).get('normal')
        messages = []
        if check_birth_cost and isinstance(state, dict):
            self._log_unaffordable_birth(state, now)
        if isinstance(state, dict):
            notices = self.life_stages.messages(state, ident.player_id, now)
            if state.get('npcMarriageRequests'):
                notices.extend(self.marriage.messages(state, now, ident.player_id))
            if notices:
                outward, _ = mappings(state, ident.player_id)
                messages = translate(notices, outward)
        return {'code':200,'currentTime':now,'messages':messages,
                'data':{'calls':results}}

    def _resolve_blocked_birthdays(self, snapshot):
        at = int(time.time())
        state = (snapshot.payload.get('originalSave') or {}).get('normal')
        if not isinstance(state, dict):
            return snapshot
        due = sorted((person['id'], birthday)
                     for person, birthday in self.life_stages.blocked_birthdays(state, at))
        if not due:
            return snapshot
        signature = hashlib.sha256(repr(due).encode()).hexdigest()

        def resolve(payload):
            normal = payload['originalSave']['normal']
            for person, _ in self.life_stages.blocked_birthdays(normal, at):
                # The native dialog cannot submit a choice if every skill is mastered.
                self.life_stages.complete(normal, person, 0, at)
            return {}

        updated, _, _ = self.repo.mutate(snapshot.village_id, operation_key=f'original:maxed-birthday:{signature}',
                                         request={'action': 'complete-maxed-birthdays'}, change=resolve)
        return updated

    def _log_unaffordable_birth(self, state, now):
        try:
            balance = float(state.get('inventory', {}).get('323', 0))
        except (TypeError, ValueError):
            return
        for record in state.get('pregnancies', {}).values():
            if record.get('status') != 'pregnant' or not isinstance(record.get('readyAt'), int):
                continue
            try:
                cost = gem_price(self.world, record['readyAt'] - now, 'PregnancySkip')
            except KeyError:
                continue
            if balance < cost:
                LOG.warning('Birth skip costs %g gems. You have %g and need %g more. '
                            'You can close the panel and wait for the birth.',
                            cost, balance, cost - balance)
                return

    def _execute(self, ident, call, service:str, data:dict, save, *, legacy_import=False)->dict:
        if not isinstance(save,dict):raise ValueError('Original tutorial not initialised; log in again')
        if service in NORMAL_READ and service!='ClientStartupService/GetAreaContent':
            return self._normal_read(save,service,data,ident)
        if service in {'ClientUserHashService/GetUserHash',
                       'ClientSettingService/GetUserGameSettings'}:
            result, changed=self.tutorial.run(save,service,data)
            assert changed is False
            return result
        # Client RPC IDs alone are not unique across sessions. Bind to the session token.
        call_id=call.get('id')
        # When id missing, reject mutation rather than risk duplicate reward grants.
        if call_id is None or len(str(call_id))>120:raise ValueError('Valid original call ID required')
        operation_key=f'original:{ident.session_token}:{call_id}'
        def apply(payload):
            save=payload.get('originalSave')
            if not isinstance(save,dict):raise ValueError('Missing tutorial save')
            normal=save.get('normal')
            now=int(time.time())
            if normal:
                normal['lastDailyActivityAt']=max(normal.get('lastDailyActivityAt',0),now)
            if service=='ClientUserService/ProgressArea':
                if save.get('normal'):
                    raise ValueError('Initial bridge transition already completed')
                if save['userHash']['activeSequence']!=217:
                    raise ValueError('Original FTUE checkpoint 217 required')
                save['normal']=self.world.bridge(save,int(time.time()))
                self.materials.restore_starter_tools(save['normal'])
                self.habitats.migrate(save['normal'],int(time.time()))
                self.fun.migrate(save['normal'])
                save['gameSettings']={'activeSequenceId':'410','activeSequence':'410',
                     'lastViewedArea':'1'}
                result={'scenarioId':save['normal']['scenarioId'],
                        'areaId':save['normal']['areaId']}
            elif service=='ClientUserService/UnlockArea':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                result=self.areas.unlock(normal,data.get('areaId'),int(time.time()))
            elif service=='ClientUser/IncreaseLevel':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required for level-up')
                rng=save.setdefault('rng',new_state())
                result=self.progression.increase_level(normal,data,operation_key,
                                                       self.economy,rng)
            elif service=='ClientUser/CompleteTutorial':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required for tutorial completion')
                now=int(time.time())
                normal.setdefault('tutorialCompletedAt',now)
                save.setdefault('gameSettings',{})['isFtueComplete']='1'
                self.progression.sync_script_assignments(save)
                result={}
            elif service in HABITAT_SERVICES:
                normal=save.get('normal')
                if not normal and service=='ClientUserShelterService/ResetHappinessTimer':
                    result,_=self.tutorial.run(save,service,data)
                elif not normal:
                    raise ValueError('Normal world required for fire and shelter actions')
                else:
                    result,_=self.habitats.operate(normal,service,data,
                                                  int(time.time()),operation_key,legacy_import=legacy_import)
            elif service==INTERACTIVE_SERVICE:
                if not normal:raise ValueError('Normal world required for interactive activities')
                result=self.wants.interactive.perform(normal,data,now)
            elif service=='ClientStartupService/ProcessOfflineConsumption':
                if not normal:raise ValueError('Normal world required for offline consumption')
                result={'OfflineConsumptionMessageModel':normal.pop('offlineConsumption', []),
                        'inventory':self.materials.list_items(normal)}
            elif service in FUN_SERVICES:
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required for fun activities')
                rng=save.get('rng')
                if rng is None:
                    rng=save['rng']=new_state()
                result=self.fun.perform(normal,data,int(time.time()),operation_key,rng)
            elif service=='ClientUserBundleService/CreateUserBundle':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                bundle_id=data.get('bundleId')
                if isinstance(bundle_id,bool) or not isinstance(bundle_id,int):
                    raise ValueError('Bundle identifier required')
                self.defs.item('bundle',bundle_id)
                existing=next((row for row in normal.setdefault('bundles',[])
                               if row.get('bundleTypeId')==bundle_id),None)
                if existing is None:
                    existing={'bundleTypeId':bundle_id,'date':int(time.time()),'ignore':'true'}
                    normal['bundles'].append(existing)
                    normal['revision']=int(normal.get('revision',0))+1
                result={'userBundles':[copy.deepcopy(existing)]}
            elif service=='ClientVillager/ReleaseXp':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required for XP collection')
                result=self.wants.release_xp(normal,data)
            elif service=='ClientVillager/Consume':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required for consumption')
                result=self.wants.consume(normal,data,int(time.time()),operation_key)
            elif service=='ClientStartupService/GetAreaContent':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                self.buildings.reconcile_boulder_foundation(normal)
                self.quests.reconcile_travel(normal, now)
                result=self.areas.view(normal,data.get('areaId'),now)
                save.setdefault('gameSettings', {})['lastViewedArea'] = str(normal['areaId'])
                self.wants.daily.project_energy(result['areaJson']['entities'],now)
            elif service in self.work.TYPES:
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                result=self.work.start(normal,service,data,int(time.time()))
            elif service=='ClientTaskService/HarvestTask':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                result=self.work.harvest(normal,data,int(time.time()))
            elif service=='ClientTaskService/InstantCompleteTaskCurve':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                result=self.work.instant_complete(normal,data,int(time.time()))
            elif service=='ClientVillagerService/MoveVillagers':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                result=self.areas.move(normal,data,int(time.time()))
                result['inventory'] = self.materials.list_items(normal)
            elif service in LEARNING_SERVICES:
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required for material learning')
                result=self.learning.apply(normal,service,data,int(time.time()))
            elif service in ECONOMY_SERVICES:
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                now=int(time.time())
                if service=='ClientMaterialService/BuyMaterialType':
                    result=self.economy.buy_material(normal,data,operation_key)
                elif service=='ClientMaterialService/BuyStoreItem':
                    result=self.economy.buy_store_item(normal,data,operation_key)
                elif service=='ClientMaterialService/SellMaterialType':
                    result=self.economy.sell_material(normal,data,operation_key)
                else:
                    rng=save.get('rng')
                    if rng is None:
                        rng=save['rng']=new_state()
                    result=self.economy.daily_spin(normal,data,now,operation_key,
                                                   rng)
            elif service in BUILDING_SERVICES:
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                if service=='ClientBuildingService/CreateUserBuildingTask':
                    result=self.buildings.place(normal,data)
                elif service=='ClientBuildingService/DeleteUserBuildingTask':
                    result=self.buildings.delete(normal,data)
                elif service=='ClientUserDecorItemService/CreateUserDecorItem':
                    result=self.buildings.place_decor(normal,data)
                elif service=='ClientUserDecorItemService/DeleteUserDecorItem':
                    result=self.buildings.delete_decor(normal,data)
                elif service=='ClientUtilityService/UpdatePosition':
                    result=self.buildings.update_position(normal,data)
                elif service=='ClientFarmingService/PlaceFarmPlot':
                    result=self.buildings.place_farm_plot(normal,data)
                elif service in self.buildings.AREA_EQUIPMENT:
                    result=self.buildings.place_area_equipment(normal,service,data)
                else:
                    result=self.buildings.delete_fun(normal,data)
            elif service == CHOOSE_SKILL:
                if not normal:
                    raise ValueError('Normal world required for coming of age')
                result = self.life_stages.choose_skill(normal, data, now)
            elif service in SKILL_SERVICES:
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required for skill training')
                result=self.villagers.buy_skills(
                    normal,data,int(time.time()),self.materials,
                    bundle=service=='ClientVillagerService/BuySkillsBundle')
            elif service=='ClientVillagerService/SetName':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required for villager naming')
                villager_id,name=self.villagers.set_name(normal,data)
                for person in save.get('userHash',{}).get('data',{}).get('villagers',[]):
                    if person.get('id')==villager_id:
                        person['name']=name
                result={}
            elif service in QUEST_SERVICES:
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required for quest operations')
                handler=self.quests.add if service.endswith('AddQuest') else self.quests.complete
                result=handler(normal,data,int(time.time()))
            elif service in FAMILY_SERVICES | BABY_CHARM_SERVICES:
                if not normal:
                    raise ValueError('Normal world required for family operations')
                rng = save.get('rng')
                if rng is None:
                    rng = save['rng'] = new_state()
                handler = self.family if service in FAMILY_SERVICES else self.baby_charms
                result = handler.operate(normal, service, data, now, ident.player_id, rng)
            elif service in DATING_SERVICES | MARRIAGE_SERVICES:
                if not normal:
                    raise ValueError('Normal world required for relationship operations')
                if service in DATING_SERVICES:
                    rng = save.get('rng')
                    if rng is None:
                        rng = save['rng'] = new_state()
                    result = self.dating.operate(normal, service, data, now, ident.player_id,
                                                 rng, self.marriage)
                else:
                    remaining = (self.life_stages.acknowledge(normal, service, data, ident.player_id, now)
                                 if service in {ACK_MESSAGE, ACK_NOTICE} else data)
                    result = (self.marriage.operate(normal, service, remaining, now, ident.player_id)
                              if remaining is not None else {})
            elif service in WANT_SERVICES:
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required for want generation')
                result=self.wants.generate(normal,service,int(time.time()))
            else:
                result,_=self.tutorial.run(save,service,data)
                if service=='ClientSettingService/SaveGameSetting' and data.get('key') in {'activeSequence','activeSequenceId','isFtueComplete'}:
                    self.progression.sync_script_assignments(save)
                    if normal:
                        self.materials.restore_starter_tools(normal)
            return result
        _, result, _=self.repo.mutate(ident.village_id,operation_key=operation_key,
               request={'service':service,'data':data},change=apply)
        return result

    def _normal_read(self, save:dict, service:str, data:dict, ident=None)->dict:
        world=save.get('normal')
        if not isinstance(world,dict):raise ValueError('Normal village is not available yet')
        if service=='ClientStartupService/GetStartupInfo':
            now=int(time.time())
            result=self.world.startup(world,now)
            self.wants.daily.project_energy(result['world']['entities'],now)
            result['OfflineConsumptionMessageModel']=self._offline_inbox_summary()
            return result
        if service=='ClientBuildingService/GetUserBuildingTasks':
            return self.buildings.list_foundations(world)
        if service=='ClientStartupService/GetAreaContent':
            return self.world.area_content(world,data.get('areaId'),int(time.time()))
        if service=='ClientMaterialService/GetUserMaterialTypes':
            return {'user':dict(world['user']),'inventory':self.materials.list_items(world)}
        if service=='ClientVillagerService/GetUserGachaVillagers':
            return read_collection(world)
        if service=='ClientVillagerService/GetVillagerRelations':
            return self.villagers.history(world,data,int(time.time()),ident.player_id)
        if service=='ClientVillagerService/GetVillagerSkills':
            return self.villagers.skills(world,data)
        if service=='ClientQuestService/GetQuests':return {'userQuests':list(world.get('quests',[]))}
        if service=='ClientUserBundleService/GetUserBundles':return {'userBundles':list(world.get('bundles',[]))}
        if service=='ClientUserService/GetUserPayments':return {'userPayments':list(world.get('payments',[]))}
        if service in MARRIAGE_READS:
            now = int(time.time())
            result = self.marriage.read(world, service, data, now, ident.player_id)
            if service == 'ClientUserService/GetUserNotifications':
                result['userNotifications'].extend(self.life_stages.notifications(world, ident.player_id, now))
            return result
        if service=='ClientStartupService/GetStartupInfoForExtras':
            return {'OfflineConsumptionMessageModel':self._offline_inbox_summary()}
        if service=='ClientWant/AllWants':return {'result':list(world.get('wants',[]))}
        raise NotImplementedError(service)

    @staticmethod
    def _offline_inbox_summary() -> dict:
        # Client script 1971 counts a nonzero summary as a request, but its
        # consumption panel (script 3400) is a no-op in this client.
        return {'DrinksQuantity': 0, 'FoodQuantity': 0, 'TotalXp': 0}
