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
if __name__=='__main__':unittest.main()
