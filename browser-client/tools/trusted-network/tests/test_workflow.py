# SPDX-License-Identifier: Apache-2.0
"""Pure staging/refusal tests; never install profiles, unshare or signal hosts."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

BASE=Path(__file__).resolve().parents[1]
def module(name):
 spec=importlib.util.spec_from_file_location(name,BASE/'workflow'/(name+'.py'))
 value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
build=module('build');installer=module('install')
POLICY={'version':1,'hostUID':1000,'hostGID':1000,'sessionParent':'/tmp',
 'nativeExecutables':['/opt/overte/interface'],'nativeReadRoots':['/opt/overte']}

class Workflow(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.work=tempfile.TemporaryDirectory(prefix='overte-trusted-stage-cpu-')
  cls.stage=Path(cls.work.name)/'stage'
  cls.manifest=build.build(cls.stage,POLICY,static_libraries=os.environ.get('OVERTE_SETUP_STATIC_LIBRARIES'))
  cls.digest=hashlib.sha256((cls.stage/'manifest.json').read_bytes()).hexdigest()
 @classmethod
 def tearDownClass(cls):cls.work.cleanup()
 def duplicate_stage(self):
  root=tempfile.TemporaryDirectory(prefix='overte-trusted-copy-cpu-');self.addCleanup(root.cleanup)
  path=Path(root.name)/'stage';path.mkdir()
  for source in self.stage.iterdir():(path/source.name).write_bytes(source.read_bytes())
  return path
 def test_actual_strict_c_build_and_complete_authenticated_bundle(self):
  manifest,data=installer.verified_bundle(self.stage,self.digest)
  self.assertEqual(set(data),installer.REQUIRED)
  self.assertEqual(manifest['activated'],False)
  self.assertEqual(manifest['actualNamespaceCapabilityRoutingProof'],False)
  self.assertEqual(data['policy.json'],(self.stage/'policy.json').read_bytes())
  for name in ('launcher','native-boundary-exec'):
   elf=subprocess.run(['/usr/bin/readelf','-lW',str(self.stage/name)],capture_output=True,check=True,timeout=2).stdout
   self.assertNotIn(b'INTERP',elf)
 def test_actual_static_sha256_primitive_matches_independent_known_vectors(self):
  with tempfile.TemporaryDirectory(prefix='overte-digest-cpu-') as d:
   root=Path(d);code=root/'digest.c';binary=root/'digest'
   code.write_text('#define main unused_setup_main\n#include '+json.dumps(str(BASE/'src/launcher.c'))+'\n#undef main\nint main(void){unsigned char bytes[4096],digest[32];size_t n=fread(bytes,1,sizeof(bytes),stdin);if(!digest_bytes(bytes,n,digest))return 1;for(int i=0;i<32;i++)printf("%02x",digest[i]);return 0;}\n')
   flags=['-static']
   if os.environ.get('OVERTE_SETUP_STATIC_LIBRARIES'):flags+=['-L'+os.environ['OVERTE_SETUP_STATIC_LIBRARIES']]
   subprocess.run(['cc',*flags,'-std=c11','-O2','-I'+str(self.stage),str(code),'-lcrypto','-o',str(binary)],capture_output=True,check=True)
   for value in (b'',b'abc',bytes(range(256)),bytes(range(256))*8):
    result=subprocess.run([binary],input=value,capture_output=True,check=True,timeout=2)
    self.assertEqual(result.stdout.decode(),hashlib.sha256(value).hexdigest());self.assertEqual(result.stderr,b'')
 def test_launcher_refuses_before_namespace_on_missing_owned_profile_or_extra_arg(self):
  before=[os.stat('/proc/self/ns/'+kind).st_ino for kind in ('user','net')]
  for args in ([],['not-a-command']):
   result=subprocess.run([self.stage/'launcher',*args],capture_output=True,timeout=2,
     env={'PATH':'/usr/bin:/bin','OVERTE_SYNTHETIC_SECRET':'never-output'})
   self.assertEqual(result.returncode,78);self.assertEqual(result.stdout,b'')
   lines=result.stderr.splitlines();self.assertEqual(len(lines),2);self.assertEqual(lines[-1],b'Trusted network setup refused.')
   self.assertTrue(lines[0].startswith(b'OVERTE_NET_TRUSTED_FAILURE='))
   diagnostic=json.loads(lines[0].removeprefix(b'OVERTE_NET_TRUSTED_FAILURE='))
   self.assertEqual(set(diagnostic),{'version','phase','errnoObserved'});self.assertEqual(diagnostic['version'],1)
   self.assertIn(diagnostic['phase'],('admission','initial-capabilities','installed-profile','initial-nnp'))
   self.assertIs(type(diagnostic['errnoObserved']),int);self.assertGreaterEqual(diagnostic['errnoObserved'],0);self.assertLessEqual(diagnostic['errnoObserved'],4095)
   if args:self.assertEqual(diagnostic,{'version':1,'phase':'admission','errnoObserved':0})
   self.assertNotIn(b'never-output',result.stderr)
  self.assertEqual(before,[os.stat('/proc/self/ns/'+kind).st_ino for kind in ('user','net')])
 def test_real_untrusted_preload_constructor_cannot_run_before_fixed_entry(self):
  with tempfile.TemporaryDirectory(prefix='overte-preload-cpu-') as d:
   root=Path(d);code=root/'constructor.c';library=root/'constructor.so';marker=root/'unexpected-constructor'
   code.write_text('#include <stdio.h>\n#include <stdlib.h>\n__attribute__((constructor)) static void attempt(void){const char *p=getenv("OVERTE_CPU_CONSTRUCTOR_MARKER");if(p){FILE *f=fopen(p,"w");if(f){fputs("unexpected",f);fclose(f);}}}\n')
   subprocess.run(['cc','-shared','-fPIC',str(code),'-o',str(library)],check=True,capture_output=True)
   for name,args in (('launcher',[]),('native-boundary-exec',['/opt/overte/interface'])):
    result=subprocess.run([self.stage/name,*args],capture_output=True,timeout=2,env={'LD_PRELOAD':str(library),'LD_LIBRARY_PATH':d,'OVERTE_CPU_CONSTRUCTOR_MARKER':str(marker)})
    self.assertEqual(result.returncode,78);self.assertFalse(marker.exists())
    self.assertNotIn(b'ld.so',result.stderr)
 def test_final_guard_refuses_without_native_boundary_and_never_executes_payload(self):
  result=subprocess.run([self.stage/'native-boundary-exec','/opt/overte/interface'],capture_output=True,timeout=2)
  self.assertEqual(result.returncode,78);self.assertEqual(result.stdout,b'')
  self.assertEqual(result.stderr,b'Native capability boundary refused.\n')
 def test_mutated_payload_and_digest_refused(self):
  path=self.duplicate_stage();(path/'launcher').write_bytes(b'not-reviewed')
  with self.assertRaisesRegex(installer.Refusal,'bundle-hash-mismatch'):installer.verified_bundle(path,self.digest)
  with self.assertRaisesRegex(installer.Refusal,'review-manifest-mismatch'):installer.verified_bundle(self.stage,'0'*64)
 def test_unreviewed_manifest_or_extra_file_refused(self):
  with self.assertRaisesRegex(installer.Refusal,'review-manifest-required'):installer.verified_bundle(self.stage,'')
  path=self.duplicate_stage();(path/'extra').write_text('unknown')
  with self.assertRaisesRegex(installer.Refusal,'bundle-extra-file'):installer.verified_bundle(path,self.digest)
 def test_bundle_final_symlink_and_alias_refused(self):
  path=self.duplicate_stage();(path/'launcher').unlink();(path/'launcher').symlink_to(self.stage/'launcher')
  with self.assertRaises(OSError):installer.verified_bundle(path,self.digest)
  with tempfile.TemporaryDirectory() as d:
   alias=Path(d)/'alias';alias.symlink_to(self.stage,target_is_directory=True)
   with self.assertRaisesRegex(installer.Refusal,'bundle-alias'):installer.verified_bundle(alias,self.digest)
 def test_snapshot_bytes_not_borrowed_from_later_mutable_stage(self):
  path=self.duplicate_stage();_,data=installer.verified_bundle(path,self.digest)
  (path/'policy.json').write_bytes(b'{}')
  self.assertEqual(data['policy.json'],(self.stage/'policy.json').read_bytes())
  for name in ('launcher','native-boundary-exec'):
   elf=subprocess.run(['/usr/bin/readelf','-lW',str(self.stage/name)],capture_output=True,check=True,timeout=2).stdout
   self.assertNotIn(b'INTERP',elf)
 def test_oversized_nonregular_and_empty_bundle_files_refused(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'file'
   for value in (b'',b'x'*17):
    path.write_bytes(value)
    with self.assertRaisesRegex(installer.Refusal,'bundle-file-bound'):installer.bounded_file(path,16)
   with self.assertRaisesRegex(installer.Refusal,'bundle-file-bound'):installer.bounded_file(Path(d),16)
 def test_loaded_profiles_exact_duplicate_unknown_and_bound(self):
  self.assertEqual(installer.parse_loaded_profiles('bwrap (enforce)\nunpriv_bwrap (enforce)\n'),{'bwrap':'enforce','unpriv_bwrap':'enforce'})
  for value in ('bwrap (enforce)\nbwrap (enforce)\n','bwrap (unknown)\n','bad-record\n','x'*(1024*1024+1)):
   with self.assertRaises(installer.Refusal):installer.parse_loaded_profiles(value)
 def test_nonroot_install_refuses_before_file_or_profile_mutation(self):
  with patch.object(installer.os,'geteuid',return_value=1000),patch.object(installer,'verified_bundle') as checked:
   with self.assertRaisesRegex(installer.Refusal,'root-required'):installer.install(self.stage,self.digest)
   checked.assert_not_called()
 def test_policy_injection_broad_root_aliases_and_boolean_headers_refused_before_build(self):
  import copy
  for key,value in [('sessionParent','/tmp/\ncapability, '),('nativeExecutables',['/bin/sh\n']),('nativeReadRoots',['/']),
                    ('nativeReadRoots',['/opt/pkg/../secret']),('version',True)]:
   policy=copy.deepcopy(POLICY);policy[key]=value
   with tempfile.TemporaryDirectory() as d:
    with self.assertRaises(ValueError):build.build(d,policy)
 def test_stage_cannot_overwrite_existing_output(self):
  with self.assertRaisesRegex(ValueError,'stage-must-be-empty'):build.build(self.stage,POLICY)
 def test_scoped_profile_has_no_workspace_or_generic_setup_exec(self):
  profile=(self.stage/'overte-browser-network').read_text()
  setup,owner=profile.split('profile overte-browser-network-owner flags=',1)
  self.assertIn('capability net_admin,',setup)
  self.assertIn('capability setpcap,',setup)
  self.assertIn(' Px -> overte-browser-network-owner,',setup)
  self.assertNotIn('/** ix',setup);self.assertNotIn('/tmp/**',setup)
  self.assertIn('audit deny capability,',owner)
  self.assertIn('/usr/bin/bwrap Px -> bwrap,',owner)
  self.assertNotIn('complain',profile)
 def test_untrusted_interpreter_root_refused(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'python3.12';path.write_text('not a package')
   with self.assertRaisesRegex(ValueError,'not-root-trusted'):build.rooted(path)
 def test_pinned_c_loader_and_original_owner_lifecycle_are_preserved(self):
  c=(BASE/'src/launcher.c').read_text();owner=(BASE/'src/trusted_owner.py').read_text()
  self.assertIn('fexecve(10,arguments,environment)',c)
  self.assertIn('overte_retire_setup_capabilities()',c)
  self.assertIn('syscall(SYS_close_range,11u,~0u,0u)',c)
  self.assertIn('reap_owned_descendants()',owner)
  self.assertIn('PR',c)
  self.assertNotIn('subprocess.run(["ip"',owner)
  self.assertNotIn('sys.path.insert',owner)

if __name__=='__main__':unittest.main()
