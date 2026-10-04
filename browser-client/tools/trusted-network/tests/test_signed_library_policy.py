# SPDX-License-Identifier: Apache-2.0
"""Pinned typed-member policy and real static C/hash contracts; no activation."""
import ctypes,hashlib,importlib.util,json,os,re,stat,subprocess,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1]
def load(name):
 spec=importlib.util.spec_from_file_location('signed_policy_'+name,BASE/'workflow'/(name+'.py'))
 result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result
B=load('build');I=load('install');S=load('signed_library')
POLICY={'version':1,'hostUID':1000,'hostGID':1000,'sessionParent':'/tmp','nativeExecutables':['/opt/overte/interface'],'nativeReadRoots':['/opt/overte']}
def ordinary(index=0,size=0):return {'path':'/usr/share/fixed-'+str(index).zfill(3),'bytes':size,'sha256':'a'*64}

def function(source,name):
 marker='static int '+name+'(int fd,const char *resolved) {';start=source.index(marker);offset=start+len(marker);depth=1
 while depth:
  depth+=(source[offset]=='{')-(source[offset]=='}');offset+=1
 return source[start:offset]

class TypedPolicy(unittest.TestCase):
 def test_exact_pin_only_no_asserted_signature_boolean_or_basename_permission(self):
  self.assertEqual(S.validate_library(S.PIN),S.PIN)
  for key,value in [('canonicalPath','/usr/lib/other/libpython3.12.so.1.0'),('packageVersion','3.12.3-1ubuntu0.18'),('memberBytes',True),('memberSHA256','0'*64),('interpreterMemberSHA256','0'*64)]:
   with self.subTest(key=key),self.assertRaises(ValueError):S.validate_library(dict(S.PIN,**{key:value}))
  with self.assertRaises(ValueError):S.validate_library(dict(S.PIN,signatureVerified=True))
 def test_original_general_4mib_stays_and_typed_debits_original_unique_count_bytes_and_metadata(self):
  self.assertEqual(S.validate_mixed_budget([ordinary(size=4194304)],S.PIN),4194304+S.PIN['memberBytes'])
  for items in ([ordinary(size=4194305)],[ordinary(0,4194304),ordinary(1,4194304)],[ordinary(i)for i in range(64)],[ordinary()|{'path':S.PIN['canonicalPath']}],[{'path':'/usr/lib/'+chr(97+i)+'/'+'x'*3900,'bytes':0,'sha256':'a'*64}for i in range(4)]):
   with self.assertRaises(ValueError):S.validate_mixed_budget(items,S.PIN)
 def test_default_header_and_runtime_have_no_new_configuration_provider_or_route_path(self):
  self.assertEqual(S.header(None),'#define PYTHON_SIGNED_LIBRARY_COUNT 0\n')
  source=(BASE/'src/launcher.c').read_text();typed=function(source,'verify_signed_library_target')
  self.assertNotIn('EVP_',typed);self.assertNotIn('dlopen',typed);self.assertNotIn('getenv',typed);self.assertIn('SHA256_Init(&hash)',typed)
  self.assertIn('unsigned char bytes[65536]',typed)
 def test_missing_input_pair_or_failed_signature_never_reaches_interpreter_or_import_probe(self):
  for pair in [('cache',None),(None,'keyring')]:
   with patch.object(B,'trusted_import_paths')as probe,self.assertRaises(ValueError):B.signed_library_context('/usr/bin/python3.12',*pair)
   probe.assert_not_called()
  with patch.object(S,'authenticate_cache',side_effect=ValueError('signature-refused')),patch.object(S,'installed_member')as installed:
   with self.assertRaises(ValueError):S.context('cache','keyring','/usr/bin/python3.12')
   installed.assert_not_called()
 def test_wrong_interpreter_context_refuses_before_any_installed_read(self):
  with patch.object(S,'authenticate_cache',return_value=S.PIN),patch.object(S,'installed_member')as installed:
   with self.assertRaises(ValueError):S.context('cache','keyring','/usr/bin/python3.14')
   installed.assert_not_called()
 def test_changed_package_buffer_refuses_before_decoder(self):
  with patch.object(S,'bounded_decode')as decoder:
   with self.assertRaises(ValueError):S.verify_member(b'wrong')
   decoder.assert_not_called()
 def test_bounded_decoder_actual_small_content_and_actual_oversize_refusal(self):
  for size in (0,1000):
   compressed=subprocess.run(['/usr/bin/zstd','-q','-c'],input=b'x'*size,capture_output=True,check=True).stdout
   self.assertEqual(S.bounded_decode(compressed),b'x'*size)
  compressed=subprocess.run(['/usr/bin/zstd','-q','-c'],input=b'x'*33554433,capture_output=True,check=True).stdout
  with self.assertRaisesRegex(ValueError,'data-bound'):S.bounded_decode(compressed)

