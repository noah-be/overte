# SPDX-License-Identifier: Apache-2.0
"""Pure CPU source/schema composition; never execute services, namespaces or filters."""
import ast,contextlib,hashlib,importlib.util,io,json,os,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
import probe
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent
sys.path.insert(0,str(SOURCE))
SEVEN=('manage.py','native_admin.py','guest_permissions.py','provisioning_diagnostics.py','host_tools.py','chrome_browser.py','native_launch.py')
def body(text,name):
 node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)and n.name==name)
 return ''.join(text.splitlines(keepends=True)[node.lineno-1:node.end_lineno])
class SevenClosure(unittest.TestCase):
 def test_literal_seven_and_reviewed_helper_and_chrome_bytes(self):
  self.assertEqual(probe.SOURCE_DEPENDENCIES,frozenset(SEVEN));probe.verify_reviewed_sources(SOURCE)
  self.assertEqual(hashlib.sha256((SOURCE/'native_launch.py').read_bytes()).hexdigest(),'5358a62e101c2fc8fc94063b6ec617a9a221b93b6778f59fc80cac2171ccc581')
  self.assertEqual(hashlib.sha256((SOURCE/'chrome_browser.py').read_bytes()).hexdigest(),'4220e1c5d656d95c93d68e649eeffef086bff6ab6a894435c47b0ef354408d21')
 def test_old_five_root_six_and_fda_six_refuse_before_import_ports_or_child(self):
  good=probe.reviewed_source_pins()
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);repo=root/'repo';lab=root/'lab';out=root/'out';meta=root/'meta';source=repo/'browser-client/lab'
   for p in(source,lab,out,meta):p.mkdir(parents=True,mode=0o700)
   for n in SEVEN:(source/n).write_bytes((SOURCE/n).read_bytes())
   for remove in(('chrome_browser.py','native_launch.py'),('native_launch.py',),('chrome_browser.py',)):
    pins={n:h for n,h in good.items()if n not in remove};(meta/'source-pins.json').write_text(json.dumps(pins))
    with self.subTest(remove=remove),patch.object(probe,'HERE',meta),patch.object(probe,'free_ports')as ports,patch.object(probe.importlib.util,'spec_from_file_location')as importing,patch.object(probe.subprocess,'Popen')as child:
     with self.assertRaisesRegex(ValueError,'^probe-reviewed-source-schema-changed$'):probe.prepare(repo,lab,out)
     ports.assert_not_called();importing.assert_not_called();child.assert_not_called()
 def test_duplicate_unknown_missing_bad_digest_and_original_4k_cap(self):
  good=probe.reviewed_source_pins()
  texts=[json.dumps(good)[:-1]+',"manage.py":'+json.dumps(good['manage.py'])+'}',json.dumps({**good,'caller.py':'a'*64}),json.dumps({n:h for n,h in good.items()if n!='native_launch.py'}),' '*4097]
  texts +=[json.dumps({**good,'native_launch.py':v})for v in(False,'A'*64,'a'*63,'/private/secret')]
  with tempfile.TemporaryDirectory()as tmp:
   meta=Path(tmp)
   for text in texts:
    (meta/'source-pins.json').write_text(text)
    with self.subTest(kind=text[:25]),patch.object(probe,'HERE',meta),patch.object(probe,'sha')as full_hash:
     with self.assertRaises(ValueError):probe.verify_reviewed_sources(SOURCE)
     full_hash.assert_not_called()
 def test_same_schema_with_previous_manage_digest_refuses_and_no_pin_repair(self):
  good=probe.reviewed_source_pins();old=json.loads((HERE/'fixtures/source-pins-six-chrome-before.json').read_text());bad={**good,'manage.py':old['manage.py']}
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp)/'source-pins.json';p.write_text(json.dumps(bad));before=p.read_bytes()
   with patch.object(probe,'HERE',p.parent),self.assertRaisesRegex(ValueError,'^probe-reviewed-source-changed$'):probe.verify_reviewed_sources(SOURCE)
   self.assertEqual(p.read_bytes(),before)
 def test_whole_current_six_probe_and_original_coherence_bodies_recover(self):
  import test_source_coherence as history
  text=(HERE/'probe.py').read_text();restored=history.recover_managed_source(text)
  self.assertEqual(restored,(HERE/'fixtures/probe-six-chrome-before.py.txt').read_text())
  for mutated in(text.replace('SOURCE_DEPENDENCIES=', 'CALLER_DEPENDENCIES=',1),text.replace('4096)','65536)',1),text+'\n# unknown delta\n'):
   with self.assertRaises(ValueError):history.recover_managed_source(mutated)
  old=ast.parse((HERE/'fixtures/source-coherence-six-chrome-before.py.txt').read_text());new=ast.parse((HERE/'test_source_coherence.py').read_text())
  extract=lambda t:{n.name:ast.dump(n,include_attributes=False)for c in t.body if isinstance(c,ast.ClassDef)for n in c.body if isinstance(n,ast.FunctionDef)and n.name.startswith('test_')}
  self.assertEqual(extract(old),extract(new))
 def test_default_probe_mode_and_opt_in_retains_only_fixed_launch_arguments(self):
  source=(HERE/'probe.py').read_text();tree=ast.parse(source);run=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='run')
  original_try=next(n for n in run.body if isinstance(n,ast.Try))
  start=next(i for i,n in enumerate(original_try.body)if isinstance(n,ast.Assign)and any(isinstance(t,ast.Name)and t.id=='observer_command'for t in n.targets))
  nodes=original_try.body[start:start+2]
  for confined,flag in((False,'--managed-domain'),(True,'--confined-diagnostic')):
   scope={'sys':types.SimpleNamespace(executable='python-owned'),'HERE':Path('/owned/fixed/probe'),'Path':Path,'output':'/owned/output','confined_diagnostic':confined,'out':{}}
   exec(compile(ast.Module(body=nodes,type_ignores=[]),'existing-probe-prefix','exec'),scope)
   self.assertEqual(scope['observer_command'],['python-owned','/owned/fixed/probe/observer.py','--configuration','/owned/output/launch.private.json',flag])
