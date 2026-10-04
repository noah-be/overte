#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Genuine own CPU children only; no Qt/display/browser/process simulation."""
import ast,ctypes,hashlib,io,json,os,signal,subprocess,sys,tempfile,time,unittest
from unittest.mock import Mock,patch
from pathlib import Path
HERE=Path(__file__).resolve().parent
AFTER=HERE/'run.py'
parsed=ast.parse(AFTER.read_text());node=next(n for n in parsed.body if isinstance(n,ast.ClassDef)and n.name=='OwnedRendererGroup')
ns={'ctypes':ctypes,'os':os,'Path':Path,'signal':signal,'subprocess':subprocess,'time':time}
exec(compile(ast.Module(body=[node],type_ignores=[]),str(AFTER),'exec'),ns)
Group=ns['OwnedRendererGroup']

def setUpModule():
 # This required Linux guard cannot become a green skipped qualification on an
 # unsupported OS, Python build or kernel. No Qt/runtime resource is needed.
 if sys.platform!='linux' or not all(callable(getattr(o,n,None)) for o,n in [(os,'fork'),(os,'pidfd_open'),(signal,'pidfd_send_signal')]) or not callable(getattr(ctypes.CDLL(None),'prctl',None)):
  raise RuntimeError('Required Linux owned-renderer CPU facilities are unavailable; qualification refused')
 try:
  descriptor=os.pidfd_open(os.getpid())
  try:signal.pidfd_send_signal(descriptor,0)
  finally:os.close(descriptor)
 except OSError as error:
  raise RuntimeError('Required Linux pidfd kernel facility is unavailable; qualification refused') from error

class PureIdentity(unittest.TestCase):
 def group(self):
  g=Group();g.leader=700;g.birth=100;g.seen={700:100};return g
 def row(self,**updates):
  x={'pid':700,'state':'S','parent':os.getpid(),'group':700,'session':700,'birth':100,'uid':os.getuid()};x.update(updates);return x
 def setUp(self):
  self.previous=ctypes.c_int();self.assertEqual(ctypes.CDLL(None).prctl(37,ctypes.byref(self.previous),0,0,0),0)
 def tearDown(self):self.assertEqual(ctypes.CDLL(None).prctl(36,self.previous.value,0,0,0),0)
 def test_unknown_group_parent_is_refused(self):
  g=self.group()
  with self.assertRaisesRegex(RuntimeError,'unknown-group'):g.validate([self.row(pid=701,parent=999)])
 def test_reused_birth_wrong_session_owner_and_group_refuse(self):
  for change in [{'birth':101},{'session':701},{'uid':os.getuid()+1},{'group':701}]:
   with self.subTest(change=change):
    g=self.group()
    with self.assertRaises(RuntimeError):g.validate([self.row(**change)])
 def test_reentrant_adoption_and_parent_order_are_authenticated(self):
  g=self.group();rows=[self.row(pid=702,parent=701,birth=101),self.row(pid=701,parent=os.getpid(),birth=101)]
  self.assertEqual(g.validate(rows),rows);self.assertEqual(g.seen[702],101)
 def test_group_and_proc_bounds_refuse(self):
  g=self.group()
  with self.assertRaisesRegex(RuntimeError,'group-bound'):g.validate([self.row()]*129)
  g.seen.update({p:100 for p in range(800,1055)})
  with self.assertRaisesRegex(RuntimeError,'birth-bound'):g.validate([self.row(pid=701,birth=101)])
 def test_unobserved_existing_group_is_refused_without_signal_or_reap(self):
  g=self.group();g.members=lambda:[];g.signal=Mock();g.reap=Mock()
  with patch.object(os,'killpg',return_value=None):
   with self.assertRaisesRegex(RuntimeError,'unobserved-group'):g.stop(Mock())
  g.signal.assert_called_once_with([],signal.SIGTERM);g.reap.assert_called_once_with([])
 def test_reap_never_waits_for_an_unadopted_member(self):
  g=self.group();row=self.row(pid=701,parent=700,birth=101)
  with patch.object(os,'waitpid',side_effect=AssertionError('foreign wait')):g.reap([row])
 def test_failed_unbound_stop_restores_previous_subreaper_and_never_signals(self):
  libc=ctypes.CDLL(None);before=ctypes.c_int();self.assertEqual(libc.prctl(37,ctypes.byref(before),0,0,0),0)
  g=Group();g.leader=700;g.signal=Mock()
  with self.assertRaisesRegex(RuntimeError,'unbound-group'):g.stop(Mock())
  after=ctypes.c_int();self.assertEqual(libc.prctl(37,ctypes.byref(after),0,0,0),0);self.assertEqual(after.value,before.value);g.signal.assert_not_called()
 def test_discovery_children_byte_and_count_bounds_refuse(self):
  for data in [b'1 '*4097,b'1 '*129,b'unknown']:
   with self.subTest(size=len(data)):
    g=self.group()
    with patch.object(Path,'open',return_value=io.BytesIO(data)):
     with self.assertRaisesRegex(RuntimeError,'children-bound'):g.members()
 def test_discovery_does_not_enumerate_foreign_processes(self):
  g=self.group()
  with patch.object(Path,'iterdir',side_effect=AssertionError('global scan')),patch.object(Path,'open',return_value=io.BytesIO(b'')):
   self.assertEqual(g.members(),[])
 def test_failed_unknown_stop_restores_previous_subreaper(self):
  g=self.group();g.members=Mock(side_effect=RuntimeError('unknown-group'))
  with self.assertRaisesRegex(RuntimeError,'unknown-group'):g.stop(Mock())
  after=ctypes.c_int();self.assertEqual(g.libc.prctl(37,ctypes.byref(after),0,0,0),0);self.assertEqual(after.value,g.previous)
 def test_existing_capture_function_and_editor_oracles_unchanged(self):
  # Literal SHA-256 oracles derive from the approved original c843 runner;
  # no historical runtime fallback or external packet input is used.
  source=AFTER.read_text();tree=ast.parse(source)
  expected={'sha': '50f6306d242a45d4116b6d4b24364b6240ccb398b96f76eb94ad268c5b2af875', 'run': 'c2b7bde6eaf303ce7a6c25020570ca7992710446bac56b123bcf41b400562d6f', 'capture_bounded': '907f76860b85fae89682945628671c5683a5514a9d18be4d5421e56be041cef7'}
  for name,digest in expected.items():
   node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name==name)
   self.assertEqual(hashlib.sha256(ast.get_source_segment(source,node).encode()).hexdigest(),digest)
  start="    stdout,stderr,output_truncated=capture_bounded(native,65)"
  end="except (OSError, AssertionError, RuntimeError, subprocess.SubprocessError, ValueError) as error:"
  self.assertEqual(source.count(start),1);self.assertEqual(source.count(end),1)
  self.assertEqual(hashlib.sha256(source[source.index(start):source.index(end)].encode()).hexdigest(),'c8cfded751262eb7d2eb3ff91e02d9f84cd95205872856c6273a5d57a3b2629a')

