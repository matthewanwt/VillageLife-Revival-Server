"""Index evidence for local server methods; static candidates are not proven contracts."""
from pathlib import Path
import sys,contextlib,io,re,json,datetime,collections
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'backend'))
with contextlib.redirect_stdout(io.StringIO()):import trace_arm_protocol as native
import session,world,buildings
methods={}
def add(name,evidence):methods.setdefault(name,{'evidence':[]})['evidence'].append(evidence)
for raw in re.findall(rb'[ -~]{8,}',native.IMAGE):
 value=raw.decode('ascii')
 if re.fullmatch(r'Client[A-Za-z0-9]+/[A-Za-z][A-Za-z0-9]+',value):add(value,{'type':'original_literal'})
for symbol in native.SYMBOLS:
 if symbol['defined']!='True' or not ('Script_' in symbol['name'] and ('Server' in symbol['name'] or any(v in symbol['name'] for v in ['StartTask','WorkAreaModelInteraction']))):continue
 trace=native.trace(symbol)
 for call in trace['calls']:
  if 'ServerIRemoteCall' not in call['name']:continue
  args=call['args'];service=native.cstring(int(args.get('r0','0'),16));method=native.cstring(int(args.get('r1','0'),16))
  if service and method and re.fullmatch(r'Client[A-Za-z0-9]+',service) and re.fullmatch(r'[A-Za-z][A-Za-z0-9]+',method):add(service+'/'+method,{'type':'static_call_candidate','symbol':symbol['name'],'pc':call['pc']})
observed={}
for log in sorted((ROOT/'experiments').glob('local-service-*/requests.jsonl')):
 requests={}
 for line in log.read_text(encoding='utf8').splitlines():
  try:record=json.loads(line)
  except ValueError:continue
  if record['method']=='POST':
   for call in record.get('document',{}).get('data',{}).get('calls',[]):
    requests[call['id']]=call['service'];add(call['service'],{'type':'observed_request','log':str(log.relative_to(ROOT))});observed.setdefault(call['service'],set())
  elif record['method']=='RESPONSE':
   for call in record.get('calls',[]):
    name=requests.get(call['id'])
    if name:observed[name].add(call['code'])
implemented=session.TUTORIAL_SERVICES|session.OPTIONAL_EMPTY|{'ClientAchievement/GetUserAchievements','ClientService/Login'}
for name,record in methods.items():
 record['local_handler']=name in implemented;record['observed_response_codes']=sorted(observed.get(name,[]));record['evidence']=list({json.dumps(v,sort_keys=True):v for v in record['evidence']}.values())
covered=collections.Counter();blocked=collections.Counter();family_names={v['id']:v['name'] for v in world.rows('task_type')}
for task in world.rows('task'):
 family=task['taskType'];reason=None
 if family not in {'1','2','3'}:reason='task family protocol not implemented'
 rewards=[v for v in world.rows('reward_set_item') if v['setId']==task['rewardSet']]
 if not reason and (not rewards or any(float(v['chance'])!=1 for v in rewards)):reason='probability/empty-reward semantics not recovered'
 if family=='2' and not reason:
  definitions=[v for v in world.rows('building_task') if v['taskId']==task['id']]
  if not definitions or any(world.by_id('building_type',v['buildingType'])['entityRef'] not in buildings.SUPPORTED_BUILD_KINDS for v in definitions):reason='building completion schema not recovered'
 if reason:blocked[(family_names[family],reason)]+=1
 else:covered[family_names[family]]+=1
result={'generatedUtc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Original method literals, static call candidates, actual local requests and local implementation coverage. Candidate extraction is incomplete and is not proof the old server implementation exists.','methods':dict(sorted(methods.items())),'task_table_candidates_using_shared_rules':dict(covered),'task_table_blockers':[{'family':k[0],'reason':k[1],'count':v} for k,v in blocked.items()],'limitations':['Candidate recipe support is static; does not prove every task has been exercised in the original client.','Original skill/time modifiers, learned-unlock state, simulation and probabilistic rewards are not complete.']}
out=ROOT/'analysis/server_contracts.json';out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps({'methods_indexed':len(methods),'local_handlers':sum(r['local_handler'] for r in methods.values()),'table_candidates':dict(covered),'output':str(out)}))
