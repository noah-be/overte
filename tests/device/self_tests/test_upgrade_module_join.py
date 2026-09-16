"""Actual upgrade assertion module with transport/session substitutes; no target calls."""
from pathlib import Path
import json,os,runpy,sys,tempfile,types,unittest
from unittest.mock import patch
D=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(D))
from execution_plan import module_capabilities
if os.environ.get('OVERTE_UPGRADE_OLD_PLANNER'):
 source=(D/'execution_plan.py').read_text()
 begin=source.index('    for module in selected:')
 end=source.index('    return ([module["id"] for module in selected],',begin)
 namespace={'__name__':'restored_old_planner'}
 exec(compile(source[:begin]+source[end:],'restored_old_planner','exec'),namespace)
 module_capabilities=namespace['module_capabilities']
class UpgradeJoin(unittest.TestCase):
 def exercise(self,fault=None):
  calls=[];state={'setting':False,'version':'1','sessions':0};reports=[]
  def operation(name,args=None):
   args=args or {};calls.append((name,args))
   if name=='app.version':return {'version':('wrong' if fault=='version' else state['version'])}
   if name=='setting.set':state['setting']=args['enabled']
   if name=='app.upgrade':
    if fault=='upgrade':raise RuntimeError('fixture upgrade failed')
    state['version']='2'
    if fault=='lost':state['setting']=False
   return {}
  class Session:
   def __init__(self):state['sessions']+=1
   def snapshot(self):return {'settings':{'audioWarnWhenMuted':state['setting']}}
  support=types.ModuleType('module_support');support.contract_operation=operation
  support.assert_foreground=lambda phase:None;support.wait_for_process=lambda:None
  support.write_json=lambda name,value:reports.append(value);support.module_main=lambda fn:fn()
  def fail(message):raise AssertionError(message)
  support.fail=fail;session=types.ModuleType('overte_session');session.OverteSession=Session
  error=None
  with patch.dict(sys.modules,{'module_support':support,'overte_session':session}),patch.dict(os.environ,{'OVERTE_E2E_UPGRADE_FROM_VERSION':'1','OVERTE_E2E_UPGRADE_TO_VERSION':'2','OVERTE_E2E_UPGRADE_SOURCE_ARTIFACT':'/synthetic/source.apk'}):
   try:runpy.run_path(str(D/'modules/update_upgrade.py'))
   except (AssertionError,RuntimeError) as caught:error=caught
  if fault:self.assertIsNotNone(error);self.assertFalse(reports)
  else:self.assertIsNone(error);self.assertTrue(reports[0]['safeSettingRetained']);self.assertEqual(state['sessions'],2)
  self.assertFalse(state['setting'])
  self.assertEqual([n for n,a in calls[:3]],['app.stop','app.install','app.launch'])
  if fault!='version':self.assertEqual(calls[-1],('setting.set',{'settingId':'audio.warn-when-muted','enabled':False}))
  catalog=json.loads((D/'catalog.json').read_text());entry=next(m for m in catalog['modules'] if m['id']=='update-upgrade')
  self.assertTrue({n for n,a in calls}<=set(entry['requires']))
 def test_success(self):self.exercise()
 def test_failures_and_restore(self):
  for fault in ['version','upgrade','lost']:
   with self.subTest(fault=fault):self.exercise(fault)
 def test_missing_command_rejected_before_execution(self):
  with tempfile.TemporaryDirectory() as directory:
   p=Path(directory)/'catalog.json';p.write_text(json.dumps({'modules':[{'id':'missing-fixture','suites':['fixture'],'requires':[],'command':['missing.py']}]}))
   with self.assertRaisesRegex(ValueError,'module command source is missing'):
    module_capabilities(p,'fixture')
 def test_current_module_inventory(self):
  modules=json.loads((D/'catalog.json').read_text())['modules']
  for suite in {s for m in modules for s in m['suites']}:module_capabilities(D/'catalog.json',suite)
if __name__=='__main__':unittest.main()
