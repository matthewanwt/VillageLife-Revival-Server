"""Prepare original source data for the normal-world handoff; do not serve it yet."""
from pathlib import Path
import sqlite3,json,hashlib,collections
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1]
DATABASE=ROOT/'analysis/private/game_tables.sqlite'
def rows(conn,name):
 return [json.loads(v[0]) for v in conn.execute('select fields_json from game_rows r join game_tables t on r.table_id=t.id where t.name=? order by r.ordinal',(name,))]
def prepare():
 with closing(sqlite3.connect('file:'+str(DATABASE)+'?mode=ro',uri=True)) as conn:
  scenarios=rows(conn,'scenario');source=next(v for v in scenarios if v['serverScenarioId']=='2')
  entities=json.loads(source['clientData'])
  versions={v['refId']:v for v in rows(conn,'villager_starting_variation') if v['id'] in {'0','4','8','10','12','22'}}
 return {'runtime_ready':False,'reason':'Normal startup response contracts and simulation have not been implemented; source data only','source_database_sha256':hashlib.sha256(DATABASE.read_bytes()).hexdigest(),'scenario_source':source,'original_entity_counts':dict(collections.Counter(v['templateType'] for v in entities)),'original_entities':entities,'original_character_variation_sources':versions,'handoff_observed_request':{'service':'ClientUserService/ProgressArea','data':{}},'required_contracts':['ClientStartupService/GetStartupInfo','ClientStartupService/GetStartupInfoForExtras','ClientMaterialService/GetUserMaterialTypes','ClientQuestService/GetUserQuests','ClientUserBundleService/GetUserBundles','ClientUserService/GetUserPayments'],'identity_requirements':['Preserve distinct character IDs across handoff','Map source shelter-bed villager references to the same live character IDs','Keep tutorial source records separate from normal-world server models','Use decimal epoch seconds for native GetChildTime fields']}
if __name__=='__main__':
 out=ROOT/'analysis/private/normal_world_source_seed.json';data=prepare();out.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf8');print(json.dumps({'file':str(out),'runtime_ready':False,'source_scenario':data['scenario_source']['name'],'entities':sum(data['original_entity_counts'].values())}))
