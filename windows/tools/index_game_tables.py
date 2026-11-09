"""Index original English data tables for future local backend work; no game changes."""
from pathlib import Path
import hashlib,json,sqlite3,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'analysis/private/decoded_xml/files/xml'
TARGET=ROOT/'analysis/private/game_tables.sqlite'
assert not TARGET.exists(),'Preserve existing derived database; choose a new output for regeneration.'
conn=sqlite3.connect(TARGET)
conn.executescript('''PRAGMA foreign_keys=ON;
CREATE TABLE source_files(id INTEGER PRIMARY KEY,path TEXT UNIQUE,sha256 TEXT);
CREATE TABLE game_tables(id INTEGER PRIMARY KEY,source_id INTEGER REFERENCES source_files(id),name TEXT,declared_rows INTEGER,actual_rows INTEGER);
CREATE TABLE game_rows(table_id INTEGER REFERENCES game_tables(id),ordinal INTEGER,row_id TEXT,fields_json TEXT,PRIMARY KEY(table_id,ordinal));
CREATE INDEX table_name ON game_tables(name);
CREATE INDEX row_key ON game_rows(table_id,row_id);
''')
summary=[]
for source in sorted(BASE.glob('*_en.xml')):
 raw=source.read_bytes();root=ET.fromstring(raw.rstrip(b'\0'))
 sid=conn.execute('INSERT INTO source_files(path,sha256) VALUES(?,?)',(source.name,hashlib.sha256(raw).hexdigest())).lastrowid
 for table in root.iter('table'):
  name=table.get('name');rows=table.findall('./rows/row')
  expected=int(table.get('numrows'));assert len(rows)==expected,(source.name,name,expected,len(rows))
  tid=conn.execute('INSERT INTO game_tables(source_id,name,declared_rows,actual_rows) VALUES(?,?,?,?)',(sid,name,expected,len(rows))).lastrowid
  fields=set()
  for ordinal,row in enumerate(rows):
   data={}
   for field in row:
    value=ET.tostring(field,encoding='unicode') if len(field) or field.attrib else (field.text or '')
    if field.tag in data:
     if not isinstance(data[field.tag],list):data[field.tag]=[data[field.tag]]
     data[field.tag].append(value)
    else:data[field.tag]=value
    fields.add(field.tag)
   conn.execute('INSERT INTO game_rows VALUES(?,?,?,?)',(tid,ordinal,row.findtext('id'),json.dumps(data,ensure_ascii=True)))
  summary.append(dict(source=source.name,table=name,rows=len(rows),fields=sorted(fields)))
conn.commit();assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok';conn.close()
(ROOT/'analysis/english_table_schema.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
record=dict(source_files=len(list(BASE.glob('*_en.xml'))),table_definitions=len(summary),distinct_table_names=len(set(x['table'] for x in summary)),rows=sum(x['rows'] for x in summary),declared_counts_match=True,database_integrity='ok',database_sha256=hashlib.sha256(TARGET.read_bytes()).hexdigest(),automatic_gameplay_or_service_modifications=False)
(ROOT/'analysis/game_database_summary.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
print(json.dumps(record,indent=2))
