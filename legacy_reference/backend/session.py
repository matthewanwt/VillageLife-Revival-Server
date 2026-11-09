"""Private local sessions and original tutorial-state persistence.

Implements observed tutorial and normal startup contracts; economy simulation remains incomplete.
"""
import datetime,hashlib,json,threading,uuid,sqlite3,os,time
from pathlib import Path
from functools import lru_cache
from contextlib import closing
import world as world_model
import tasks as task_model
import buildings as building_model
import progression as progression_model
import quests as quest_model
import needs as needs_model
import shop as shop_model
import learning as learning_model
import fortune as fortune_model
import collection as collection_model
import interactive as interactive_model
import charms as charm_model
import areas as area_model
import placement as placement_model
import fun as fun_model
import social as social_model
import habitats as habitat_model
import starter_tools as starter_tool_model
import family as family_model
import relationships as relationship_model
import marriage as marriage_model
LOCK=threading.RLock()
STATE=Path(__file__).resolve().parent/'private_state'
DATABASE=Path(__file__).resolve().parents[1]/'analysis/private/game_tables.sqlite'

def now():return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def wire_time():return int(time.time())
def numeric_time(value):
 if isinstance(value,int):return value
 return int(datetime.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp())
def profile_path(device):return STATE/(hashlib.sha256(device.encode()).hexdigest()+'.json')
def atomic_json(path,value):
 path.parent.mkdir(exist_ok=True,parents=True)
 temporary=path.with_suffix(path.suffix+'.tmp')
 with temporary.open('w',encoding='utf8',newline='\n') as f:
  json.dump(value,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(temporary,path)

def login(request):
 device=str(request.get('deviceId',''))
 if not device:raise ValueError('deviceId required')
 with LOCK:
  path=profile_path(device)
  if path.exists():profile=json.loads(path.read_text(encoding='utf8'))
  else:
   profile={'pId':str(uuid.uuid4().int >> 80),'fbId':'','zId':'','deviceId':device,'sessionId':uuid.uuid4().hex,'fbHashId':'','scenarioId':1,'userLevelId':0,'fbDeviceConnectedAt':0,'createdAt':wire_time(),'isNewUser':True}
   atomic_json(path,profile)
  if request.get('_accountName'):
   profile['sessionId']=uuid.uuid4().hex;atomic_json(path,profile)
  if request.get('_accountName') and profile.get('displayName')!=request['_accountName']:
   profile['displayName']=request['_accountName'];atomic_json(path,profile)
 state_path=path.with_suffix('.tutorial.json')
 if state_path.exists():
  with LOCK:
   saved=json.loads(state_path.read_text(encoding='utf8'));normal=saved.get('normal')
   if normal:
    changed=world_model.migrate_level_numbers(normal)
    changed=world_model.migrate_authored_area(normal) or changed
    changed=fun_model.migrate(normal) or changed
    changed=progression_model.reconcile_level_rewards(normal) or changed
    changed=habitat_model.migrate(normal,wire_time()) or changed
    changed=habitat_model.sync(normal,wire_time()) or changed
    changed=starter_tool_model.recover(normal,wire_time()) or changed
    if needs_model.reconcile_fun_wishes(normal,wire_time()):normal['revision']+=1;changed=True
    if normal:saved['requestEpoch']=uuid.uuid4().hex;changed=True
    if changed:atomic_json(state_path,saved)
  if normal:profile={**profile,'scenarioId':normal['scenarioId'],'userLevelId':normal['user']['userLevelID'],'isNewUser':False}
 profile={**profile,'fbDeviceConnectedAt':numeric_time(profile['fbDeviceConnectedAt']),'createdAt':numeric_time(profile['createdAt'])}
 return {'code':200,'data':{'users':[profile]}}

# Empty optional offers are a deliberate local deployment configuration.
OPTIONAL_EMPTY={'ClientAnalyticsService/Install','ClientAnalyticsService/Tutorial','ClientAnalyticsService/Event','ClientAnalyticsService/Visit','ClientAdvertisement/SyncVideoWatchedCount','ClientAdvertisement/PuppetShow','ClientData/GetEmbedVideoData','ClientData/GetBannerData','ClientData/GetGemSaleData'}

def validate_character_ids(records):
 ids=[v.get('id') for v in records]
 if any(not isinstance(v,str) or not v or len(v.encode('utf8'))>128 for v in ids):raise ValueError('Every character requires a non-empty native id')
 if len(ids)!=len(set(ids)):raise ValueError('Character ids must be unique across the saved village')

@lru_cache(maxsize=1)
def _fresh_tutorial_json():
 villagers=[]
 with closing(sqlite3.connect('file:'+str(DATABASE)+'?mode=ro',uri=True)) as conn:
  steps=[json.loads(v[0]) for v in conn.execute("select fields_json from game_rows r join game_tables t on r.table_id=t.id where t.name='seq_state_tablet_ftue'")]
  required={json.loads(v['dataJSON'])['refId'] for v in steps if v['sequenceType']=='62'}
  rows=conn.execute("select fields_json from game_rows r join game_tables t on r.table_id=t.id where t.name='villager_starting_variation' order by r.ordinal")
  for row in rows:
   value=json.loads(row[0]);ref=value['refId']
   # Match the authored child class from introduction, avoiding an adult-to-child jump.
   if ref=='sister' and (value['villagerType']!='11' or not 5<=int(value['startAge'])<=12):continue
   if ref in required and not any(v['refId']==ref for v in villagers):
    villagers.append({'id':ref,'refId':ref,'name':value['name'],'variationId':int(value['id'])})
 assert {v['refId'] for v in villagers}==required
 return json.dumps({'userHash':{'activeSequence':0,'segmentId':0,'data':{'villagers':villagers}}})

def fresh_tutorial():
 # Each player receives a separate mutable copy of the immutable cached seed.
 return json.loads(_fresh_tutorial_json())

@lru_cache(maxsize=1)
def tutorial_sequences():
 with closing(sqlite3.connect('file:'+str(DATABASE)+'?mode=ro',uri=True)) as conn:
  rows=[json.loads(row[0]) for row in conn.execute("select r.fields_json from game_rows r join game_tables t on r.table_id=t.id where t.name='seq_state_tablet_ftue'")]
  # Some original persist targets point beyond this table's direct records.
  # They are still legitimate client-issued checkpoints, not invalid input.
  return {int(row['id']) for row in rows}|{int(row['persist']) for row in rows if int(row['persist'])>0}

def authenticated_tutorial_path(request):
 device=str(request.get('deviceId',''))
 if not device:raise PermissionError('Local session required')
 path=profile_path(device)
 if not path.exists():raise PermissionError('Local session not found')
 profile=json.loads(path.read_text(encoding='utf8'))
 if not request.get('sessionId') or request['sessionId']!=profile['sessionId'] or str(request.get('pId',''))!=profile['pId']:
  raise PermissionError('Local session mismatch')
 return path.with_suffix('.tutorial.json')

def tutorial_operation(request,service,data,call_id=None):
 with LOCK:
  path=authenticated_tutorial_path(request)
  saved=json.loads(path.read_text(encoding='utf8')) if path.exists() else {'version':1,**fresh_tutorial()}
  if saved.get('normal'):
   changed=world_model.migrate_level_numbers(saved['normal'])
   changed=world_model.migrate_authored_area(saved['normal']) or changed
   changed=world_model.repair_starter_family(saved['normal']) or changed
   changed=collection_model.migrate_skills(saved['normal']) or changed
   changed=fun_model.migrate(saved['normal']) or changed
   changed=habitat_model.migrate(saved['normal'],wire_time()) or changed
   changed=habitat_model.sync(saved['normal'],wire_time()) or changed
   changed=progression_model.sync_inventory_assignments(saved) or changed
   if changed:atomic_json(path,saved)
  world=saved['userHash']
  migrated=False
  for villager in world['data']['villagers']:
   if not villager.get('id'):
    villager['id']=villager['refId'];migrated=True
  for original in fresh_tutorial()['userHash']['data']['villagers']:
   if not any(v['refId']==original['refId'] for v in world['data']['villagers']):
    world['data']['villagers'].append(original);migrated=True
  if migrated:
   saved['version']=3;atomic_json(path,saved)
  validate_character_ids(world['data']['villagers'])
  if service in social_model.SERVICES:
   profile=json.loads(profile_path(str(request['deviceId'])).read_text(encoding='utf-8'))
   return social_model.native_response(STATE,profile,saved.get('normal'),service,data)
  if service in marriage_model.SERVICES:
   if not saved.get('normal'):raise ValueError('Normal world required for marriage')
   import copy
   candidate=copy.deepcopy(saved['normal'])
   response,changed=marriage_model.operate(candidate,service,data,wire_time(),str(request['pId']))
   if changed:world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service in relationship_model.SERVICES:
   if not saved.get('normal'):raise ValueError('Normal world required for relationships')
   import copy
   candidate=copy.deepcopy(saved['normal'])
   response,changed=relationship_model.operate(candidate,service,data,wire_time(),str(request['pId']))
   if changed:world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service in family_model.READ_SERVICES:
   if not saved.get('normal'):raise ValueError('Normal world required for family history')
   if service.endswith('/GetVillagerSkills'):return family_model.skills(saved['normal'],data)
   return family_model.history(saved['normal'],data,wire_time(),str(request['pId']))
  if service in area_model.SERVICES:
   if not saved.get('normal'):raise ValueError('Normal village required for area access')
   import copy
   candidate=copy.deepcopy(saved['normal']);at=wire_time()
   key=str(saved.get('requestEpoch','initial'))+':'+str(call_id) if call_id is not None else None
   response,changed=area_model.unlock(candidate,data,at) if service.endswith('/UnlockArea') else area_model.move(candidate,data,at,key,str(request['pId']))
   if changed:world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service in family_model.SERVICES:
   if not saved.get('normal'):raise ValueError('Normal world required for family actions')
   import copy
   candidate=copy.deepcopy(saved['normal']);key=str(saved.get('requestEpoch','initial'))+':'+str(call_id) if call_id is not None else None
   response,changed=family_model.operate(candidate,service,data,wire_time(),str(request['pId']),key)
   if changed:
    world_model.validate_world(candidate);saved['normal']=candidate
    if service.endswith('/SetName'):
     for person in world['data']['villagers']:
      if person['id']==data.get('villagerId'):person['name']=family_model.actor(candidate,person['id'])['name']
    atomic_json(path,saved)
   return response
  if service in habitat_model.SERVICES and saved.get('normal'):
   import copy
   candidate=copy.deepcopy(saved['normal']);key=str(saved.get('requestEpoch','initial'))+':'+str(call_id) if call_id is not None else None
   response,changed=habitat_model.operate(candidate,service,data,wire_time(),key)
   if changed:world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service=='ClientUser/KeepActive':
   at=wire_time()
   if at>saved.get('lastActiveAt',0):saved['lastActiveAt']=at;atomic_json(path,saved)
   return {}
  if service=='ClientVillagerService/PerformFunActivity':
   if not saved.get('normal'):raise ValueError('Normal world required')
   import copy
   candidate=copy.deepcopy(saved['normal']);key=str(saved.get('requestEpoch','initial'))+':'+str(call_id)
   response,changed=fun_model.perform(candidate,data,wire_time(),key)
   if changed:world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service in {'ClientMaterialService/BuyMaterialType','ClientMaterialService/SellMaterialType','ClientMaterialService/BuyStoreItem'}:
   if not saved.get('normal'):raise ValueError('Normal world required')
   import copy
   candidate=copy.deepcopy(saved['normal'])
   receipt_key=str(saved.get('requestEpoch','initial'))+':'+str(call_id) if call_id is not None else ''
   response,changed=(shop_model.sell if service.endswith('SellMaterialType') else shop_model.buy_store if service.endswith('BuyStoreItem') else shop_model.buy)(candidate,data,receipt_key)
   if changed:world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service in interactive_model.SERVICES:
   if not saved.get('normal'):raise ValueError('Normal village required for interactive activities')
   import copy
   candidate=copy.deepcopy(saved['normal'])
   if service.endswith('GenerateInteractiveWants'):response,changed=interactive_model.generate(candidate,wire_time())
   else:response,changed=interactive_model.perform(candidate,data,wire_time(),str(saved.get('requestEpoch','initial'))+':'+str(call_id) if call_id is not None else None)
   if changed:world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service in placement_model.SERVICES:
   if not saved.get('normal'):raise ValueError('Normal village required for placement')
   import copy
   candidate=copy.deepcopy(saved['normal'])
   response,changed=placement_model.operate(candidate,service,data,str(saved.get('requestEpoch','initial'))+':'+str(call_id) if call_id is not None else None)
   if changed:world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service in charm_model.SERVICES:
   if not saved.get('normal'):raise ValueError('Normal village required for charms')
   import copy
   candidate=copy.deepcopy(saved['normal'])
   response,changed=charm_model.operate(candidate,service,data,wire_time(),str(request['pId']),str(saved.get('requestEpoch','initial'))+':'+str(call_id) if call_id is not None else None)
   if changed:world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service in collection_model.SERVICES:
   if not saved.get('normal'):raise ValueError('Normal village required for collection purchases')
   import copy
   candidate=copy.deepcopy(saved['normal'])
   response,changed=collection_model.operate(candidate,service,data,wire_time(),str(request['pId']),str(saved.get('requestEpoch','initial'))+':'+str(call_id) if call_id is not None else None)
   if changed:world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service in fortune_model.SERVICES:
   if not saved.get('normal'):raise ValueError('Normal village required for fortune')
   import copy
   candidate=copy.deepcopy(saved['normal'])
   response,changed=fortune_model.operate(candidate,service,data,wire_time(),str(saved.get('requestEpoch','initial'))+':'+str(call_id) if call_id is not None else None)
   if changed:world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service in learning_model.SERVICES:
   if not saved.get('normal'):raise ValueError('Normal world required for learning')
   import copy
   candidate=copy.deepcopy(saved['normal'])
   response,changed=learning_model.operate(candidate,service,data,wire_time())
   if changed:world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service=='ClientUserBundleService/CreateUserBundle':
   if not saved.get('normal'):raise ValueError('Normal world required')
   ident=data.get('bundleId')
   if isinstance(ident,bool) or not isinstance(ident,int):raise ValueError('Bundle identifier required')
   try:world_model.by_id('bundle',ident)
   except StopIteration:raise ValueError('Unknown bundle') from None
   normal=saved['normal'];existing=next((v for v in normal['bundles'] if v['bundleTypeId']==ident),None)
   if existing is None:
    # Local preservation configuration suppresses commercial offers, never awards their contents.
    existing={'bundleTypeId':ident,'date':wire_time(),'ignore':'true'};normal['bundles'].append(existing);normal['revision']+=1;atomic_json(path,saved)
   return {'userBundles':[dict(existing)]}
  if service in NEED_SERVICES:
   if not saved.get('normal'):raise ValueError('Normal world required for needs')
   import copy
   candidate=copy.deepcopy(saved['normal'])
   if service=='ClientVillager/Consume':response,changed=needs_model.consume(candidate,data,wire_time(),str(saved.get('requestEpoch','initial'))+':'+str(call_id) if call_id is not None else None)
   elif service=='ClientVillager/ReleaseXp':response,changed=needs_model.release_xp(candidate,data)
   else:response,changed=needs_model.generate(candidate,service,wire_time())
   if changed:
    world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service in PROGRESSION_SERVICES or service in QUEST_SERVICES:
   if not saved.get('normal'):raise ValueError('Normal world required')
   import copy
   candidate=copy.deepcopy(saved['normal'])
   if service=='ClientUser/IncreaseLevel':response,changed=progression_model.increase_level(candidate,data,str(saved.get('requestEpoch','initial'))+':'+str(call_id) if call_id is not None else None)
   elif service=='ClientUser/CompleteTutorial':
    changed='tutorialCompletedAt' not in candidate or str(saved.get('gameSettings',{}).get('isFtueComplete','')).lower() not in {'1','true'};candidate.setdefault('tutorialCompletedAt',wire_time());response={}
    saved.setdefault('gameSettings',{})['isFtueComplete']='1'
   else:response,changed=(quest_model.add if service.endswith('AddQuest') else quest_model.complete)(candidate,data,wire_time())
   if changed:
    world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service in BUILDING_SERVICES:
   if not saved.get('normal'):raise ValueError('Normal world required for building')
   if service.endswith('GetUserBuildingTasks'):return building_model.list_foundations(saved['normal'])
   import copy
   candidate=copy.deepcopy(saved['normal']);handler=building_model.delete_fun if service.endswith('DeleteUserFunBuildingType') else building_model.delete if service.endswith('DeleteUserBuildingTask') else building_model.place
   response,changed=handler(candidate,data)
   if changed:
    world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
   return response
  if service in TASK_SERVICES:
   if not saved.get('normal'):raise ValueError('Normal world required for gathering')
   # Work on a copy so validation failures cannot partially spend materials.
   import copy
   candidate=copy.deepcopy(saved['normal'])
   receipt_key=str(saved.get('requestEpoch','initial'))+':'+str(call_id) if call_id is not None else None
   response,changed=(task_model.instant_complete(candidate,data,wire_time()) if service.endswith('InstantCompleteTaskCurve') else task_model.harvest(candidate,data,wire_time()) if service.endswith('HarvestTask') else task_model.start(candidate,data,wire_time(),service,receipt_key))
   if changed:
    saved['normal']=candidate;saved['updatedAt']=now();atomic_json(path,saved)
   return response
  if service=='ClientUserService/ProgressArea':
   if 'normal' not in saved:
    if world['activeSequence']!=217:raise ValueError('Bridge checkpoint 217 required for first area transition')
    saved['normal']=world_model.build_bridge_world(saved,wire_time())
    saved['schemaVersion']=4
    saved.setdefault('gameSettings',{}).update({'activeSequenceId':'410','activeSequence':'410','lastViewedArea':'1','isFtueComplete':'false','hoursPerYear':world_model.global_value('hours_per_year')})
    saved['updatedAt']=now();atomic_json(path,saved)
   elif saved.get('gameSettings',{}).get('activeSequenceId')!='410':
    raise ValueError('Later area progression is not implemented; existing bridge transition cannot be reused')
   return {'scenarioId':saved['normal']['scenarioId'],'areaId':saved['normal']['areaId']}
  if service in NORMAL_READ_SERVICES:
   normal=saved.get('normal')
   if normal is None:raise ValueError('Normal world has not been created by the bridge transition')
   if service=='ClientStartupService/GetAreaContent':
    import copy
    candidate=copy.deepcopy(normal);at=wire_time();changed=area_model.view(candidate,data.get('areaId'),at)
    response=world_model.area_content(candidate,data.get('areaId'),at)
    if changed:saved['normal']=candidate;saved.setdefault('gameSettings',{})['lastViewedArea']=str(candidate['areaId']);atomic_json(path,saved)
    return response
   if service=='ClientUserService/GetUserNotifications':return {'userNotifications':list(normal.get('notifications',[]))}
   if service in {'ClientRequestService/GetPaginatedSentRequests','ClientRequestService/GetPaginatedReceivedRequests'}:
    count=data.get('count',500)
    if isinstance(count,bool) or not isinstance(count,int) or not 1<=count<=500:raise ValueError('Invalid request page size')
    key='sentRequests' if service.endswith('SentRequests') else 'receivedRequests'
    records=normal.get(key,[])
    if records:raise ValueError('Nonempty request pagination is not implemented')
    return {'userRequests':[]}
   if service=='ClientWant/AllWants':return {'result':list(normal.get('wants',[]))}
   if service=='ClientStartupService/GetStartupInfo':return world_model.startup(normal,wire_time())
   if service=='ClientMaterialService/GetUserMaterialTypes':return {'user':dict(normal['user']),'inventory':task_model.inventory(normal)}
   if service=='ClientQuestService/GetQuests':return {'userQuests':list(normal['quests'])}
   if service=='ClientUserBundleService/GetUserBundles':return {'userBundles':list(normal['bundles'])}
   if service=='ClientUserService/GetUserPayments':return {'userPayments':list(normal['payments'])}
   if service=='ClientStartupService/GetStartupInfoForExtras':return {'OfflineConsumptionMessageModel':[]}
   if service=='ClientVillagerService/GetUserGachaVillagers':return collection_model.read(normal)
  if service=='ClientUserHashService/GetUserHash':return {'userHash':world}
  if service=='ClientUserHashService/SetActiveSequence':
   value=data.get('activeSequence')
   if isinstance(value,bool) or not isinstance(value,int) or value not in tutorial_sequences():raise ValueError('Unknown original tutorial checkpoint')
   world['activeSequence']=value
  elif service=='ClientUserHashService/SetVillagerName':
   ref=str(data.get('villagerId',''));name=data.get('name')
   if not isinstance(name,str) or not name.strip() or len(name.encode('utf8'))>64 or any(ord(ch)<32 for ch in name):raise ValueError('Invalid villager name')
   villager=next((v for v in world['data']['villagers'] if v['id']==ref or v['refId']==ref),None)
   if villager is None:raise ValueError('Unknown tutorial villager reference')
   villager['name']=name
   if saved.get('normal'):
    for actor in saved['normal']['world']['entities']:
     if actor['id']==villager['id']:actor['name']=name
    saved['normal']['revision']+=1
  elif service=='ClientSettingService/GetUserGameSettings':
   settings=dict(saved.get('gameSettings',{}))
   # Both names feed the same native resume field; never emit a stale legacy value.
   if 'activeSequenceId' in settings:settings['activeSequence']=settings['activeSequenceId']
   return {'gameSettings':[{'key':key,'value':value} for key,value in settings.items()]}
  elif service=='ClientSettingService/SaveGameSetting':
   key=data.get('key');value=data.get('value')
   if not isinstance(key,str) or not key or len(key)>128 or not isinstance(value,(str,int,float,bool)) or len(str(value).encode('utf8'))>65536:raise ValueError('Invalid game setting')
   saved.setdefault('gameSettings',{})[key]=str(value).lower() if isinstance(value,bool) else str(value)
   if key in {'activeSequence','activeSequenceId'}:
    saved['gameSettings']['activeSequence']=str(value);saved['gameSettings']['activeSequenceId']=str(value)
    progression_model.sync_inventory_assignments(saved)
  elif service=='ClientUserShelterService/ResetHappinessTimer':
   shelter=data.get('userShelterId')
   if not isinstance(shelter,str) or not shelter or len(shelter)>128 or any(ord(ch)<32 for ch in shelter):raise ValueError('Invalid shelter identifier')
   record=saved.setdefault('shelters',{}).setdefault(shelter,{'id':shelter})
   record['happinessCollectedAt']=wire_time()
  else:raise NotImplementedError(service)
  saved['updatedAt']=now()
  atomic_json(path,saved)
  with path.with_suffix('.history.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps({'utc':now(),'service':service,'data':data},ensure_ascii=False)+'\n')
  return {'userShelter':dict(record)} if service=='ClientUserShelterService/ResetHappinessTimer' else {}

NORMAL_READ_SERVICES={'ClientStartupService/GetAreaContent','ClientUserService/GetUserNotifications','ClientRequestService/GetPaginatedSentRequests','ClientRequestService/GetPaginatedReceivedRequests','ClientWant/AllWants','ClientStartupService/GetStartupInfo','ClientMaterialService/GetUserMaterialTypes','ClientQuestService/GetQuests','ClientUserBundleService/GetUserBundles','ClientUserService/GetUserPayments','ClientStartupService/GetStartupInfoForExtras','ClientVillagerService/GetUserGachaVillagers'}
NEED_SERVICES={'ClientWant/'+v for v in needs_model.GENERATORS}|{'ClientWant/'+v for v in needs_model.DEFERRED}|{'ClientVillager/Consume','ClientVillager/ReleaseXp'}
PROGRESSION_SERVICES={'ClientUser/IncreaseLevel','ClientUser/CompleteTutorial'}
QUEST_SERVICES={'ClientVillagerService/PerformFunActivity','ClientMaterialService/SellMaterialType','ClientMaterialService/BuyStoreItem','ClientMaterialService/BuyMaterialType','ClientUserBundleService/CreateUserBundle','ClientQuestService/AddQuest','ClientQuestService/CompleteQuest'}
BUILDING_SERVICES={'ClientBuildingService/DeleteUserFunBuildingType','ClientBuildingService/DeleteUserBuildingTask','ClientBuildingService/CreateUserBuildingTask','ClientBuildingService/GetUserBuildingTasks'}
TASK_SERVICES={'ClientTaskService/InstantCompleteTaskCurve','ClientTaskService/StartGatheringTask','ClientTaskService/StartCraftingTask','ClientTaskService/StartBuildingTask','ClientTaskService/StartFarmingTask','ClientTaskService/HarvestTask'}
TUTORIAL_SERVICES={'ClientUser/KeepActive','ClientUserHashService/GetUserHash','ClientUserHashService/SetActiveSequence','ClientUserHashService/SetVillagerName','ClientUserShelterService/ResetHappinessTimer','ClientSettingService/GetUserGameSettings','ClientSettingService/SaveGameSetting','ClientUserService/ProgressArea'}|area_model.SERVICES|placement_model.SERVICES|charm_model.SERVICES|interactive_model.SERVICES|collection_model.SERVICES|fortune_model.SERVICES|learning_model.SERVICES|marriage_model.SERVICES|relationship_model.SERVICES|family_model.SERVICES|family_model.READ_SERVICES|habitat_model.SERVICES|social_model.SERVICES|NORMAL_READ_SERVICES|TASK_SERVICES|BUILDING_SERVICES|PROGRESSION_SERVICES|QUEST_SERVICES|NEED_SERVICES
def community_relationship_operation(profile,service,data):
 with LOCK:
  path=profile_path(profile['deviceId']).with_suffix('.tutorial.json')
  saved=json.loads(path.read_text(encoding='utf-8'));normal=saved.get('normal')
  if normal is None:raise ValueError('Normal village required')
  import copy
  candidate=copy.deepcopy(normal);response,changed=relationship_model.community(candidate,service,data,wire_time(),profile['pId'])
  if changed:
   candidate['revision']+=1;candidate['updatedAt']=wire_time();world_model.validate_world(candidate);saved['normal']=candidate;atomic_json(path,saved)
  return response

def process(request,native_ids=False):
 if native_ids:
  import native_identity
  return native_identity.process(request)
 calls=request.get('data',{}).get('calls',[])
 if not isinstance(calls,list):raise ValueError('calls array required')
 results=[]
 for call in calls:
  service=call.get('service','');data={};code=200;message=''
  try:
   if service in OPTIONAL_EMPTY:pass # Request already recorded privately by HTTP handler.
   elif service=='ClientAchievement/GetUserAchievements':data={'result':[]} # Fresh local profile, no achievements earned.
   elif service in TUTORIAL_SERVICES:
    payload=call.get('data',{})
    if not isinstance(payload,dict):raise ValueError('Call data must be an object')
    data=tutorial_operation(request,service,payload,call.get('id'))
   else:code=501;message='Unimplemented local preservation service: '+service
  except NotImplementedError as ex:code=501;message=str(ex)
  except PermissionError as ex:code=403;message=str(ex)
  except ValueError as ex:code=400;message=str(ex)
  results.append({'id':str(call.get('id','')),'code':code,'data':data,'message':message})
 pending=[]
 with LOCK:
  try:
   path=authenticated_tutorial_path(request)
   saved=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
   if saved.get('normal'):pending=marriage_model.messages(saved['normal'],wire_time(),str(request['pId']))
  except PermissionError:pass # No private inbox is exposed by unauthenticated calls.
 return {'code':200,'currentTime':wire_time(),'messages':pending,'data':{'calls':results}}
