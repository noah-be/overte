"""Actual loader/drain/cancellation prefixes with real Qt queued delivery."""
import pathlib,os,shlex,subprocess,tempfile,unittest,resource
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
ROOT=pathlib.Path(__file__).resolve().parents[4]
def function(s,name):
 start=s.index(name);begin=s.index('{',start);depth=1;i=begin+1
 while depth:
  if s[i]=='{':depth+=1
  elif s[i]=='}':depth-=1
  i+=1
 return s[start:i]+'\n'
class EntityLoads(unittest.TestCase):
 def test_real_load_and_dispatch(self):
  source=(ROOT/'libraries/script-engine/src/ScriptManager.cpp').read_text();header=(ROOT/'libraries/script-engine/src/ScriptManager.h').read_text()
  self.assertIn('            processEntityScriptContents();',source)
  structs=header[header.index('struct EntityScriptLoadRequest {'):header.index('typedef QList<CallbackData>')]
  names=['bool ScriptManager::isCurrentEntityScriptLoad(', 'void ScriptManager::cancelEntityScriptLoad(', 'void ScriptManager::processEntityScriptContents(', 'void ScriptManager::loadEntityScript(', 'void ScriptManager::executeOnScriptThread(']
  extracted='\n'.join(function(source,n) for n in names)
  for n,end in [('void ScriptManager::unloadEntityScript(', '    EntityScriptDetails oldDetails;'),('void ScriptManager::unloadAllEntityScriptsForEntity(', '    std::vector<EntityScriptDetails> scriptDetails;'),('void ScriptManager::unloadAllEntityScripts(bool','    std::vector<std::pair<EntityItemID, EntityScriptDetails>> scripts;')]:
   extracted+=function(source,n).split(end)[0]+'}\n'
  if os.environ.get('OVERTE_ENTITY_LOAD_ACCEPT_STALE'):
   needle='_entityScriptLoads.value(entityID).value(script) == request';assert extracted.count(needle)==1;extracted=extracted.replace(needle,'true')
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
  with tempfile.TemporaryDirectory(prefix='entity-load-scope-') as d:
   d=pathlib.Path(d);(d/'structs.inc').write_text(structs);(d/'production.inc').write_text(extracted)
   binary=d/'test';subprocess.run(['c++','-std=c++17','-fPIC','-pthread','-I',str(d),str(pathlib.Path(__file__).with_name('entity-load-scope-test.cpp')),'-o',str(binary),*flags],check=True,timeout=30)
   subprocess.run(['unshare','--user','--map-root-user','--net',str(binary)],check=True,timeout=5)
if __name__=='__main__':unittest.main()
