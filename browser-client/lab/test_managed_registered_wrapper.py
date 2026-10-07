"""Exact managed readback consumer with bounded fake owned tree; no /proc reads."""
import ast,importlib.util,os,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('actual_registered_helper',HERE/'native_launch.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Registered(unittest.TestCase):
 def setUp(self):
  self.wrapper=dict(pid=10001,startTicks='101',uid=os.getuid(),gid=os.getgid(),parent=50,group=10001,session=10001)
  self.native=dict(pid=10002,startTicks='102',uid=os.getuid(),gid=os.getgid(),parent=10001,group=10001,session=10001)
  self.rows={10001:self.wrapper,10002:self.native};self.closed=[]
 def invoke(self,expected='101',endpoint=True,changed_after=False):
  def identities(pid):return dict(self.rows[pid])
  def endpoint_read(pid):
   if changed_after:self.rows[10001]['startTicks']='999'
   return endpoint
  profile={'zeroCapabilities':True,'noNewPrivileges':True,'userIsolated':True,'ipcIsolated':True,'profile':'signed-bwrap-child-enforce','identityStable':True,'seccompFiltered':True,'allThreadsConfined':True}
  poll=SimpleNamespace(register=Mock(),poll=Mock(return_value=[]))
  with patch.object(m,'_process_identity',side_effect=identities),patch.object(m,'_managed_children',side_effect=lambda row:[10002]if row['pid']==10001 else[]),patch.object(m.os,'pidfd_open',side_effect=[71,72]),patch.object(m.os,'close',side_effect=self.closed.append),patch.object(m.os.path,'samefile',side_effect=lambda path,native:path.parent.name=='10002'),patch.object(m,'native_endpoint_owned',side_effect=endpoint_read),patch.object(m,'confinement',return_value=profile),patch.object(m.os,'readlink',return_value='CPU-owned'),patch('select.poll',return_value=poll):
   return m.managed_confinement(10001,'fixed-native',{'kind':'apparmor','context':''},expected_start_ticks=expected)
 def test_live_recorded_wrapper_and_only_owned_native_pass(self):
  self.assertTrue(self.invoke()['identityStable']);self.assertEqual(self.closed,[71,72])
 def test_no_missing_none_bool_or_wrong_recorded_birth_bypass(self):
  with self.assertRaises(TypeError):m.managed_confinement(10001,'fixed-native',{})
  for value in(None,True,'','bad','999'):
   with self.assertRaises(ValueError):self.invoke(expected=value)
 def test_reuse_before_discovery_refuses_without_any_pidfd_signal(self):
  with self.assertRaises(ValueError):self.invoke(expected='202')
  self.assertEqual(self.closed,[])
 def test_reuse_after_endpoint_native_readback_refuses_and_closes_all(self):
  with self.assertRaises(ValueError):self.invoke(changed_after=True)
  self.assertEqual(self.closed,[71,72])
 def test_changed_group_or_session_refuses_before_discovery(self):
  for key in('group','session'):
   self.wrapper[key]=20001
   with self.assertRaises(ValueError):self.invoke()
   self.wrapper[key]=10001
 def test_unowned_child_ancestry_refuses(self):
  self.native['parent']=20001
  with self.assertRaisesRegex(ValueError,'ancestry'):self.invoke()
  self.assertEqual(self.closed,[71])
 def test_endpoint_refusal_closes_all_descriptors(self):
  with self.assertRaisesRegex(ValueError,'endpoint'):self.invoke(endpoint=False)
  self.assertEqual(self.closed,[71,72])
 def test_snapshot_exception_after_open_closes_every_admitted_fd(self):
  with patch.object(m,'_managed_wrapper',side_effect=[self.wrapper,PermissionError('CPU-only')]),patch.object(m.os,'pidfd_open',return_value=71),patch.object(m.os,'close',side_effect=self.closed.append),self.assertRaises(PermissionError):m._managed_native_snapshot(10001,'fixed-native','101')
  self.assertEqual(self.closed,[71])
 def test_tree_bound_cycle_refuses_and_retires_fds(self):
  with patch.object(m,'_managed_wrapper',return_value=self.wrapper),patch.object(m,'_process_identity',side_effect=lambda pid:self.rows[pid]),patch.object(m,'_managed_children',return_value=[10001]),patch.object(m.os,'pidfd_open',return_value=71),patch.object(m.os,'close',side_effect=self.closed.append),patch.object(m.os.path,'samefile',return_value=False),self.assertRaises(ValueError):m._managed_native_snapshot(10001,'fixed-native','101')
  self.assertEqual(self.closed,[71])
 def test_exact_callers_pass_the_original_stored_birth(self):
  manage=(HERE/'manage.py').read_text();probe=(HERE/'atomic-provisioning/probe.py').read_text()
  self.assertIn('expected_start_ticks=state["domain"]["startTicks"]',manage)
  self.assertIn("observer_birth=manage.start_ticks(process.pid)",probe)
  self.assertIn("'startTicks':observer_birth",probe)
  self.assertIn('expected_start_ticks=observer_birth',probe)
  for text in(manage,probe):ast.parse(text)
 def test_legacy_unregistered_discovery_body_byte_exact(self):
  before=(HERE/'fixtures/native-launch-original-fda.py').read_text();after=(HERE/'native_launch.py').read_text()
  def body(text):return ast.get_source_segment(text,next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)and n.name=='owned_native_pid'))
  self.assertEqual(body(before),body(after))
if __name__=='__main__':unittest.main(verbosity=2)
