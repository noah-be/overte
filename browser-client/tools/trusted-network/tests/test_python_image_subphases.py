# SPDX-License-Identifier: Apache-2.0
"""Pure exact-source dispatch/operation preservation; no namespace or profile runs."""
import ctypes,json,pathlib,re,subprocess,tempfile,unittest
HERE=pathlib.Path(__file__).parent
ROOT=HERE.parent/'src'/'launcher.c'
BEFORE=HERE/'fixtures'/'python-image-before.c.txt'
class PythonImage(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  source=ROOT.read_text();cls.source=source;cls.work=tempfile.TemporaryDirectory(prefix='overte-python-phase-cpu-');d=pathlib.Path(cls.work.name)
  phases=source[source.index('enum setup_phase {'):source.index('static volatile sig_atomic_t')]
  start=source.index(' PHASE(SETUP_PYTHON_OPEN);');end=source.index(' // Relocate above',start);branch=source[start:end]
  code='''#include <stddef.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
'''+phases+'''
static int failing,calls;
static int rootfile(const char *ignored){(void)ignored;calls=calls*10+1;if(failing==1){errno=EACCES;return -1;}return 33;}
static int binary_hash(int fd,const unsigned char *ignored){(void)ignored;if(fd!=33)return -1;calls=calls*10+2;if(failing==2){errno=EACCES;return -1;}return 0;}
static int verify_import_roots(enum setup_phase *ignored){(void)ignored;calls=calls*10+3;if(failing==3){errno=EACCES;return -1;}return 0;}
#define PYTHON_PATH "/fixed-immutable-distro-image"
static const unsigned char PYTHON_HASH[32]={0};
#define PHASE(value) do{failure_phase=(value);errno=0;}while(0)
#define FAIL_IF(condition) do{if(condition){failure_errno=errno;goto fail;}}while(0)
int dispatch(int failure,char *output,size_t capacity){
 failing=failure;calls=0;enum setup_phase failure_phase=SETUP_ADMISSION;int failure_errno=0;
'''+branch+'''
 (void)python;return calls;
 fail: setup_failure_json(failure_phase,failure_errno,output,capacity);return -calls;
}
'''
  (d/'test.c').write_text(code);subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-O2','-shared','-fPIC',str(d/'test.c'),'-o',str(d/'api.so')],check=True,capture_output=True)
  cls.api=ctypes.CDLL(str(d/'api.so'));cls.api.dispatch.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_size_t];cls.api.dispatch.restype=ctypes.c_int
 @classmethod
 def tearDownClass(cls):cls.work.cleanup()
 def test_each_exact_production_branch_refuses_without_calling_later_operations(self):
  for failure,calls,phase in [(1,-1,'python-image-open'),(2,-12,'python-image-hash'),(3,-123,'python-import-roots')]:
   output=ctypes.create_string_buffer(192);self.assertEqual(self.api.dispatch(failure,output,192),calls);self.assertEqual(json.loads(output.value),{'version':1,'phase':phase,'errnoObserved':13})
 def test_positive_production_branch_retains_original_open_hash_import_order(self):
  output=ctypes.create_string_buffer(b'unchanged',192);self.assertEqual(self.api.dispatch(0,output,192),123);self.assertEqual(output.value,b'unchanged')
 def test_helpers_preserve_every_original_syscall_gate_and_argument_after_removing_fixed_diagnostic_progress(self):
  before=BEFORE.read_text();after=self.source
  def region(value):return value[value.index('static int import_tree('):value.index('// Deliberately use OpenSSL')]
  original=region(before);candidate=region(after)
  candidate=re.sub(r'\s*inspection_phase\(phase,SETUP_PYTHON_[A-Z_]+\);','',candidate)
  candidate=candidate.replace('inspection_phase(phase,SETUP_PYTHON_IMPORT_SCAN),','')
  candidate=candidate.replace(',enum setup_phase *phase','').replace('verify_import_roots(enum setup_phase *phase)','verify_import_roots(void)')
  # Version2 adds only these strengthening alias hash/budget gates. Strip
  # their exact reviewed spelling while comparing EVERY original syscall gate.
  candidate=candidate.replace('import_alias_reads=0;import_alias_read_bytes=0;','')
  candidate=candidate.replace('int checked=verify_import_alias_target(target,resolved);int saved=errno;close(target);errno=saved;if(checked)goto done;continue;','close(target);continue;')
  self.assertIn('int checked=verify_import_alias_target(target,resolved);int saved=errno;close(target);errno=saved;if(checked)goto done;continue;',self.source)
  candidate=candidate.replace('import_tree(next,entries,depth+1,phase)','import_tree(next,entries,depth+1)').replace('import_tree(fd,&entries,0,phase)','import_tree(fd,&entries,0)')
  candidate=candidate.replace('if(length<1||length>=(int)sizeof(name))goto done;if(!realpath(name,resolved))goto done;','if(length<1||length>=(int)sizeof(name)||!realpath(name,resolved))goto done;')
  self.assertEqual(re.sub(r'\s+','',candidate),re.sub(r'\s+','',original))
 def test_scan_alias_resolve_and_alias_target_are_distinct_fixed_progress_not_dynamic_path_labels(self):
  tree=self.source[self.source.index('static int import_tree('):self.source.index('static int verify_import_roots(')]
  self.assertIn('inspection_phase(phase,SETUP_PYTHON_ALIAS_RESOLVE);if(!realpath(name,resolved))goto done;',tree)
  self.assertIn('inspection_phase(phase,SETUP_PYTHON_ALIAS_TARGET);int target=rootfile(resolved);',tree)
  self.assertIn('while((inspection_phase(phase,SETUP_PYTHON_IMPORT_SCAN),errno=0,(entry=readdir(directory))))',tree)
  helper=self.source.split('static void inspection_phase(',1)[1].split('static int import_tree(',1)[0]
  self.assertEqual(re.sub(r'\s+','',helper),'enumsetup_phase*phase,enumsetup_phasenext){*phase=next;errno=0;}')
 def test_profile_route_capability_exec_and_ownership_helpers_are_byte_unchanged(self):
  before=BEFORE.read_text()
  for start,end in [('static int rootnode(','// Isolated Python'),('// Deliberately use OpenSSL','static int initially_unprivileged('),('static int initially_unprivileged(','static const char bootstrap[]='),(' // Relocate above',' #undef ROUTE_FAIL_IF')]:
   self.assertEqual(self.source[self.source.index(start):self.source.index(end,self.source.index(start))],before[before.index(start):before.index(end,before.index(start))])
if __name__=='__main__':unittest.main()
