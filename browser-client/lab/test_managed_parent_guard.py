"""Actual helper methods with mocked parent/kernel records; no existing process reads."""
import ctypes,errno,importlib.util,json,os,signal,stat,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('actual_parent_helper',HERE/'native_launch.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ParentGuards(unittest.TestCase):
 def setUp(self):
  self.expected={'pid':10001,'startTicks':'101','uid':os.getuid(),'gid':os.getgid()}
  self.parent={**self.expected,'pid':10002,'startTicks':'102','parent':10001}
  self.owner={**self.expected,'parent':50}
 def chain(self):return [dict(self.parent),dict(self.owner)]
 def invoke(self,*,chains=None,readback=signal.SIGKILL,set_result=0,get_result=0,ready=None,ppid=10002):
  chains=chains or[self.chain(),self.chain(),self.chain()]
  def prctl(option,arg,*unused):
   if option==1:return set_result
   if option==2:arg._obj.value=readback;return get_result
   raise AssertionError('unknown prctl')
  library=SimpleNamespace(prctl=Mock(side_effect=prctl));poll=SimpleNamespace(register=Mock(),poll=Mock(side_effect=ready or[[],[]]));closed=[]
  with patch.object(m,'_parent_chain',side_effect=chains),patch.object(m.os,'pidfd_open',side_effect=[70,71]),patch.object(m.os,'close',side_effect=closed.append),patch.object(m.os,'getppid',return_value=ppid),patch.object(m.ctypes,'CDLL',return_value=library),patch('select.poll',return_value=poll):
   try:m.bind_managed_parent(self.expected)
   finally:self.assertEqual(closed,[70,71])
  return library
 def test_actual_set_get_and_descriptor_retirement(self):
  library=self.invoke();self.assertEqual([call.args[0]for call in library.prctl.call_args_list],[1,2])
 def test_wrong_readback_or_prctl_failure_refuses(self):
  for change in({'readback':0},{'set_result':-1},{'get_result':-1}):
   with self.subTest(change=change),self.assertRaisesRegex(ValueError,'binding'):self.invoke(**change)
 def test_parent_death_ready_before_or_after_setting_refuses(self):
  for ready in([[(70,1)],[]],[[],[(71,1)]]):
   with self.assertRaisesRegex(ValueError,'binding'):self.invoke(ready=ready)
 def test_setup_reparent_reuse_or_uid_change_refuses(self):
  for field,value in(('parent',60),('startTicks','202'),('uid',os.getuid()+1)):
   changed=self.chain();changed[0][field]=value
   with self.assertRaisesRegex(ValueError,'binding'):self.invoke(chains=[self.chain(),changed])
  with self.assertRaisesRegex(ValueError,'binding'):self.invoke(ppid=77)
 def test_partial_pidfd_open_failure_closes_first_descriptor(self):
  closed=[]
  with patch.object(m,'_parent_chain',return_value=self.chain()),patch.object(m.os,'pidfd_open',side_effect=[70,PermissionError('CPU-only')]),patch.object(m.os,'close',side_effect=closed.append),self.assertRaises(PermissionError):m.bind_managed_parent(self.expected)
  self.assertEqual(closed,[70])
 def test_ancestry_reaches_only_exact_sealed_supervisor(self):
  with patch.object(m.os,'getppid',return_value=10002),patch.object(m,'_process_identity',side_effect=[self.parent,self.owner]):self.assertEqual(m._parent_chain(self.expected),self.chain())
 def test_same_uid_adopter_outside_expected_chain_refuses(self):
  adopter={**self.parent,'pid':20002,'parent':1}
  with patch.object(m.os,'getppid',return_value=20002),patch.object(m,'_process_identity',return_value=adopter),self.assertRaisesRegex(ValueError,'ancestry'):m._parent_chain(self.expected)
 def test_expected_supervisor_reuse_refuses(self):
  reused={**self.owner,'startTicks':'999'}
  with patch.object(m.os,'getppid',return_value=10002),patch.object(m,'_process_identity',side_effect=[self.parent,reused]),self.assertRaisesRegex(ValueError,'supervisor'):m._parent_chain(self.expected)
 def test_unbounded_loop_unknown_or_pid_one_refuses(self):
  for ppid,row in((1,self.parent),(10002,{**self.parent,'parent':10002})):
   with patch.object(m.os,'getppid',return_value=ppid),patch.object(m,'_process_identity',return_value=row),self.assertRaises(ValueError):m._parent_chain(self.expected)
 def test_final_record_strict_extra_field_and_duplicates(self):
  initial={'version':1,'lab':'private','repo':'source','environment':{},'policy':{},'parentUser':'user:[1]','parentIPC':'ipc:[2]'}
  final={**initial,'supervisor':self.expected}
  with patch.object(m,'checked_managed_record',return_value=initial)as checked:
   self.assertEqual(m.checked_managed_final_record(json.dumps(final).encode()),final)
   self.assertEqual(set(json.loads(checked.call_args.args[0])),set(initial))
   for document in(initial,{**final,'unknown':False},{**final,'supervisor':{**self.expected,'uid':True}}):
    with self.assertRaises(ValueError):m.checked_managed_final_record(json.dumps(document).encode())
   raw=json.dumps(final).encode().replace(b'"supervisor":',b'"supervisor":{},"supervisor":')
   with self.assertRaisesRegex(ValueError,'duplicate'):m.checked_managed_final_record(raw)
 def test_final_producer_sealed_fd_actual_consumer(self):
  initial={'version':1,'lab':'private','repo':'source','environment':{},'policy':{},'parentUser':'user:[1]','parentIPC':'ipc:[2]'}
  captured=[];fd=m.sealed_record(b'CPU-owned-initial-record')
  def supervised(command,descriptors):
   self.assertEqual(len(descriptors),2);self.assertEqual(command[command.index('--ro-bind-data')+1],str(descriptors[0]))
   raw=os.pread(descriptors[0],65537,0);captured.append(raw)
   with patch.object(m,'checked_managed_record',return_value=initial):self.assertEqual(m.checked_managed_final_record(raw)['supervisor'],self.expected)
   return 7
  try:
   with patch.object(m,'checked_managed_record',return_value=initial),patch.object(m,'_process_identity',return_value={**self.expected,'parent':50}),patch.object(m,'sealed_filter',side_effect=lambda:m.sealed_record(b'CPU-owned-filter-placeholder')),patch.object(m,'base_command',return_value=['/usr/bin/bwrap','--new-session']),patch.object(m,'supervise',side_effect=supervised):self.assertEqual(m.exec_managed(fd),7)
   self.assertEqual(len(captured),1)
  finally:os.close(fd)

class NativePrivilege(unittest.TestCase):
 def invoke(self,mode=0o100755,xattr_errno=errno.ENODATA,xattr_present=False,nnp=b'NoNewPrivs:\t1\n',content=b'fixed-owned-CPU-bytes'):
  info=SimpleNamespace(st_mode=mode,st_uid=os.getuid(),st_size=len(content),st_dev=1,st_ino=2,st_ctime_ns=3)
  opened=[];closed=[];reads={91:0,92:0}
  def openfd(*args,**kwargs):fd=91+len(opened);opened.append(fd);return fd
  def read(fd,count):
   reads[fd]+=1
   return(content if reads[fd]==1 else b'')if fd==91 else nnp
  with patch.object(m.os,'open',side_effect=openfd),patch.object(m.os,'close',side_effect=closed.append),patch.object(m.os,'fstat',return_value=info),patch.object(m.os,'getxattr',side_effect=None if xattr_present else OSError(xattr_errno,'private-error'),return_value=b''),patch.object(m.os,'read',side_effect=read),patch.object(m,'NATIVE_SHA256',m.hashlib.sha256(content).hexdigest()):
   try:m.require_unprivileged_native('CPU-owned-fixed-native')
   finally:self.assertEqual(sorted(closed),sorted(opened))
 def test_exact_regular_nonprivileged_owned_nnp_one_passes(self):self.invoke()
 def test_setuid_setgid_or_nonregular_refuses(self):
  for mode in(0o104755,0o102755,0o010755):
   with self.assertRaisesRegex(ValueError,'privilege'):self.invoke(mode=mode)
 def test_present_capability_or_unknown_xattr_error_refuses(self):
  with self.assertRaises(ValueError):self.invoke(xattr_present=True)
  for value in(errno.EACCES,errno.ENOTSUP,errno.EIO):
   with self.assertRaises(ValueError):self.invoke(xattr_errno=value)
 def test_missing_false_duplicate_or_unbounded_nnp_refuses(self):
  for value in(b'',b'NoNewPrivs:\t0\n',b'NoNewPrivs:\t1\nNoNewPrivs:\t1\n',b'x'*65537):
   with self.assertRaises(ValueError):self.invoke(nnp=value)

class AdmitRetirement(unittest.TestCase):
 def test_actual_admit_identity_exception_retires_opened_fd(self):
  import ast,time
  source=(HERE/'manage.py').read_text();node=next(n for n in ast.parse(source).body if isinstance(n,ast.ClassDef)and n.name=='_OwnedStop')
  scope={'Path':Path,'os':os,'signal':signal,'time':time};exec(compile(ast.Module(body=[node],type_ignores=[]),'actual-stop','exec'),scope)
  own=scope['_OwnedStop']({'pid':10001,'startTicks':'101'});row=dict(pid=10001,birth='101',parent=50,group=10001,session=10001,uid=os.getuid());closed=[]
  with patch.object(os,'pidfd_open',return_value=771),patch.object(os,'close',side_effect=closed.append),patch.object(own,'identity',side_effect=PermissionError('CPU-only')):
   with self.assertRaises(PermissionError):own.admit(row)
   own.close()
  self.assertEqual(closed,[771]);self.assertEqual(own.descriptors,{})

if __name__=='__main__':unittest.main(verbosity=2)
