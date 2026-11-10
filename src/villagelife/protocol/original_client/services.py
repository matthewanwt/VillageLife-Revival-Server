"""Original Village Life RPC compatibility without importing legacy runtime code.

Each verified operation is isolated as a service on the NEW SQLite repository.
Missing original-game mechanics return per-call 501 and appear in diagnostics.
"""
from __future__ import annotations
import copy
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
from villagelife.protocol.original_client.economy import OriginalEconomyRules
from villagelife.protocol.original_client.buildings import OriginalBuildingRules
from villagelife.protocol.original_client.randomness import new_state
from villagelife.protocol.original_client.inventory import OriginalInventoryRules
from villagelife.protocol.original_client.collection import read_collection
from villagelife.protocol.original_client.villagers import OriginalVillagerRules
from villagelife.support import record_missing, record_original_call
from villagelife.core.errors import DuplicateActionConflict
from villagelife.protocol.original_client.native_ids import mappings, translate

OPTIONAL_EMPTY={'ClientAnalyticsService/Install','ClientAnalyticsService/Tutorial',
'ClientAnalyticsService/Event','ClientAnalyticsService/Visit',
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

ECONOMY_SERVICES={'ClientMaterialService/BuyMaterialType',
                  'ClientMaterialService/BuyStoreItem',
                  'ClientMaterialService/SellMaterialType',
                  'ClientFortune/GetWOFSpinResult'}

BUILDING_SERVICES={'ClientBuildingService/CreateUserBuildingTask',
                   'ClientBuildingService/DeleteUserBuildingTask',
                   'ClientBuildingService/DeleteUserFunBuildingType'}

class OriginalClientGame:
    def __init__(self, repository:SqliteSaveRepository, definitions:OriginalDefinitions):
        self.repo=repository
        self.sessions=OriginalClientSessions(repository)
        self.tutorial=TutorialRules(definitions)
        self.world=OriginalWorldRules(definitions)
        self.areas=AreaRules(definitions)
        self.materials=OriginalInventoryRules(definitions)
        self.work=OriginalWorkRules(definitions,self.materials)
        self.economy=OriginalEconomyRules(definitions,self.materials)
        self.buildings=OriginalBuildingRules(definitions)
        self.villagers=OriginalVillagerRules()

    def login(self, request:dict)->dict:
        ident,profile,stored=self.sessions.login(request.get('deviceId'))
        if stored.get('originalSave') is None:
            fresh=self.tutorial.fresh()
            def initialize(payload):
                if payload.get('originalSave') is None:payload['originalSave']=fresh
                return {'initialized':True}
            self.repo.mutate(ident.village_id,operation_key='original:init',
                             request={'action':'initialize'},change=initialize)
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
        results=[]
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
            elif service not in TUTORIAL_SERVICES|NORMAL_READ|ECONOMY_SERVICES|BUILDING_SERVICES|{'ClientUserService/ProgressArea', 'ClientUserService/UnlockArea', 'ClientVillagerService/MoveVillagers', 'ClientVillagerService/SetName', 'ClientTaskService/StartGatheringTask', 'ClientTaskService/StartCraftingTask', 'ClientTaskService/StartFarmingTask', 'ClientTaskService/HarvestTask'}:
                code=501;message='Original gameplay rule not implemented: '+service
            else:
                try:
                    snapshot=self.repo.read_village(ident.village_id)
                    world=(snapshot.payload.get('originalSave') or {}).get('normal')
                    outward,inward=mappings(world,ident.player_id) if isinstance(world,dict) else ({},{})
                    canonical=translate(data,inward)
                    response=self._execute(ident,call,service,canonical)
                    response=translate(response,outward)
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
                try:record_original_call(self.repo,service,code,response,data)
                except Exception:pass
            results.append({'id':str(call.get('id','')),'code':code,
                            'data':response,'message':message})
        return {'code':200,'currentTime':int(time.time()),'messages':[],
                'data':{'calls':results}}

    def _execute(self, ident, call, service:str, data:dict)->dict:
        snap=self.repo.read_village(ident.village_id)
        save=snap.payload.get('originalSave')
        if not isinstance(save,dict):raise ValueError('Original tutorial not initialised; log in again')
        if service in NORMAL_READ and service!='ClientStartupService/GetAreaContent':
            return self._normal_read(save,service,data)
        if service in {'ClientUserHashService/GetUserHash',
                       'ClientSettingService/GetUserGameSettings'}:
            result, changed=self.tutorial.run(copy.deepcopy(save),service,data)
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
            if service=='ClientUserService/ProgressArea':
                if save.get('normal'):
                    raise ValueError('Initial bridge transition already completed')
                if save['userHash']['activeSequence']!=217:
                    raise ValueError('Original FTUE checkpoint 217 required')
                save['normal']=self.world.bridge(save,int(time.time()))
                save['gameSettings']={'activeSequenceId':'410','activeSequence':'410',
                     'lastViewedArea':'1'}
                result={'scenarioId':save['normal']['scenarioId'],
                        'areaId':save['normal']['areaId']}
            elif service=='ClientUserService/UnlockArea':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                result=self.areas.unlock(normal,data.get('areaId'),int(time.time()))
            elif service=='ClientStartupService/GetAreaContent':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                result=self.areas.view(normal,data.get('areaId'),int(time.time()))
            elif service in self.work.TYPES:
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                result=self.work.start(normal,service,data,int(time.time()))
            elif service=='ClientTaskService/HarvestTask':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                result=self.work.harvest(normal,data,int(time.time()))
            elif service=='ClientVillagerService/MoveVillagers':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required')
                result=self.areas.move(normal,data,int(time.time()))
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
                else:
                    result=self.buildings.delete_fun(normal,data)
            elif service=='ClientVillagerService/SetName':
                normal=save.get('normal')
                if not normal:raise ValueError('Normal world required for villager naming')
                ident,name=self.villagers.set_name(normal,data)
                for person in save.get('userHash',{}).get('data',{}).get('villagers',[]):
                    if person.get('id')==ident:
                        person['name']=name
                result={}
            else:
                result,_=self.tutorial.run(save,service,data)
            return result
        _, result, _=self.repo.mutate(ident.village_id,operation_key=operation_key,
               request={'service':service,'data':data},change=apply)
        return result

    def _normal_read(self, save:dict, service:str, data:dict)->dict:
        world=save.get('normal')
        if not isinstance(world,dict):raise ValueError('Normal village is not available yet')
        if service=='ClientStartupService/GetStartupInfo':
            return self.world.startup(world,int(time.time()))
        if service=='ClientBuildingService/GetUserBuildingTasks':
            return self.buildings.list_foundations(world)
        if service=='ClientStartupService/GetAreaContent':
            return self.world.area_content(world,data.get('areaId'),int(time.time()))
        if service=='ClientMaterialService/GetUserMaterialTypes':
            return {'user':dict(world['user']),'inventory':self.materials.list_items(world)}
        if service=='ClientVillagerService/GetUserGachaVillagers':
            return read_collection(world)
        if service=='ClientQuestService/GetQuests':return {'userQuests':list(world.get('quests',[]))}
        if service=='ClientUserBundleService/GetUserBundles':return {'userBundles':list(world.get('bundles',[]))}
        if service=='ClientUserService/GetUserPayments':return {'userPayments':list(world.get('payments',[]))}
        if service=='ClientUserService/GetUserNotifications':return {'userNotifications':list(world.get('notifications',[]))}
        if service=='ClientStartupService/GetStartupInfoForExtras':return {'OfflineConsumptionMessageModel':[]}
        if service=='ClientWant/AllWants':return {'result':list(world.get('wants',[]))}
        if service in {'ClientRequestService/GetPaginatedSentRequests','ClientRequestService/GetPaginatedReceivedRequests'}:
            key='sentRequests' if service.endswith('SentRequests') else 'receivedRequests'
            if world.get(key):raise NotImplementedError('Nonempty social request pagination requires verification')
            return {'userRequests':[]}
        raise NotImplementedError(service)
