"""Offline restoration coverage: original contracts, regression traces and table sweeps.
Never launches Android, contacts a game server, or reads/modifies the live save.
"""
from pathlib import Path
import argparse,collections,copy,csv,datetime,hashlib,io,json,re,sys,tempfile,unittest,zipfile,os,ast
from decimal import Decimal
from functools import lru_cache
from audit_dashboard import render_dashboard
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'tools'))
import session,world,tasks,buildings,community,needs,habitats,shop
EXPECTED='8d25823b824ba766b38e53aedb74b270a0254e6bf3fbbcf1a858b090a66b5c08'

@lru_cache(maxsize=None)
def audit_rows(table):
 return tuple(world.rows(table))

def digest(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def static_catalog(root=ROOT):
 archive=next(root.glob('*.xapk'))
 if digest(archive)!=EXPECTED:raise RuntimeError('Original XAPK hash mismatch; audit stopped')
 with zipfile.ZipFile(archive) as z:
  with zipfile.ZipFile(io.BytesIO(z.read('com.playdemic.villagelife.android.apk'))) as apk:image=apk.read('lib/armeabi-v7a/libpdandroid.so')
 catalog={}
 def add(name,kind):catalog.setdefault(name,{'evidence':[]}).setdefault('evidence',[]).append(kind)
 for value in re.findall(rb'[ -~]{8,}',image):
  name=value.decode('ascii')
  if re.fullmatch(r'Client[A-Za-z0-9]+/[A-Za-z][A-Za-z0-9]+',name):add(name,'original_binary_literal')
 old=root/'analysis/server_contracts.json'
 if old.exists():
  for name,record in json.loads(old.read_text())['methods'].items():
   for item in record.get('evidence',[]):
    if item['type'] in {'original_literal','static_call_candidate'}:add(name,item['type'])
 implemented=session.TUTORIAL_SERVICES|session.OPTIONAL_EMPTY|{'ClientAchievement/GetUserAchievements','ClientService/Login','ApplicationSetting/Get'}
 disabled=session.OPTIONAL_EMPTY|{'ClientWant/'+v for v in needs.DEFERRED}|{'ClientAchievement/GetUserAchievements','ApplicationSetting/Get'}
 for name in implemented:add(name,'local_route')
 for name,record in catalog.items():
  record['evidence']=sorted(set(record['evidence']));record['handler_declared']=name in implemented
  record['policy_disabled_or_empty']=name in disabled
  record['regression_tests']=[];record['observed_codes']=[];record['latest_observation']=None
 return catalog

class TraceResult(unittest.TextTestResult):
 def startTest(self,test):self.audit.current=test.id();super().startTest(test)
 def addSuccess(self,test):self.audit.passed.add(test.id());super().addSuccess(test)
 def stopTest(self,test):super().stopTest(test);self.audit.current=None

class RegressionAudit:
 def __init__(self):self.current=None;self.passed=set();self.events=[]
 def record(self,name,code):self.events.append((self.current or 'background',name,code))
 def run(self,out):
  original=session.process;original_login=session.login;original_community=community.process
  def process(request,*args,**kwargs):
   response=original(request,*args,**kwargs)
   for call,result in zip(request.get('data',{}).get('calls',[]),response['data']['calls']):self.record(call.get('service',''),result['code'])
   return response
  def login(request):
   result=original_login(request);self.record('ClientService/Login',result['code']);return result
  def community_process(document,*args,**kwargs):
   result=original_community(document,*args,**kwargs)
   for call,response in zip(document.get('Calls',[]),result.get('data',[])):self.record(call.get('Service',''),response['code'])
   return result
  suite=unittest.TestSuite()
  for folder in ['backend','tools']:
   suite.addTests(unittest.TestLoader().discover(str(ROOT/folder),pattern='test_*.py',top_level_dir=str(ROOT/folder)))
  with tempfile.TemporaryDirectory(prefix='village-audit-') as temp,patch.object(session,'STATE',Path(temp)),patch.object(session,'process',process),patch.object(session,'login',login),patch.object(community,'process',community_process),(out/'regression-tests.txt').open('w',encoding='utf-8') as log:
   runner=unittest.TextTestRunner(stream=log,verbosity=2,resultclass=TraceResult)
   runner._makeResult=lambda: self.result(runner.stream)
   result=runner.run(suite)
  return {'run':result.testsRun,'passed':len(self.passed),'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)}
 def result(self,log):
  result=TraceResult(log,True,2);result.audit=self;return result

def observations(catalog,root=ROOT):
 # Metadata only: never copy request bodies, identities, credentials or save contents.
 logs=list((root/'experiments').glob('local-service-*/requests.jsonl'))
 for log in sorted(logs):
  pending={}
  for line in log.read_text(encoding='utf-8',errors='replace').splitlines():
   try:row=json.loads(line)
   except ValueError:continue
   if row.get('method')=='POST':
    doc=row.get('document',{});calls=doc.get('data',{}).get('calls',[])
    for call in calls:pending[str(call.get('id'))]=call.get('service')
   if row.get('method')!='RESPONSE':continue
   for call in row.get('calls',[]):
    name=pending.pop(str(call.get('id')),None)
    if not name:continue
    record=catalog.setdefault(name,{'evidence':[],'handler_declared':False,'policy_disabled_or_empty':False,'regression_tests':[],'observed_codes':[],'latest_observation':None})
    code=call.get('code');record['observed_codes'].append(code)
    event={'utc':row.get('utc',''),'code':code,'log':str(log.relative_to(root)).replace(chr(92),'/')}
    if not record['latest_observation'] or event['utc']>record['latest_observation']['utc']:record['latest_observation']=event
 for record in catalog.values():record['observed_codes']=sorted(set(record['observed_codes']))

def task_cases():
 definitions=collections.defaultdict(list)
 for row in audit_rows('building_task'):definitions[row['taskId']].append(row)
 for task in audit_rows('task'):
  variants=definitions[task['id']] if task['taskType'] in {'2','6'} else [None]
  for variant in variants or [None]:yield task,variant

def fixture(task,variant,base):
 family=task['taskType'];state=copy.deepcopy(base);state['workAreas']={}
 # Synthetic prerequisites deliberately bypass progression, placement and unlock UI.
 for req in audit_rows('requirement_set_item'):
  state['inventory'][req['materialType']]=max(state['inventory'].get(req['materialType'],0),float(req['quantity'])+float(req['quantityUsed'])+100)
  if req['materialType']=='7':state['user']['xp']=max(state['user']['xp'],float(req['quantity'])+100)
 point={'x':4000,'y':4000,'rotation':0,'areaId':state['areaId']}
 entity={'id':'audit-source','serverPersisted':True,'position':point}
 if family=='4':
  source=world.by_id('farming_plot',0)
  entity.update(templateType='farming_plot',templateId=int(source['id']))
 elif family=='3':
  source=next((v for v in audit_rows('material_source') if v['task']==task['id']),None)
  if source is None:raise LookupError('No original material_source references this task')
  entity.update(templateType='material_source',templateId=int(source['id']))
 elif family=='1':
  source=next((v for v in audit_rows('workshop') if task['workAreaType'] in v['tableIDs'].split(',')),None)
  if source is None:raise LookupError('No original workshop table matches this recipe')
  entity.update(templateType='workshop',templateId=int(source['id']))
 else:
  if variant is None:raise LookupError('No original foundation references this building task')
  if family=='6':
   if variant['parentId']=='-1':raise LookupError('Upgrade has no original parent')
   previous=world.by_id('building_type',world.by_id('building_task',variant['parentId'])['buildingType'])
   entity.update(templateType=previous['entityRef'],templateId=int(previous['entityID']))
   import fun
   fun.initialize(entity);habitats.initialize(entity,1000)
   state['inventory'][previous['materialType']]=max(1,state['inventory'].get(previous['materialType'],0))
  else:entity.update(templateType='building_task',templateId=int(variant['id']))
 state['world']['entities'].append(entity)
 actor=next(v for v in state['world']['entities'] if v['templateType']=='villager_type' and world.by_id('villager_type',v['templateId'])['canWork']=='1')
 data={'villagerId':actor['id'],'taskTypeId':int(task['id']),'userMaterialSourceId':entity['id'],**point}
 if family=='4':data['userFarmPlotId']=entity['id']
 return state,data

def require(condition,message):
 if not condition:raise AssertionError(message)

def exercise_fire_task(task,base):
 result={'task_id':task['id'],'name':task['name'],'family':'5','family_name':'Fire','foundation_id':None,'status':None,'reason':None,'checks':[],'stage':'fixture'}
 try:
  definition=next((v for v in audit_rows('fire_task') if v['taskId']==task['id']),None)
  if definition is None:raise LookupError('No original fire type references this task')
  state=copy.deepcopy(base);fire=next(e for e in state['world']['entities'] if e['templateType']=='fire_type');fire['templateId']=int(definition['fireType'])
  for req in audit_rows('requirement_set_item'):state['inventory'][req['materialType']]=max(state['inventory'].get(req['materialType'],0),float(req['quantity'])+float(req['quantityUsed'])+100)
  data={'userFireId':fire['id'],'villagerId':'steve'};before=copy.deepcopy(state['inventory']);result['stage']='start'
  response,_=habitats.operate(state,'ClientUserFireService/StartFire',data,1000,'audit-start');require(response['userFire']['endsAt']==1000+int(definition['burnDuration']),'Original burn time mismatch')
  for req in audit_rows('requirement_set_item'):
   if req['requirementSet']==task['requirementSet']:require(abs(state['inventory'][req['materialType']]-(before[req['materialType']]-float(req['quantityUsed'])))<1e-7,'Original fire cost mismatch')
  snapshot=copy.deepcopy(state);habitats.operate(state,'ClientUserFireService/StartFire',data,1001,'audit-start');require(snapshot==state,'Repeated fire start charged twice');result['checks']+=['original_fire_costs_and_burn_timer','repeat_start_no_double_charge']
  result['stage']='expiry_after_reload';state=json.loads(json.dumps(state));require(habitats.sync(state,response['userFire']['endsAt']),'Fire did not expire after reload');snapshot=copy.deepcopy(state);require(not habitats.sync(state,response['userFire']['endsAt']+1) and state==snapshot,'Fire expiry applied twice');world.validate_world(state);result['checks']+=['reload_then_expiry','repeat_expiry_no_double_deduction','world_invariants'];result['status']='passed_server_fixture'
 except NotImplementedError as error:result.update(status='not_implemented',reason=str(error))
 except LookupError as error:result.update(status='fixture_missing',reason=str(error))
 except ValueError as error:result.update(status='rejected_fixture',reason=str(error))
 except Exception as error:result.update(status='failed',reason=type(error).__name__+': '+str(error))
 return result

def exercise_task(task,variant,base):
 family=task['taskType']
 if family=='5':return exercise_fire_task(task,base)
 result={'task_id':task['id'],'name':task['name'],'family':family,'family_name':next(v['name'] for v in audit_rows('task_type') if v['id']==family),'foundation_id':variant['id'] if variant else None,'status':None,'reason':None,'checks':[]}
 if family not in {'1','2','3','4','6'}:
  result.update(status='not_implemented',reason='Task family has no local start/finish implementation');return result
 stage='fixture'
 try:
  state,data=fixture(task,variant,base);before=copy.deepcopy(state);stage='start'
  service={'1':'ClientTaskService/StartCraftingTask','2':'ClientTaskService/StartBuildingTask','3':'ClientTaskService/StartGatheringTask','4':'ClientTaskService/StartFarmingTask','6':'ClientTaskService/StartBuildingTask'}[family]
  start,changed=tasks.start(state,data,1000,service);require(changed,'First start did not create a job')
  require(start['completionTime']==1000+int(task['duration']),'Completion time differs from original base duration')
  deductions=collections.defaultdict(Decimal)
  for req in audit_rows('requirement_set_item'):
   if req['requirementSet']==task['requirementSet']:deductions[req['materialType']]+=Decimal(req['quantityUsed'])
  for key,cost in deductions.items():require(abs(state['inventory'][key]-(before['inventory'].get(key,0)-float(cost)))<1e-7,'Original cost mismatch: '+key)
  result['checks'].append('base_duration_and_original_costs');started=copy.deepcopy(state)
  again,changed=tasks.start(state,data,1000,service);require(not changed and again==start and state==started,'Repeated start changed state or charged twice')
  result['checks'].append('repeat_start_no_double_charge');stage='early_harvest'
  try:tasks.harvest(state,{'workAreaId':start['workAreaId'],'taskTypeId':int(task['id'])},start['completionTime']-1)
  except ValueError:pass
  else:raise AssertionError('Premature harvest accepted')
  require(state==started,'Premature harvest mutated state');result['checks'].append('early_harvest_no_mutation')
  state=json.loads(json.dumps(state));stage='harvest_after_reload';balances=copy.deepcopy(state['inventory'])
  request={'workAreaId':start['workAreaId'],'taskTypeId':int(task['id'])}
  response,changed=tasks.harvest(state,request,start['completionTime']);require(changed,'First harvest did not commit')
  rewards=collections.defaultdict(Decimal)
  for reward in audit_rows('reward_set_item'):
   if task['rewardSet']!='0' and reward['setId']==task['rewardSet']:rewards[reward['materialType']]+=Decimal(reward['quantity'])
  if family in {'2','6'}:
   definition=buildings.completion_definition({'templateId':int(variant['id'])})
   if definition['materialType'] not in rewards:rewards[definition['materialType']]+=1
   if family=='6':
    previous=world.by_id('building_type',world.by_id('building_task',variant['parentId'])['buildingType'])
    if previous['materialType']!=definition['materialType']:rewards[previous['materialType']]-=1
  for key,amount in rewards.items():require(abs(state['inventory'][key]-(balances.get(key,0)+float(amount)))<1e-7,'Original reward mismatch: '+key)
  result['checks'].append('reload_then_original_rewards');after=copy.deepcopy(state)
  replay,changed=tasks.harvest(state,request,start['completionTime']+1);require(not changed and replay==response and state==after,'Repeated harvest awarded twice or changed state')
  world.validate_world(state);result['checks']+=['repeat_harvest_no_double_reward','world_invariants'];result['status']='passed_server_fixture'
 except NotImplementedError as error:result.update(status='not_implemented',reason=str(error))
 except LookupError as error:result.update(status='fixture_missing',reason=str(error))
 except ValueError as error:result.update(status='rejected_fixture',reason=str(error))
 except Exception as error:result.update(status='failed',reason=type(error).__name__+': '+str(error))
 result['stage']=stage;return result

def purchase_cases():
 for definition in audit_rows('material_type'):
  result={'material_id':definition['id'],'name':definition['name'],'status':None,'reason':None,'quantities_tested':[],'checks':[]}
  low=max(1,int(definition['minPurchasable']));high=int(definition['maxPurchasable'])
  if Decimal(definition['gemsRatio'] or '0')<=0 or high<low:
   result.update(status='not_direct_gem_purchase',reason='Original table has no positive direct gem price or valid quantity range');yield result;continue
  amounts=range(low,high+1) if high-low<=50 else sorted({low,min(low+1,high),(low+high)//2,max(low,high-1),high})
  try:
   for amount in amounts:
    cost=shop.purchase_price(definition,amount);state={'inventory':{'323':cost+10},'user':{'userLevelID':int(definition['unlockLevel'])},'revision':1};data={'materialTypeId':int(definition['id']),'amount':amount}
    shop.buy(state,data,'audit-buy');require(state['inventory']['323']==10,'Wrong gem deduction');require(state['inventory'][definition['id']]==amount,'Wrong purchased quantity')
    state=json.loads(json.dumps(state));before=copy.deepcopy(state);require(not shop.buy(state,data,'audit-buy')[1] and state==before,'Purchase replay charged twice after reload')
    poor={'inventory':{'323':cost-1},'user':{'userLevelID':int(definition['unlockLevel'])},'revision':1};before=copy.deepcopy(poor)
    try:shop.buy(poor,data,'insufficient')
    except ValueError:pass
    else:raise AssertionError('Purchase accepted with insufficient gems')
    require(poor==before,'Failed purchase mutated inventory');result['quantities_tested'].append(amount)
   result.update(status='passed_server_fixture',checks=['original_float32_price','quantity_boundaries_or_all_small_range','deduct_and_deliver','reload_and_repeat_no_double_charge','insufficient_gems_no_mutation'])
  except NotImplementedError as error:result.update(status='not_implemented',reason=str(error))
  except Exception as error:result.update(status='failed',reason=type(error).__name__+': '+str(error))
  yield result

def unsupported_branches():
 result=[]
 for path in sorted((ROOT/'backend').glob('*.py')):
  if path.name.startswith('test_'):continue
  tree=ast.parse(path.read_text(encoding='utf-8'))
  for node in ast.walk(tree):
   if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):continue
   for child in ast.walk(node):
    if not isinstance(child,ast.Raise) or not isinstance(child.exc,ast.Call) or not isinstance(child.exc.func,ast.Name) or child.exc.func.id!='NotImplementedError':continue
    reason=ast.unparse(child.exc.args[0]) if child.exc.args else 'No recovered rule'
    result.append({'file':str(path.relative_to(ROOT)).replace(chr(92),'/'),'function':node.name,'line':child.lineno,'reason':reason})
 return result

def classify(record):
 if record['policy_disabled_or_empty']:return 'disabled_or_empty_policy'
 if not record['handler_declared']:return 'not_implemented'
 if record['regression_tests']:return 'exercised_in_passing_regression'
 return 'declared_not_exercised'

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--skip-regressions',action='store_true');parser.add_argument('--open',action='store_true');args=parser.parse_args()
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out=ROOT/'analysis/feature-audits'/stamp;out.mkdir(parents=True)
 print('Reading original client contracts; the game will not be launched.',flush=True);catalog=static_catalog()
 audit=RegressionAudit();tests=audit.run(out) if not args.skip_regressions else {'skipped_entire_suite':True}
 for test,name,code in audit.events:
  if test in audit.passed and code==200 and name in catalog:catalog[name]['regression_tests'].append(test)
 for record in catalog.values():record['regression_tests']=sorted(set(record['regression_tests']))
 print('Testing original task rows in disposable synthetic villages...',flush=True);base=world.build_bridge_world(session.fresh_tutorial(),1000)
 matrix=[]
 for index,(task,variant) in enumerate(task_cases(),1):
  matrix.append(exercise_task(task,variant,base))
  if index%250==0:print(f'  {index} original task definitions checked',flush=True)
 print('Testing original material purchase ranges...',flush=True);purchases=list(purchase_cases())
 observations(catalog)
 for record in catalog.values():
  record['status']=classify(record)
  record['open_observed_error']=bool(record['latest_observation'] and record['latest_observation']['code']>=400)
 with (ROOT/'analysis/libpdandroid.so.symbols.csv').open(encoding='utf-8') as source:symbols=list(csv.DictReader(source))
 scripts=[row for row in symbols if row['defined']=='True' and 'Script_' in row['name']]
 with (out/'original-script-symbols.csv').open('w',newline='',encoding='utf-8-sig') as target:
  writer=csv.DictWriter(target,fieldnames=['name','address','size']);writer.writeheader();writer.writerows({k:row[k] for k in writer.fieldnames} for row in scripts)
 result={'generated_utc':stamp,'original_sha256':EXPECTED,'game_executed':False,'live_save_used':False,'regressions':tests,'method_counts':dict(collections.Counter(r['status'] for r in catalog.values())),'task_counts':dict(collections.Counter(r['status'] for r in matrix)),'missing_task_families':dict(collections.Counter(r['family_name'] for r in matrix if r['family'] not in {'1','2','3','5','6'})),'original_defined_script_symbols':sum(s['defined']=='True' and 'Script_' in s['name'] for s in symbols),'methods':dict(sorted(catalog.items())),'purchase_counts':dict(collections.Counter(r['status'] for r in purchases)),'purchases':purchases,'unsupported_branches':unsupported_branches(),'tasks':matrix,'limitations':['Client code does not contain the original server implementation.','Static candidates may be obsolete, debug-only or unreachable.','Synthetic fixtures bypass unlocks, progression, placement and native rendering.','Passing server tests do not prove a complete feature or in-game UI works.','Live observations are historical per-log request-ID correlations, not a fresh UI test.','Disabled/empty policies can return200 without implementing their gameplay.','Skill/time modifiers, probability rules and event simulation remain incomplete.']}
 (out/'coverage.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
 render_dashboard(result,out/'dashboard.html')
 with (out/'methods.csv').open('w',newline='',encoding='utf-8-sig') as f:
  writer=csv.writer(f);writer.writerow(['method','status','passing_test_count','historical_codes','latest_code'])
  for name,r in sorted(catalog.items()):writer.writerow([name,r['status'],len(r['regression_tests']),','.join(map(str,r['observed_codes'])),(r['latest_observation'] or {}).get('code','')])
 with (out/'tasks.csv').open('w',newline='',encoding='utf-8-sig') as f:
  writer=csv.DictWriter(f,fieldnames=['task_id','name','family','family_name','foundation_id','status','reason','stage']);writer.writeheader()
  for row in matrix:writer.writerow({k:row.get(k) for k in writer.fieldnames})
 with (out/'purchases.csv').open('w',newline='',encoding='utf-8-sig') as f:
  writer=csv.writer(f);writer.writerow(['material_id','name','status','quantities_tested','reason'])
  for row in purchases:writer.writerow([row['material_id'],row['name'],row['status'],len(row['quantities_tested']),row['reason']])
 lines=['# Restoration coverage audit','',f'Generated {stamp}. Offline analysis and disposable server tests; no Android execution or live-save changes.','',f'Regressions: {tests}',f'Method states: {result["method_counts"]}',f'Task variants: {result["task_counts"]}',f'Material purchase definitions: {result["purchase_counts"]}','','## Prioritised backlog','','### Observed missing operations','']
 missing=[(name,r) for name,r in sorted(catalog.items()) if not r['handler_declared'] and r['latest_observation'] and r['latest_observation']['code']==501]
 lines += [f'- {name} (last observed {r["latest_observation"]["utc"]})' for name,r in missing] or ['No latest correlated501 for an undeclared route.']
 lines+=['','### Implemented operations with latest observed errors','']
 lines += [f'- {name}: code{r["latest_observation"]["code"]} at {r["latest_observation"]["utc"]}; regression exercise does not establish native success' for name,r in sorted(catalog.items()) if r['handler_declared'] and r['open_observed_error']] or ['No latest correlated native error for a declared route.']
 lines+=['','### Batch task blockers','']
 for (status,reason),count in collections.Counter((r['status'],r['reason']) for r in matrix if r['status']!='passed_server_fixture').most_common():lines.append(f'- {count} variants: {status}: {reason}')
 lines+=['','Missing task-family rows: '+str(result['missing_task_families']),'','### Declared operations without successful regression exercise','']+[f'- {name}' for name,r in sorted(catalog.items()) if r['status']=='declared_not_exercised']
 lines+=['','### Deliberately disabled or empty policies','']+[f'- {name}' for name,r in sorted(catalog.items()) if r['policy_disabled_or_empty']]
 lines+=['','### Other original candidates awaiting contracts','']+[f'- {name}' for name,r in sorted(catalog.items()) if r['status']=='not_implemented' and not any(name==n for n,_ in missing)]
 lines+=['','### Explicit unsupported input branches','']+[f'- {item["file"]}:{item["line"]} ({item["function"]}): {item["reason"]}' for item in result['unsupported_branches']]
 lines+=['','## Limits','']+['- '+s for s in result['limitations']]
 lines+=['','## Repeatable workflow','','1. Recover request/response fields and rules from original tables, call sites and response parsers.','2. Add a disposable scenario with explicit expected balances, timers and state changes.','3. Implement the shared mechanic, rerun this audit, then test its original game UI.','4. Only mark a feature live-verified after that interaction succeeds, including restart/retry.','5. Package a versioned update after regression checks; preserve/migrate existing saves and retain rollback.','','Files: coverage.json contains evidence; methods.csv and tasks.csv are sortable inventories.']
 (out/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');pointer={'folder':str(out),'report':str(out/'REPORT.md'),'dashboard':str(out/'dashboard.html'),'method_counts':result['method_counts'],'task_counts':result['task_counts'],'regressions':tests,'purchase_counts':result['purchase_counts']}
 (ROOT/'analysis/latest-feature-audit.json').write_text(json.dumps(pointer,indent=2),encoding='utf-8');print(json.dumps(pointer,indent=2),flush=True)
 if args.open and hasattr(os,'startfile'):os.startfile(out/'dashboard.html')
 if tests.get('failures') or tests.get('errors') or any(r['status']=='failed' for r in matrix+purchases):return 1
 return 0
if __name__=='__main__':sys.exit(main())
