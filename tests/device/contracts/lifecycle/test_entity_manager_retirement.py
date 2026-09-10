"""Actual renderer retirement helper and reset/shutdown prefixes; real Qt threads."""
from pathlib import Path
import os, resource, shlex, subprocess, tempfile, unittest
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
from test_login_dialog_domain_receiver import block
ROOT=Path(__file__).resolve().parents[4]
class Retirement(unittest.TestCase):
 def test_actual_renderer_retirement(self):
  relative='libraries/entities-renderer/src/EntityTreeRenderer.cpp'
  baseline=os.environ.get('OVERTE_ENTITY_RETIRE_BASELINE')
  source=subprocess.check_output(['git','show',baseline+':'+relative],cwd=ROOT,text=True) if baseline else (ROOT/relative).read_text()
  helper=block(source,'static void retireEntityScriptManager(') if 'static void retireEntityScriptManager(' in source else ''
  registry_source=(ROOT/'libraries/script-engine/src/ScriptManager.cpp').read_text()
  if os.environ.get('OVERTE_ENTITY_RETIRE_REGISTRY_BASELINE'):
   registry_source=subprocess.check_output(['git','show',os.environ['OVERTE_ENTITY_RETIRE_REGISTRY_BASELINE']+':libraries/script-engine/src/ScriptManager.cpp'],cwd=ROOT,text=True)
  methods=[]
  for name,member in [('Persistent','_persistentEntitiesScriptManager'),('NonPersistent','_nonPersistentEntitiesScriptManager')]:
   body=block(source,'void EntityTreeRenderer::reset'+name+'EntitiesScriptEngine(')
   methods.append(body[:body.index('    '+member+' = scriptManagerFactory')]+ '\n}')
  body=block(source,'void EntityTreeRenderer::clear(');a=body.index('        // unload and stop the engines');z=body.index('\n\n        if (scene)',a)
  methods.append('void EntityTreeRenderer::shutdownManagers() {\n'+body[a:z]+'\n}')
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core','Qt6Concurrent'],text=True))
  with tempfile.TemporaryDirectory(prefix='entity-retire-') as d:
   d=Path(d);(d/'retirement.inc').write_text(helper+'\n'+'\n'.join(methods)+'\n'+block(registry_source,'void ScriptManager::removeFromScriptEngines('));binary=d/'test'
   subprocess.run(['c++','-std=c++17','-fPIC','-pthread','-I',str(d),str(Path(__file__).with_name('entity-manager-retirement-test.cpp')),'-o',str(binary),*flags],check=True,timeout=30)
   for mode in ['persistent','nonpersistent','shutdown','shutdown-nonpersistent','already-done','registry-expired','empty']:
    with self.subTest(mode=mode):subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),mode],check=True,timeout=5)
if __name__=='__main__':unittest.main()