class Bundle(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.work=tempfile.TemporaryDirectory(prefix='signed-library-bundle-cpu-');cls.stage=Path(cls.work.name)/'stage'
  def inventory(python,*,aliases,signed_library,signed_libraries):
   assert python==S.PIN['interpreterCanonicalPath']and signed_library==S.PIN
   signed_libraries.append(dict(S.PIN));return ['/usr/lib/python3.12']
  # Controlled installed/signature boundary ONLY; the actual production header,
  # static compiler, manifest/bundle/schema and C implementation run unchanged.
  with patch.object(B,'rooted',return_value=S.PIN['interpreterCanonicalPath']),patch.object(B,'signed_library_context',return_value=S.PIN),patch.object(B,'trusted_import_paths',side_effect=inventory):
   cls.manifest=B.build(cls.stage,POLICY,static_libraries=os.environ.get('OVERTE_SETUP_STATIC_LIBRARIES'),signed_library_cache='authored-cache',signed_library_keyring='authored-keyring')
 @classmethod
 def tearDownClass(cls):cls.work.cleanup()
 def digest(self,path):return hashlib.sha256((path/'manifest.json').read_bytes()).hexdigest()
 def changed(self,edit,header=None):
  import shutil
  temporary=tempfile.TemporaryDirectory(prefix='signed-library-mutated-bundle-');self.addCleanup(temporary.cleanup);stage=Path(temporary.name)/'stage';shutil.copytree(self.stage,stage)
  manifest=json.loads((stage/'manifest.json').read_bytes());edit(manifest)
  if header is not None:
   (stage/'image.h').write_text(header);manifest['files']['image.h']=hashlib.sha256((stage/'image.h').read_bytes()).hexdigest()
  (stage/'manifest.json').write_text(json.dumps(manifest));return stage
 def test_actual_static_c_and_v3_bundle_no_additional_files_or_profile_grants(self):
  manifest,data=I.verified_bundle(self.stage,self.digest(self.stage));self.assertEqual(manifest['version'],3);self.assertEqual(manifest['pythonSignedLibraries'],[S.PIN]);self.assertEqual(set(data),I.REQUIRED)
  self.assertFalse(manifest['activated']);self.assertFalse(manifest['actualNamespaceCapabilityRoutingProof'])
  self.assertIn(S.header(S.PIN),data['image.h'].decode());self.assertEqual(data['overte-browser-network'].count(b'/usr/lib/** r,'),1)
  for name in ('launcher','native-boundary-exec'):
   result=subprocess.run(['/usr/bin/readelf','-lW',self.stage/name],capture_output=True,check=True).stdout;self.assertNotIn(b'INTERP',result)
 def test_v2_cannot_smuggle_typed_field_or_v3_missing_and_extra_records(self):
  for edit in (lambda m:m.update(version=2),lambda m:m.pop('pythonSignedLibraries'),lambda m:m.update(pythonSignedLibraries=[]),lambda m:m.update(pythonSignedLibraries=[S.PIN,S.PIN]),lambda m:m['pythonSignedLibraries'][0].update(memberSHA256='0'*64),lambda m:m.update(python='/usr/bin/python3.14')):
   stage=self.changed(edit)
   with self.assertRaises(ValueError):I.verified_bundle(stage,self.digest(stage))
 def test_even_new_review_digest_cannot_mismatch_missing_duplicate_or_wrong_signed_header(self):
  old=(self.stage/'image.h').read_text()
  for header in (old.replace(S.header(S.PIN),''),old+S.header(S.PIN),old.replace(str(S.PIN['memberBytes']),'9061001')):
   stage=self.changed(lambda _m:None,header)
   with self.assertRaisesRegex(ValueError,'signed-header'):I.verified_bundle(stage,self.digest(stage))
 def test_installer_must_reauthenticate_and_reinventory_not_accept_manifest_boolean(self):
  manifest=self.manifest
  with patch.object(I,'trusted_directory')as writes:
   with self.assertRaisesRegex(ValueError,'reauthentication'):I.verify_python_imports(manifest)
   writes.assert_not_called()
  calls=[]
  def context(python,cache,keyring):calls.append(('signed-and-installed',python,cache,keyring));return S.PIN
  def inventory(python,*,aliases,signed_library,signed_libraries):calls.append(('new-inventory',python));signed_libraries.append(dict(S.PIN));return manifest['pythonImportPaths']
  fake=SimpleNamespace(signed_library_context=context,trusted_import_paths=inventory)
  spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda _m:None))
  with patch('importlib.util.spec_from_file_location',return_value=spec),patch('importlib.util.module_from_spec',return_value=fake):I.verify_python_imports(manifest,'cache','keyring')
  self.assertEqual(calls,[('signed-and-installed',manifest['python'],'cache','keyring'),('new-inventory',manifest['python'])])