class ManagedSource(unittest.TestCase):
 def test_reviewed_lifetime_delta_recovers_original_stop_and_preserves_chrome_main(self):
  import manage
  spec=json.loads((HERE/'fixtures/managed-seven-manage-recovery.json').read_text());text=(SOURCE/'manage.py').read_text();restored=text
  for anchor in reversed(spec['anchors']):self.assertEqual(restored.count(anchor['after']),1);restored=restored.replace(anchor['after'],anchor['before'],1)
  self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),spec['beforeSHA256'])
  self.assertNotEqual(body(text,'stop'),body(restored,'stop'));self.assertEqual(body(text,'main'),body(restored,'main'))
  self.assertNotIn('webbrowser',text);self.assertNotIn('runtime/admin.json',text)
 def test_sealed_descriptor_is_forwarded_by_actual_launch_without_service(self):
  import manage
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);(root/'logs').mkdir();state_path=root/'processes.json';state={};process=types.SimpleNamespace(pid=123,poll=lambda:None)
   with patch.object(manage,'ROOT',root),patch.object(manage,'STATE',state_path),patch.object(manage.subprocess,'Popen',return_value=process)as launched,patch.object(manage,'start_ticks',return_value='known-CPU-birth'),patch.object(manage.time,'sleep'),contextlib.redirect_stdout(io.StringIO()):
    manage.launch('domain',['python','fixed-helper','--managed-fd','42'],{'HOME':'cpu-fixture'},state,pass_fds=(42,))
   self.assertEqual(launched.call_args.kwargs['pass_fds'],(42,));self.assertTrue(launched.call_args.kwargs['start_new_session']);self.assertNotIn('shell',launched.call_args.kwargs)
   self.assertEqual(state['domain']['startTicks'],'known-CPU-birth')
 def test_preparation_refuses_nonprivate_root_before_artifact_or_launch(self):
  import manage
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);root.chmod(0o755)
   with patch.object(manage,'ROOT',root),patch.object(manage,'load_state',return_value={}),patch.object(manage,'run')as build,patch.object(manage.subprocess,'Popen')as child,patch.object(manage.urllib.request,'urlretrieve')as download:
    with self.assertRaisesRegex(ValueError,'^confined-private-directory-refused$'):manage.prepare()
    build.assert_not_called();child.assert_not_called();download.assert_not_called()
 def test_actual_stage_loop_copies_exact_helper_from_lab_and_facade_from_atomic(self):
  import stage
  tree=ast.parse((HERE/'stage.py').read_text());f=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='main')
  loop=next(n for n in f.body if isinstance(n,ast.For)and isinstance(n.iter,ast.Name)and n.iter.id=='FILES')
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);(root/'probe').mkdir(mode=0o700)
   exec(compile(ast.Module(body=[loop],type_ignores=[]),'existing-stage-loop','exec'),{'FILES':stage.FILES,'HERE':HERE,'base':root,'write':stage.write,'regular':stage.regular})
   self.assertEqual((root/'probe/native_launch.py').read_bytes(),(SOURCE/'native_launch.py').read_bytes());self.assertEqual((root/'probe/confined_launch.py').read_bytes(),(HERE/'confined_launch.py').read_bytes())
   self.assertEqual(set(p.name for p in(root/'probe').iterdir()),set(stage.FILES))
 def test_confinement_dto_rejects_unknown_profile_field_and_false_cap_claim(self):
  from curate import project
  row={'schemaVersion':1,'scope':'standalone-fresh-domain-provisioning-probe-not-nineteen-stage-world-lifecycle','completed':False,'phase':'preparation','endpointOwnership':'not-observed','provisioning':'not-requested','diagnosticLaunch':'managed-domain-fixed-tmpfile-denial','nativeConfinement':{n:False for n in('zeroCapabilities','noNewPrivileges','userIsolated','ipcIsolated','identityStable','seccompFiltered','allThreadsConfined')}}
  row['nativeConfinement']['profile']='unqualified';self.assertFalse(project(row)['completed'])
  for bad in({**row['nativeConfinement'],'token':'private'},{**row['nativeConfinement'],'profile':'/private/label'},{**row['nativeConfinement'],'zeroCapabilities':1}):
   with self.assertRaises(ValueError):project({**row,'nativeConfinement':bad})
if __name__=='__main__':unittest.main()
