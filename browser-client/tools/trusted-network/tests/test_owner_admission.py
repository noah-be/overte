# SPDX-License-Identifier: Apache-2.0
import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('admission',BASE/'src'/'owner_admission.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def fixture():
 d='/tmp/overte-browser-CPUproof1';display=':1234'
 policy={'version':1,'hostUID':1000,'hostGID':1000,'sessionParent':'/tmp',
 'nativeExecutables':['/opt/overte/interface'],'nativeReadRoots':['/opt/overte']}
 attest={'version':1,'hostUID':1000,'hostGID':1000,'parentPID':42,'userNS':[1,2],'netNS':[1,3],'routes':12}
 env={'HOME':d,'TMPDIR':d+'/tmp','XDG_CONFIG_HOME':d+'/config','XDG_DATA_HOME':d+'/data',
 'XDG_CACHE_HOME':d+'/cache','XDG_RUNTIME_DIR':d,'XAUTHORITY':d+'/Xauthority','DBUS_SESSION_BUS_ADDRESS':'unix:path=/dev/null',
 'PULSE_SERVER':'unix:'+d+'/pulse.socket','PATH':'/usr/bin:/bin','LANG':'C.UTF-8','USER':'browser','LOGNAME':'browser',
 'LIBGL_ALWAYS_SOFTWARE':'1','DISPLAY':display}
 args=[v.replace('{uid}','1000').replace('{gid}','1000') for v in m.PREFIX]
 args+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp','--dir','/tmp/.X11-unix','--dir','/etc']
 args+=['--ro-bind','/opt/overte','/opt/overte','--bind',d,d,'--ro-bind',d+'/machine-id','/etc/machine-id',
 '--ro-bind',d+'/network-resolv.conf','/etc/resolv.conf','--ro-bind','/tmp/.X11-unix/X1234','/tmp/.X11-unix/X1234','--chdir',d]
 for key,value in env.items():args+=['--setenv',key,value]
 args+=['--','/opt/overte/interface','--defaultScriptsOverride',d+'/bridge.js']
 config={'command':'bwrap','args':args,'environment':env,'bridgePort':8090,'bridgeSocket':d+'/native-network.socket','supervisorParentPID':42}
 return config,policy,attest

class Admission(unittest.TestCase):
 def verify(self,config,policy,attest):return m.validate(config,policy,attest,filesystem=False)
 def test_exact_original_boundary_and_fixed_final_guard(self):
  config,p,a=fixture();before=copy.deepcopy(config)
  approved=self.verify(config,p,a)
  self.assertEqual(config,before)
  i=config['args'].index('--')+1
  self.assertEqual(approved['command'],'/usr/bin/bwrap')
  self.assertEqual(approved['args'],config['args'][:i]+['/usr/libexec/overte-browser-network/native-boundary-exec']+config['args'][i:])
 def test_explicit_canonical_python_probe_retains_boundary_without_gui_or_loader_env(self):
  config,p,a=fixture();d='/tmp/overte-browser-CPUproof1'
  p['nativeExecutables']=['/usr/bin/python3.12'];p['nativeReadRoots']=['/usr/lib/python3.12']
  args=config['args'];args[args.index('--')+1]='/usr/bin/python3.12'
  j=args.index('/tmp/.X11-unix/X1234')-1;del args[j:j+3]
  j=args.index('/opt/overte')-1;del args[j:j+3]
  while '--setenv' in args:
   j=args.index('--setenv');del args[j:j+3]
  config['environment']={'PATH':'/usr/bin:/bin'};j=args.index('--');args[j:j]=['--setenv','PATH','/usr/bin:/bin']
  self.verify(config,p,a)
  config['environment']['DISPLAY']=':1234';j=args.index('--');args[j:j]=['--setenv','DISPLAY',':1234']
  with self.assertRaisesRegex(m.Refusal,'headless-probe-environment'):self.verify(config,p,a)
 def test_public_and_pinned_managed_scope(self):
  config,p,a=fixture();self.verify(config,p,a)
  config['managedUDP']={'address':'127.0.0.2','ports':[45102,45200]}
  config['managedUDPSocket']='/tmp/overte-browser-CPUproof1/managed-udp.socket';self.verify(config,p,a)
 def test_all_namespace_and_no_new_session_or_environment_replacement_flags_refused(self):
  for flag in ['--unshare-user','--unshare-pid','--unshare-ipc','--unshare-uts','--die-with-parent','--new-session','--clearenv']:
   with self.subTest(flag=flag):
    config,p,a=fixture();config['args'].remove(flag)
    with self.assertRaises(m.Refusal):self.verify(config,p,a)
 def test_all_required_mounts_and_private_directory_are_mandatory(self):
  for target in ['/proc','/dev','/tmp','/tmp/.X11-unix','/etc','/etc/machine-id','/etc/resolv.conf','/tmp/overte-browser-CPUproof1']:
   config,p,a=fixture();i=config['args'].index(target)
   # Remove the actual flag/arguments containing target; either malformed or
   # absent required boundary must refuse, never be completed by a default.
   config['args'].pop(i)
   with self.assertRaises(m.Refusal):self.verify(config,p,a)
 def test_unknown_options_and_shared_net_or_pid_are_refused(self):
  for flag in ['--share-net','--share-user','--unshare-all','--cap-add','--preserve-fds','--bind-data','--remount-ro','--perms']:
   config,p,a=fixture();i=config['args'].index('--');config['args'][i:i]=[flag,'1']
   with self.assertRaises(m.Refusal):self.verify(config,p,a)
 def test_extra_writable_or_readonly_host_or_proc_bind_and_target_replacement_refused(self):
  for flag,src,target in [('--bind','/home/operator','/home/operator'),('--ro-bind','/home/operator','/home/operator'),
   ('--ro-bind','/etc/shadow','/etc/shadow'),('--ro-bind','/proc','/proc'),('--ro-bind','/opt/overte','/usr')]:
   config,p,a=fixture();i=config['args'].index('--');config['args'][i:i]=[flag,src,target]
   with self.assertRaises(m.Refusal):self.verify(config,p,a)
 def test_generic_command_and_executable_or_uid_gid_replacement_refused(self):
  for field,value in [('command','python3'),('command','/tmp/bwrap')]:
   config,p,a=fixture();config[field]=value
   with self.assertRaises(m.Refusal):self.verify(config,p,a)
  config,p,a=fixture();config['args'][-3]='/bin/sh'
  with self.assertRaises(m.Refusal):self.verify(config,p,a)
  config,p,a=fixture();config['args'][2]='0'
  with self.assertRaises(m.Refusal):self.verify(config,p,a)
 def test_bad_privileged_loader_env_or_same_key_override_refused(self):
  for key,value in [('PYTHONPATH','/tmp/evil'),('LD_PRELOAD','/tmp/evil.so'),('LD_LIBRARY_PATH','/tmp/evil'),
   ('PULSE_SERVER','unix:/run/other/socket'),('DISPLAY',':1'),('XAUTHORITY','/home/other/.Xauthority'),('HOME','/home/other')]:
   config,p,a=fixture();config['environment'][key]=value
   # Even consistently repeated values do not override fixed scope.
   for i,token in enumerate(config['args'][:-2]):
    if token=='--setenv' and config['args'][i+1]==key:config['args'][i+2]=value
   with self.assertRaises(m.Refusal):self.verify(config,p,a)
 def test_owner_arguments_cannot_point_to_sibling_or_broad_runtime(self):
  config,p,a=fixture();config['bridgeSocket']='/tmp/overte-browser-other1/native-network.socket'
  with self.assertRaises(m.Refusal):self.verify(config,p,a)
  for root in ['/','/home','/tmp','/proc','/home/operator/.ssh']:
   config,p,a=fixture();p['nativeReadRoots']=[root]
   with self.assertRaises(m.Refusal):self.verify(config,p,a)
 def test_wrong_route_count_caller_parent_boolean_metadata_and_extra_policy_refused(self):
  for key,value in [('routes',11),('hostUID',0),('parentPID',43),('version',True),('extra','untrusted')]:
   config,p,a=fixture();a[key]=value
   with self.assertRaises(m.Refusal):self.verify(config,p,a)
  config,p,a=fixture();p['version']=True
  with self.assertRaises(m.Refusal):self.verify(config,p,a)
 def test_native_managed_udp_scope_never_widens(self):
  for value in [{'address':'192.168.1.1','ports':[80]},{'address':'127.0.0.2','ports':[True]},
                {'address':'127.0.0.2','ports':[]},{'address':'127.0.0.2','ports':[65536]}]:
   config,p,a=fixture();config['managedUDP']=value;config['managedUDPSocket']='/tmp/overte-browser-CPUproof1/managed-udp.socket'
   with self.assertRaises(m.Refusal):self.verify(config,p,a)
 def test_control_bytes_oversized_record_and_missing_delimiter_refused(self):
  config,p,a=fixture();config['args'][-1]='bad\0value'
  with self.assertRaises(m.Refusal):self.verify(config,p,a)
  config,p,a=fixture();config['args'].remove('--')
  with self.assertRaises(m.Refusal):self.verify(config,p,a)
 def test_workspace_override_only_exact_reviewed_name_target_inside_pinned_native_root(self):
  config,p,a=fixture();i=config['args'].index('--');d='/tmp/overte-browser-CPUproof1'
  config['args'][i:i]=['--ro-bind',d+'/browser-snapshot.js','/opt/overte/scripts/system/snapshot.js'];self.verify(config,p,a)
  config['args'][i+1]=d+'/arbitrary.js'
  with self.assertRaises(m.Refusal):self.verify(config,p,a)
 def test_canonical_alias_refused_with_actual_temporary_symlink(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d);(path/'file').write_text('content');(path/'alias').symlink_to(path/'file')
   self.assertEqual(m.canonical(str(path/'file')),str(path/'file'))
   with self.assertRaises(m.Refusal):m.canonical(str(path/'alias'))

class SealedRecords(unittest.TestCase):
 def sealed(self,data,seals=m.SEALS):
  fd=os.memfd_create('overte-cpu-proof',os.MFD_ALLOW_SEALING);self.addCleanup(os.close,fd)
  os.write(fd,data);fcntl.fcntl(fd,fcntl.F_ADD_SEALS,seals);return fd
 def test_actual_sealed_memory_read_and_duplicate_key_refusal(self):
  self.assertEqual(m.read_sealed_json(self.sealed(b'{"version":1}')),{'version':1})
  with self.assertRaises(m.Refusal):m.read_sealed_json(self.sealed(b'{"version":1,"version":2}'))
 def test_mutable_truncated_empty_unicode_and_oversized_records_refused(self):
  for data,seals in [(b'{}',fcntl.F_SEAL_SEAL),(b'',m.SEALS),(b'\xff',m.SEALS),(b'{',m.SEALS),(b'X'*(m.LIMIT+1),m.SEALS)]:
   with self.assertRaises((m.Refusal,ValueError)):m.read_sealed_json(self.sealed(data,seals))
 def test_non_regular_descriptor_refused(self):
  r,w=os.pipe();self.addCleanup(os.close,r);self.addCleanup(os.close,w)
  with self.assertRaises(m.Refusal):m.read_sealed_json(r)

if __name__=='__main__':unittest.main()
