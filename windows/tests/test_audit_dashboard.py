import json,re,shutil,subprocess,tempfile,unittest
from pathlib import Path
from audit_dashboard import render_dashboard
class ChecklistTests(unittest.TestCase):
 def fixture(self):
  common={'status':'not_implemented','regression_tests':[],'observed_codes':[]}
  return {'methods':{'ClientFire/Start':dict(common),'ClientTask/Gather':{**common,'status':'exercised_in_passing_regression'}},'tasks':[],'method_counts':{},'task_counts':{},'regressions':{'passed':1},'generated_utc':'test'}
 def test_embedded_data_cannot_close_script(self):
  result=self.fixture();result['methods']['</script><script>unexpected</script>']=result['methods']['ClientFire/Start']
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'test.html';render_dashboard(result,path);page=path.read_text(encoding='utf-8')
  match=re.search(r'<script id="audit-data" type="application/json">(.*?)</script>',page,re.S)
  self.assertIsNotNone(match);self.assertEqual(json.loads(match[1])['methods'],result['methods']);self.assertNotIn('<script>unexpected',page)
 @unittest.skipUnless(shutil.which('node'),'Node is optional; not installed')
 def test_filters_without_browser_or_network(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'test.html';render_dashboard(self.fixture(),path);page=path.read_text(encoding='utf-8')
   data=re.search(r'<script id="audit-data" type="application/json">(.*?)</script>',page,re.S)[1];script=re.search(r'<script>(.*?)</script>',page,re.S)[1]
   stub="""const nodes={};function element(){return {value:'',textContent:'',innerHTML:'',children:[],appendChild(v){this.children.push(v)},replaceChildren(){this.children=[];this.value=''}}}global.document={getElementById(id){return nodes[id]??=(element())},createElement(){return element()}};nodes['audit-data']=element();nodes['audit-data'].textContent="""+json.dumps(data)+";\n"
   assertions="""if(nodes.total.textContent!=='2 of 2 entries')throw Error('initial table');nodes.search.value='Fire';draw();if(nodes.total.textContent!=='1 of 2 entries')throw Error('search');nodes.search.value='';nodes.status.value='not_implemented';draw();if(nodes.total.textContent!=='1 of 2 entries')throw Error('filter');setMode('tasks');if(nodes.total.textContent!=='0 of 0 entries')throw Error('task switch');setMode('purchases');if(nodes.total.textContent!=='0 of 0 entries')throw Error('purchase switch');"""
   target=Path(temp)/'check.js';target.write_text(stub+script+assertions,encoding='utf-8');result=subprocess.run(['node',str(target)],capture_output=True,text=True,timeout=10)
  self.assertEqual(result.returncode,0,result.stderr)
if __name__=='__main__':unittest.main()