class CPrimitive(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.work=tempfile.TemporaryDirectory(prefix='signed-library-actual-c-');cls.root=Path(cls.work.name)
  # Authored whole content; expected C header is fixture-owned only. Package
  # authentication separately fixes the real production header to reviewed PIN.
  cls.file=cls.root/'member';cls.file.write_bytes(b'authored'*(S.PIN['memberBytes']//8)+b'authored'[:S.PIN['memberBytes']%8]);cls.file.chmod(0o600)
  content_hash=hashlib.sha256(cls.file.read_bytes()).digest();source=(BASE/'src/launcher.c').read_text()
  signed=function(source,'verify_signed_library_target');general=function(source,'verify_import_alias_target')
  prelude='''#define _GNU_SOURCE
#include <sys/stat.h>
#include <stdint.h>
#include <unistd.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>
#include <openssl/sha.h>
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
#define PYTHON_SIGNED_LIBRARY_COUNT 1
static unsigned import_alias_reads,actual_reads;
static uint64_t import_alias_read_bytes;
static int owned_fd=-1,mutation=0,stat_calls=0;
static int checked_fstat(int fd,struct stat*out){int result=fstat(fd,out);if(!result&&fd==owned_fd){out->st_uid=0;if(mutation&&++stat_calls>1)out->st_mtim.tv_nsec^=1;}return result;}
static ssize_t checked_pread(int fd,void*buffer,size_t count,off_t offset){actual_reads++;return pread(fd,buffer,count,offset);}
#define fstat checked_fstat
#define pread checked_pread
static int digest_bytes(const void*data,size_t size,unsigned char out[32]){return SHA256(data,size,out)!=NULL;}
'''
  # Header helper MUST refuse the authored record; C fixture must declare its
  # known content explicitly rather than pretend it is a signed production record.
  prelude+=S.header(S.PIN).replace('{'+','.join(str(v)for v in bytes.fromhex(S.PIN['memberSHA256']))+'}','{'+','.join(str(v)for v in content_hash)+'}')
  prelude+='#define PYTHON_PATH '+json.dumps(S.PIN['interpreterCanonicalPath'])+'\nstatic const unsigned char PYTHON_HASH[32]={'+','.join(str(v)for v in bytes.fromhex(S.PIN['interpreterMemberSHA256']))+'};\n'
  prelude+='#define PYTHON_IMPORT_ALIAS_COUNT 1\nstatic const char *PYTHON_IMPORT_ALIAS_PATHS[1]={"/usr/share/general"};\nstatic const unsigned PYTHON_IMPORT_ALIAS_BYTES[1]={9061000};\nstatic const unsigned char PYTHON_IMPORT_ALIAS_HASHES[1][32]={{0}};\n'
  api='''
void reset(unsigned reads,uint64_t bytes){import_alias_reads=reads;import_alias_read_bytes=bytes;actual_reads=0;mutation=0;stat_calls=0;}
void mutate(void){mutation=1;}
unsigned reads(void){return actual_reads;}
uint64_t bytes(void){return import_alias_read_bytes;}
int verify(int fd,const char*path,int owner){owned_fd=owner?fd:-1;int result=verify_import_alias_target(fd,path);owned_fd=-1;return result;}
'''
  cls.code=prelude+signed+'\n'+general+api;path=cls.root/'api.c';path.write_text(cls.code)
  subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O2','-shared','-fPIC',path,'-lcrypto','-o',cls.root/'api.so'],capture_output=True,check=True)
  cls.api=ctypes.CDLL(str(cls.root/'api.so'));cls.api.verify.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int];cls.api.reset.argtypes=[ctypes.c_uint,ctypes.c_uint64];cls.api.bytes.restype=ctypes.c_uint64
 @classmethod
 def tearDownClass(cls):cls.work.cleanup()
 def setUp(self):self.api.reset(0,0)
 def check(self,path=None,owner=1,file=None):
  fd=os.open(file or self.file,os.O_RDONLY|os.O_NOFOLLOW)
  try:return self.api.verify(fd,(path or S.PIN['canonicalPath']).encode(),owner)
  finally:os.close(fd)
 def test_real_whole9mib_stream_digest_and_original_shared_read_budget(self):
  self.assertEqual(self.check(),0);self.assertEqual(self.api.bytes(),S.PIN['memberBytes']);self.assertEqual(self.api.reads(),(S.PIN['memberBytes']+65535)//65536+1)
  self.api.reset(127,0);self.assertEqual(self.check(),0);self.assertEqual(self.check(),-1)
  self.api.reset(0,33554432-S.PIN['memberBytes']+1);self.assertEqual(self.check(),-1);self.assertEqual(self.api.reads(),0)
 def test_general_oversize_stays_refused_even_with_forged_matching_record_size(self):
  self.assertEqual(self.check('/usr/share/general'),-1);self.assertEqual(self.api.reads(),0)
 def test_owner_writable_and_wrong_canonical_refuse_before_bytes(self):
  self.assertEqual(self.check(owner=0),-1);self.assertEqual(self.api.reads(),0)
  self.api.reset(0,0);self.assertEqual(self.check('/usr/lib/other/libpython3.12.so.1.0'),-1);self.assertEqual(self.api.reads(),0)
  self.file.chmod(0o777)
  try:self.api.reset(0,0);self.assertEqual(self.check(),-1);self.assertEqual(self.api.reads(),0)
  finally:self.file.chmod(0o600)
 def test_same_size_changed_bytes_and_post_read_identity_refuse(self):
  target=self.root/'changed';target.write_bytes(self.file.read_bytes());target.chmod(0o600)
  with target.open('r+b')as stream:stream.seek(2000);stream.write(b'bad')
  self.assertEqual(self.check(file=target),-1);self.assertGreater(self.api.reads(),0)
  self.api.reset(0,0);self.api.mutate();self.assertEqual(self.check(),-1)
 def test_changed_interpreter_context_cannot_use_typed_route(self):
  for label,code in [('path',self.code.replace('#define PYTHON_PATH "/usr/bin/python3.12"','#define PYTHON_PATH "/usr/bin/other"')),('hash',re.sub(r'static const unsigned char PYTHON_HASH\[32\]=\{[^}]+\};','static const unsigned char PYTHON_HASH[32]={0};',self.code))]:
   path=self.root/(label+'.c');path.write_text(code);lib=self.root/(label+'.so')
   subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-shared','-fPIC',path,'-lcrypto','-o',lib],check=True,capture_output=True)
   loaded=ctypes.CDLL(str(lib));loaded.verify.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_int];fd=os.open(self.file,os.O_RDONLY)
   try:self.assertEqual(loaded.verify(fd,S.PIN['canonicalPath'].encode(),1),-1);self.assertEqual(loaded.reads(),0)
   finally:os.close(fd)

if __name__=='__main__':unittest.main()
