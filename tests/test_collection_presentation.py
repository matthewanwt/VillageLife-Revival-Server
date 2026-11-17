"""Synthetic ordinary/award namespace regressions; no client assets or saves."""
from copy import deepcopy
from contextlib import closing
from pathlib import Path
import json,sqlite3,tempfile,unittest
from test_original_client import fake_tables
from villagelife.protocol.original_client.catalog import OriginalDefinitions
from villagelife.protocol.original_client.services import OriginalClientGame
from villagelife.protocol.original_client.native_ids import reserve_ids
from villagelife.protocol.original_client.collection import read_collection
from villagelife.protocol.original_client.collection_projection import project_entities
from villagelife.persistence.sqlite_store import SqliteSaveRepository

def person(ident,rare=False):
 p={'id':ident,'name':'Synthetic','templateType':'villager_type','templateId':1,'villagerBaseId':52,'rarity':0,'equipment':'rare' if rare else 'ordinary','genetics':'' if rare else 'seed','serverPersisted':True,'position':{'areaId':1},'skills':[],'relations':[],'bornAt':0,'startAge':0,'gender':0}
 if rare:p['collectionBaseId']=52
 return p
class CollectionPresentationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);root=Path(self.temp.name);tables=root/'definitions.sqlite';fake_tables(tables)
  with closing(sqlite3.connect(tables)) as c:
   seed=c.execute("select id from game_tables where name='villager_starting_variation'").fetchone()[0]
   c.execute('insert into game_rows values (?,?,?,?)',(seed,99,'52',json.dumps({'id':'52','equipment':'ordinary','genetics':'seed'})))
   tid=c.execute('select max(id)+1 from game_tables').fetchone()[0];c.execute('insert into game_tables values (?,?,?,?,?)',(tid,0,'gachaVillager',1,1));c.execute('insert into game_rows values (?,?,?,?)',(tid,0,'52',json.dumps({'id':'52','equipment':'rare'})))
   c.commit()
  self.game=OriginalClientGame(SqliteSaveRepository(root/'synthetic.sqlite'),OriginalDefinitions(tables))
  self.state={'areaId':1,'initializedAreas':[1],'revision':7,'user':{'xp':0,'userLevelID':1},'inventory':{'323':77},'world':{'entities':[person('ordinary'),person('award',True)]},'villagerCollection':{'52':2},'workAreas':{}}
 def test_startup_and_actual_area_rules_keep_namespaces_separate(self):
  before=deepcopy(self.state)
  for result in (self.game.world.startup(self.state,0)['world'],self.game.areas.view(self.state,1,0)['areaJson']):
   people={e['id']:e for e in result['entities'] if e.get('templateType')=='villager_type'};self.assertEqual(people['ordinary']['villagerBaseId'],0);self.assertEqual(people['award']['villagerBaseId'],52)
  before['revision']+=1 # AreaRules.view independently advances its normal view revision.
  self.assertEqual(self.state,before)
 def test_birth_reply_has_same_projection_without_changing_children(self):
  reserve_ids(self.state,'1',());before=deepcopy(self.state)
  result=self.game.family.birth_reply(self.state,{'bornChildren':['ordinary','award']},'1')
  self.assertEqual([e['villagerBaseId'] for e in result['result']['villagers']],[0,52]);self.assertEqual(self.state,before)
 def test_reload_values_are_wire_only(self):
  state={'villagerCollection':{'1':0,'2':1,'3':2,'4':3}};before=deepcopy(state)
  self.assertEqual(json.loads(read_collection(state)['VillagerCollection']),{'1':0,'2':1,'3':1,'4':2});self.assertEqual(state,before)
 def test_ambiguous_saved_witness_does_not_remap_a_wire_record(self):
  wire={'id':'ordinary','templateType':'villager_type','villagerBaseId':52,'rarity':0}
  state={'world':{'entities':[person('ordinary'),person('ordinary',True)]}}
  self.assertEqual(project_entities([wire],self.game.defs,state),[wire])
if __name__=='__main__':unittest.main()
