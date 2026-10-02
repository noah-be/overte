# SPDX-License-Identifier: Apache-2.0
"""Compile/run pure formatter only: no profile, namespace, socket, caps or host signals."""
import ctypes,json,pathlib,subprocess,tempfile,unittest
HERE=pathlib.Path(__file__).parent
PHASES=('admission','initial-capabilities','installed-profile','initial-nnp','environment','signal-handlers','configuration','owner-modules','policy','python-image','handoff-relocate','user-namespace','groups-deny','uid-map','gid-map','network-namespace','lifetime','tap-ready','route-socket','route-bind','route-ack-option','route-install-ack','route-readback','attestation','attestation-relocate','retire-capabilities','post-retirement-lifetime','handoff-descriptors','close-inherited','exec-python')
class FixedFailure(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.work=tempfile.TemporaryDirectory(prefix='overte-fixed-failure-cpu-');root=pathlib.Path(cls.work.name)
  (root/'image.h').write_text('#define PYTHON_PATH "/usr/bin/python3"\n#define PYTHON_IMPORT_COUNT 1\nstatic const char *PYTHON_IMPORT_PATHS[]={"/usr/lib"};\n#define POLICY_PATH "/fixed"\nstatic const char *OWNER_PATHS[]={"/fixed","/fixed","/fixed","/fixed"};\nstatic const unsigned char OWNER_HASHES[4][32]={{0}};\nstatic const unsigned char POLICY_HASH[32]={0},PYTHON_HASH[32]={0};\n')
  (root/'test.c').write_text('#define main unused_setup_main\n#include '+json.dumps(str(HERE.parent/'src/launcher.c'))+'\n#undef main\nsize_t pure_diagnostic(int phase,int error,char *output,size_t capacity){return setup_failure_json((enum setup_phase)phase,error,output,capacity);}\n')
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O2','-fPIC','-shared','-I'+str(root),str(root/'test.c'),'-lcrypto','-o',str(root/'contract.so')],capture_output=True,check=True)
  cls.api=ctypes.CDLL(str(root/'contract.so'));cls.api.pure_diagnostic.argtypes=[ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_size_t];cls.api.pure_diagnostic.restype=ctypes.c_size_t
 @classmethod
 def tearDownClass(cls):cls.work.cleanup()
 def record(self,phase,error,capacity=192):
  output=ctypes.create_string_buffer(b'X'*192,193);size=self.api.pure_diagnostic(phase,error,output,capacity);return size,output
 def test_all_exact_fixed_labels_and_independent_json_wire_oracle(self):
  for index,phase in enumerate(PHASES):
   size,out=self.record(index,1);expected='{"version":1,"phase":"'+phase+'","errnoObserved":1}';self.assertEqual(out.raw[:size],expected.encode());self.assertEqual(out.raw[size],0);self.assertEqual(json.loads(out.raw[:size]),{'version':1,'phase':phase,'errnoObserved':1})
 def test_real_linux_errno_range_and_invalid_values_are_numeric_only(self):
  for errno in (0,1,2,12,13,17,22,110,4095):
   size,out=self.record(21,errno);self.assertEqual(json.loads(out.raw[:size])['errnoObserved'],errno)
  for errno in (-1,4096,2**31-1,-2**31):
   size,out=self.record(21,errno);self.assertEqual(json.loads(out.raw[:size])['errnoObserved'],0)
 def test_capacity_refusal_and_invalid_phase_are_atomic(self):
  for phase in (-1,len(PHASES),2**31-1):
   size,out=self.record(phase,1);self.assertEqual(size,0);self.assertEqual(out.raw[:192],b'X'*192)
  valid,_=self.record(29,1)
  for limit in (0,1,valid-1,valid):
   size,out=self.record(29,1,limit);self.assertEqual(size,0);self.assertEqual(out.raw[:192],b'X'*192)
  self.assertEqual(self.api.pure_diagnostic(0,1,None,192),0)
  size,out=self.record(29,1,valid+1);self.assertEqual(size,valid)
 def test_privacy_and_no_runtime_or_user_provided_label_input(self):
  for phase in range(len(PHASES)):
   size,out=self.record(phase,4095);value=json.loads(out.raw[:size]);self.assertEqual(set(value),{'version','phase','errnoObserved'});self.assertLess(size,192);self.assertNotIn('/',value['phase']);self.assertNotIn(':',value['phase'])
  source=(HERE.parent/'src/launcher.c').read_text();formatter=source.split('static size_t setup_failure_json(',1)[1].split('static volatile sig_atomic_t',1)[0];self.assertNotIn('strerror',formatter);self.assertNotIn('getenv',formatter);self.assertNotIn('read(',formatter);self.assertNotIn('getpid',formatter)
 def test_original_twelve_routes_ack_peer_lifetime_and_capability_gates_remain_present(self):
  source=(HERE.parent/'src/launcher.c').read_text()
  for token in ['route<12','seen==0xfff','peer.nl_pid!=0','MSG_TRUNC','F_SEAL_SEAL|F_SEAL_SHRINK|F_SEAL_GROW|F_SEAL_WRITE','PR_SET_PDEATHSIG','PR_SET_CHILD_SUBREAPER','overte_retire_setup_capabilities()','getppid()!=parent','stopped','fexecve(10,arguments,environment)','milliseconds()+10000']:
   self.assertIn(token,source)
  owner=source.split('int main(int argc,char **argv){',1)[1];self.assertLess(owner.index('SETUP_INSTALLED_PROFILE'),owner.index('unshare(CLONE_NEWUSER)'));self.assertLess(owner.index('routes_readback(route,deadline)'),owner.index('overte_retire_setup_capabilities()'));self.assertLess(owner.index('overte_retire_setup_capabilities()'),owner.index('fexecve(10,arguments,environment)'))
if __name__=='__main__':unittest.main()
