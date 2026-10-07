# SPDX-License-Identifier: Apache-2.0
"""Fixed staging metadata only; no system/profile/namespace/route operation."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
BASE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build_trust_projection',BASE/'workflow/build.py');build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)

def info(mode=stat.S_IFREG|0o644,uid=0,size=3):return os.stat_result((mode,0,0,1,uid,0,size,0,0,0))
class Projection(unittest.TestCase):
 def test_metadata_distinguishes_size_from_ownership_permission_and_type_without_target(self):
  for state in (info(size=build.MAX_ALIAS_BYTES+4),info(uid=12345),info(mode=stat.S_IFREG|0o666),info(mode=stat.S_IFDIR|0o755)):
   with build.trust_location('import-alias',7):error=build.TrustRefusal('python-import-alias-target-untrusted',state)
   actual=build.staging_failure(error);self.assertEqual(actual['entryOrdinal'],7);self.assertEqual(actual['entryKind'],'import-alias');metadata=actual['metadata'];self.assertEqual(metadata['rootOwned'],state.st_uid==0);self.assertEqual(metadata['groupOrOtherWritable'],bool(state.st_mode&0o022));self.assertEqual(metadata['aliasSizeWithinBound'],0<=state.st_size<=build.MAX_ALIAS_BYTES);self.assertEqual(actual['metadataSHA256'],hashlib.sha256(json.dumps(metadata,sort_keys=True,separators=(',',':')).encode()).hexdigest())
   self.assertLess(len(json.dumps(actual)),1024);self.assertEqual(str(error),'python-import-alias-target-untrusted')
 def test_actual_alias_fd_gate_preserves_refusal_and_never_reads_oversize_body(self):
  with tempfile.TemporaryDirectory()as directory:
   file=Path(directory)/'owned';file.write_bytes(b'bounded fixture');original_open=os.open
   with patch.object(build,'rooted',return_value='/usr/lib/python3.12/fixed'),patch.object(build.os,'open',side_effect=lambda *_args,**_kwargs:original_open(file,os.O_RDONLY|os.O_NOFOLLOW)),patch.object(build.os,'fstat',return_value=info(size=build.MAX_ALIAS_BYTES+1)),patch.object(build.os,'read')as read:
    with build.trust_location('import-alias',3),self.assertRaises(build.TrustRefusal)as raised:build.alias_record('/usr/lib/python3.12/fixed')
   read.assert_not_called();record=build.staging_failure(raised.exception);self.assertTrue(record['metadata']['rootOwned']);self.assertFalse(record['metadata']['groupOrOtherWritable']);self.assertFalse(record['metadata']['aliasSizeWithinBound']);self.assertEqual(record['entryOrdinal'],3)
 def test_real_canonical_writable_directory_still_refuses_and_reports_only_metadata(self):
  with self.assertRaises(build.TrustRefusal)as raised:build.rooted('/tmp')
  record=build.staging_failure(raised.exception);self.assertEqual(record['category'],'runtime-package-path-not-root-trusted');self.assertEqual(record['metadata']['fileType'],'directory');self.assertTrue(record['metadata']['groupOrOtherWritable']);self.assertNotIn('/tmp',json.dumps(record))
 def test_context_resets_on_failure_and_invalid_locations_refuse(self):
  try:
   with build.trust_location('import-root',4):raise build.TrustRefusal('runtime-package-path-not-root-trusted',info())
  except build.TrustRefusal as error:self.assertEqual(build.staging_failure(error)['entryOrdinal'],4)
  self.assertEqual(build.staging_failure(build.TrustRefusal('runtime-package-path-not-root-trusted'))['entryOrdinal'],0)
  for kind,ordinal in [('private-account',1),({},1),('import-root',True),('import-root',-1),('import-root',16385)]:
   with self.assertRaises(ValueError),build.trust_location(kind,ordinal):pass
 def test_unknown_exception_and_os_errno_never_reflect_arbitrary_fields(self):
  secret='https://secret.invalid/private?credential=value'
  self.assertEqual(build.staging_failure(ValueError(secret)),{'version':1,'category':'trusted-network-build-refused','errnoObserved':None})
  error=PermissionError(13,secret,secret);self.assertEqual(build.staging_failure(error),{'version':1,'category':'trusted-network-build-refused','errnoObserved':13})
  class Hostile(OSError):
   @property
   def errno(self):raise AssertionError('Do not inspect arbitrary exception getter')
  self.assertEqual(build.staging_failure(Hostile(secret))['errnoObserved'],None)
 def test_tampered_metadata_and_raw_extra_fields_are_never_published(self):
  for change in ('extra','mode','type','ordinal','metadata','unhashable','hostile-type'):
   error=build.TrustRefusal('python-import-alias-target-untrusted',info())
   if change=='extra':error.projection['secret']='private-value'
   if change=='mode':error.projection['metadata']['permissions']='private-value'
   if change=='type':error.projection['metadata']['fileType']='private-value'
   if change=='ordinal':error.projection['entryOrdinal']=True
   if change=='metadata':error.projection['metadata']={'rawPath':'private-value'}
   if change=='unhashable':error.projection['category']={'rawPath':'private-value'}
   if change=='hostile-type':
    class Hostile:
     def __eq__(self,_other):raise AssertionError('Do not evaluate arbitrary metadata comparisons')
    error.projection['metadata']['fileType']=Hostile()
   output=build.staging_failure(error);self.assertEqual(output['category'],'trusted-network-build-refused');self.assertNotIn('private-value',json.dumps(output))
 def test_cli_failure_is_bounded_fixed_json_not_traceback_or_argument(self):
  with tempfile.TemporaryDirectory()as directory:
   missing=Path(directory)/'private-credential-value';stage=Path(directory)/'stage';result=subprocess.run([sys.executable,str(BASE/'workflow/build.py'),'--policy',str(missing),'--stage',str(stage)],capture_output=True,text=True,timeout=5)
  self.assertEqual(result.returncode,1);self.assertEqual(result.stderr,'');self.assertLess(len(result.stdout),1024);self.assertNotIn('private-credential',result.stdout);self.assertEqual(json.loads(result.stdout),{'version':1,'category':'trusted-network-build-refused','errnoObserved':2})
 def test_original_disjunctive_admission_gates_and_runtime_source_remain_present(self):
  source=(BASE/'workflow/build.py').read_text()
  for guard in ('info.st_uid!=0 or info.st_mode&0o022','not stat.S_ISREG(before.st_mode) or before.st_uid or before.st_mode&0o022 or not 0<=before.st_size<=MAX_ALIAS_BYTES','info.st_mode&0o022 or (not stat.S_ISREG(info.st_mode) if last else not stat.S_ISDIR(info.st_mode))'):
   self.assertIn(guard,source)
 def test_original_exception_identity_args_and_traceback_show_only_fixed_metadata_note(self):
  import traceback
  with build.trust_location('import-alias',3):error=build.TrustRefusal('python-import-alias-target-untrusted',info(size=build.MAX_ALIAS_BYTES+1))
  self.assertEqual(error.args,('python-import-alias-target-untrusted',));self.assertEqual(str(error),'python-import-alias-target-untrusted')
  try:raise error
  except build.TrustRefusal as caught:
   self.assertIs(caught,error);formatted=''.join(traceback.format_exception(caught));self.assertEqual('TRUSTED_NETWORK_FAILURE:'in formatted,build._exception_add_note is not None)
  notes=vars(error).get('__notes__',[]);self.assertEqual(len(notes),1 if build._exception_add_note is not None else 0)
  if notes:self.assertEqual(json.loads(notes[0].split(':',1)[1]),build.staging_failure(error));self.assertLess(len(notes[0]),1024)
 def test_native_note_method_cannot_be_replaced_by_exception_subclass_override(self):
  class Derived(build.TrustRefusal):
   def add_note(self,_note):raise AssertionError('Do not invoke subclass methods')
  error=Derived('runtime-package-path-not-root-trusted',info())
  self.assertEqual(len(vars(error).get('__notes__',[])),1 if build._exception_add_note is not None else 0);self.assertEqual(error.args,('runtime-package-path-not-root-trusted',))
 def test_absent_python_note_api_preserves_existing_refusal_and_fixed_projection(self):
  with patch.object(build,'_exception_add_note',None):error=build.TrustRefusal('python-import-tree-untrusted',info())
  self.assertNotIn('__notes__',vars(error));self.assertEqual(str(error),'python-import-tree-untrusted');self.assertEqual(build.staging_failure(error)['category'],'python-import-tree-untrusted')
 def test_notes_never_evaluate_hostile_stat_or_project_raw_private_object(self):
  class Hostile:
   @property
   def st_mode(self):raise AssertionError('Do not inspect unknown stats')
  error=build.TrustRefusal('runtime-package-path-not-root-trusted',Hostile(),ancestor=9999)
  projection=build.staging_failure(error);self.assertIsNone(projection['metadata']);self.assertEqual(projection['ancestorOrdinal'],4096)
  notes=vars(error).get('__notes__',[]);self.assertEqual(len(notes),1 if build._exception_add_note is not None else 0)
  if notes:self.assertEqual(json.loads(notes[0].split(':',1)[1]),projection)
 def test_name_diagnostics_are_fixed_unknown_and_not_file_format_or_package_proof(self):
  cases=[('/usr/lib/x86_64-linux-gnu/libpython3.12.a','python312-static-library-name','usr-library-directory'),('/usr/lib/python3.12/config-3.12-x86_64-linux-gnu/libpython3.12.so.1.0','python312-shared-library-name','python312-config-directory'),('/etc/private-credential.data','unknown-name','other-reviewed-directory'),('/usr/lib/libpython3.13.a','unknown-name','usr-library-directory')]
  for path,name,directory in cases:
   record=build.alias_target_class(path);self.assertEqual(record,{'nameClass':name,'directoryClass':directory,'evidence':'canonical-name-only-no-byte-read'});self.assertNotIn(path,json.dumps(record));self.assertNotIn('private-credential',json.dumps(record))
 def test_actual_oversize_gate_reports_name_without_read_and_closes_original_fd(self):
  with tempfile.TemporaryDirectory()as directory:
   file=Path(directory)/'fixture';file.write_bytes(b'not a library');original_open=os.open;opened=[]
   def acquire(*_args,**_kwargs):
    fd=original_open(file,os.O_RDONLY|os.O_NOFOLLOW);opened.append(fd);return fd
   with patch.object(build,'rooted',return_value='/usr/lib/x86_64-linux-gnu/libpython3.12.a'),patch.object(build.os,'open',side_effect=acquire),patch.object(build.os,'fstat',return_value=info(size=build.MAX_ALIAS_BYTES+1)),patch.object(build.os,'read')as read:
    with build.trust_location('import-alias',3),self.assertRaises(build.TrustRefusal)as raised:build.alias_record('/usr/lib/x86_64-linux-gnu/libpython3.12.a')
   read.assert_not_called();self.assertEqual(raised.exception.args,('python-import-alias-target-untrusted',));self.assertEqual(build.staging_failure(raised.exception)['aliasTargetClass']['nameClass'],'python312-static-library-name')
   for fd in opened:
    with self.assertRaises(OSError):os.fstat(fd)
 def test_alias_name_schema_rejects_private_extra_values_and_hostile_getters(self):
  for changed in ({'nameClass':'private-path'},dict(build.alias_target_class('/usr/lib/unknown'),rawPath='/private/credential'),dict(build.alias_target_class('/usr/lib/unknown'),nameClass=[])):
   error=build.TrustRefusal('python-import-alias-target-untrusted',info());error.projection['aliasTargetClass']=changed
   self.assertEqual(build.staging_failure(error)['category'],'trusted-network-build-refused');self.assertNotIn('private',json.dumps(build.staging_failure(error)))
 def test_absent_note_api_retains_original_refusal_with_new_fixed_name_class(self):
  with patch.object(build,'_exception_add_note',None):error=build.TrustRefusal('python-import-alias-target-untrusted',info(),alias_target=build.alias_target_class('/usr/lib/libpython3.12.a'))
  self.assertNotIn('__notes__',vars(error));self.assertEqual(error.args,('python-import-alias-target-untrusted',));self.assertEqual(build.staging_failure(error)['aliasTargetClass']['nameClass'],'python312-static-library-name')
if __name__=='__main__':unittest.main()
