"""Owned controlled sibling/PYTHONPATH fixtures and system Python source guards."""
import importlib.util,json,os,stat,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('actual_isolated_python',HERE/'native_launch.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class PythonBoundary(unittest.TestCase):
 def test_actual_entry_and_final_commands_use_exact_isolation_flags(self):
  document={'version':1,'lab':'fixed','repo':'fixed','environment':{},'policy':{},'parentUser':'user:[1]','parentIPC':'ipc:[2]'}
  with patch.object(m,'managed_document',return_value=document):
   with m.managed_command('fixed','fixed',{})as(command,env,fd,policy):
    self.assertEqual(command[1:4],['-I','-S','-B']);self.assertEqual(command[0],m.trusted_python());self.assertEqual(command[4],str(HERE/'native_launch.py'))
  fd=m.sealed_record(b'fixed');seen=[]
  try:
   with patch.object(m,'checked_managed_record',return_value=document),patch.object(m,'_process_identity',return_value={'pid':123,'startTicks':'101','uid':os.getuid(),'gid':os.getgid()}),patch.object(m,'base_command',return_value=['/usr/bin/bwrap','--new-session']),patch.object(m,'supervise',side_effect=lambda c,d:seen.append(c)or 0):m.exec_managed(fd)
   command=seen[0];delimiter=command.index('--');self.assertEqual(command[delimiter+2:delimiter+5],['-I','-S','-B']);self.assertEqual(command[delimiter+1],m.trusted_python())
  finally:os.close(fd)
 def test_controlled_ctypes_sibling_old_executes_isolated_does_not(self):
  with tempfile.TemporaryDirectory(prefix='controlled-stdlib-only-CPU-')as name:
   root=Path(name);root.chmod(0o700);helper=root/'native_launch.py';helper.write_bytes((HERE/'native_launch.py').read_bytes());helper.chmod(0o600)
   marker=root/'shadow-executed.private';(root/'ctypes.py').write_text('from pathlib import Path\nPath(__file__).with_name("shadow-executed.private").write_bytes(b"controlled-CPU-only")\nraise RuntimeError("controlled-sibling-shadow")\n')
   env=m.host_environment()
   old=subprocess.run([m.trusted_python(),'-B',str(helper),'--help'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=2)
   self.assertNotEqual(old.returncode,0);self.assertTrue(marker.is_file());marker.unlink()
   current=subprocess.run([m.trusted_python(),'-I','-S','-B',str(helper),'--help'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=2)
   self.assertEqual(current.returncode,0);self.assertFalse(marker.exists());self.assertFalse(list(root.rglob('*.pyc')))
 def test_pythonpath_user_site_and_global_site_startup_disabled(self):
  with tempfile.TemporaryDirectory(prefix='controlled-pythonpath-only-CPU-')as name:
   root=Path(name);root.chmod(0o700)
   (root/'sitecustomize.py').write_text('raise RuntimeError("controlled-site-startup")\n')
   env={**m.host_environment(),'PYTHONPATH':str(root),'PYTHONUSERBASE':str(root)}
   script='import sys,json;print(json.dumps({"isolated":sys.flags.isolated,"noSite":sys.flags.no_site,"noBytecode":sys.flags.dont_write_bytecode,"siteImported":"site"in sys.modules}))'
   result=subprocess.run([m.trusted_python(),'-I','-S','-B','-c',script],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=2)
   self.assertEqual(result.returncode,0);self.assertEqual(json.loads(result.stdout),{'isolated':1,'noSite':1,'noBytecode':1,'siteImported':False})
 def test_nonroot_writable_nonregular_or_privileged_interpreter_refuses(self):
  for change in({'st_uid':os.getuid()or 1},{'st_mode':0o100777},{'st_mode':0o104755},{'st_mode':0o102755},{'st_mode':0o010755}):
   info=SimpleNamespace(st_uid=0,st_mode=0o100755);info.__dict__.update(change)
   with patch.object(Path,'stat',return_value=info),patch.object(Path,'resolve',return_value=Path('/usr/bin/fixed-python')),self.assertRaisesRegex(ValueError,'python'):m.trusted_python()
if __name__=='__main__':unittest.main(verbosity=2)