class RealProcesses(unittest.TestCase):
 def scenario(self,body):
  # A new Python owner isolates the Linux subreaper attribute and all real
  # descendants from unittest and the operator/managed laboratory processes.
  prelude='''import ast,ctypes,json,os,signal,subprocess,sys,time
from pathlib import Path
p=Path(sys.argv[1]);n=next(x for x in ast.parse(p.read_text()).body if isinstance(x,ast.ClassDef)and x.name=='OwnedRendererGroup')
s=globals();exec(compile(ast.Module(body=[n],type_ignores=[]),str(p),'exec'),s)
'''
  with tempfile.TemporaryDirectory(prefix='owned-reap-cpu-') as private:
   f=Path(private)/'scenario.py';f.write_text(prelude+body)
   r=subprocess.run([sys.executable,'-B',str(f),str(AFTER)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=8,start_new_session=True)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(json.loads(r.stdout),{'closed':True})
 def test_original_group_existence_negative_and_true_zombie_reap(self):
  self.scenario('''g=OwnedRendererGroup()
p=subprocess.Popen([sys.executable,'-c','import os,time; p=os.fork(); time.sleep(.05) if p else None; os._exit(0)'],start_new_session=True)
g.bind(p);p.wait(timeout=2)
rows=g.members();assert rows and all(x['parent']==os.getpid() for x in rows)
assert any(x['state']=='Z' for x in rows)
# Original killpg(0) still reports a group containing unreaped zombies.
os.killpg(p.pid,0)
assert g.stop(p);assert not g.members()
try:os.killpg(p.pid,0);raise AssertionError('original group still exists')
except ProcessLookupError:pass
print(json.dumps({'closed':True}))
''')
 def test_live_double_orphan_is_retired_and_reaped(self):
  self.scenario('''g=OwnedRendererGroup()
script='import os,time; a=os.fork(); b=os.fork() if a else 1; time.sleep(.1) if a and b else time.sleep(30); os._exit(0)'
p=subprocess.Popen([sys.executable,'-c',script],start_new_session=True)
g.bind(p);p.wait(timeout=2)
assert len(g.members())==2;assert g.stop(p);assert not g.members()
print(json.dumps({'closed':True}))
''')
 def test_sigterm_ignored_descendant_is_killed_within_original_bound(self):
  self.scenario('''g=OwnedRendererGroup()
script='import os,signal,time; p=os.fork(); signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(.1) if p else time.sleep(30); os._exit(0)'
p=subprocess.Popen([sys.executable,'-c',script],start_new_session=True)
g.bind(p);p.wait(timeout=2);start=time.monotonic();assert g.stop(p);assert time.monotonic()-start<5
print(json.dumps({'closed':True}))
''')
 def test_unrelated_own_child_is_not_signaled_or_reaped(self):
  self.scenario('''other=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
g=OwnedRendererGroup();p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.05)'],start_new_session=True);g.bind(p)
try:
 assert g.stop(p);assert other.poll() is None
finally:other.terminate();other.wait(timeout=2)
print(json.dumps({'closed':True}))
''')
 def test_actual_reap_omission_mutant_remains_a_failed_cleanup(self):
  self.scenario('''g=OwnedRendererGroup()
p=subprocess.Popen([sys.executable,'-c','import os,time; p=os.fork(); time.sleep(.05) if p else None; os._exit(0)'],start_new_session=True)
g.bind(p);p.wait(timeout=2);assert any(x['state']=='Z' for x in g.members())
original=g.reap;g.reap=lambda rows:None;start=time.monotonic()
assert not g.stop(p);assert 5<=time.monotonic()-start<6;assert g.members()
g.reap=original;assert g.stop(p);assert not g.members()
print(json.dumps({'closed':True}))
''')
if __name__=='__main__':unittest.main()
