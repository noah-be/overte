#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
import copy,hashlib,json,os,stat,tempfile,unittest
from pathlib import Path
from stage import signed_dependency,regular,write
from curate import project,main
HERE=Path(__file__).resolve().parent
CACHE=Path(os.environ['ATOMIC_DIAGNOSTIC_CACHE'])
KEYRING=Path(os.environ.get('ATOMIC_DIAGNOSTIC_TEST_KEYRING','/usr/share/keyrings/ubuntu-archive-keyring.gpg'))
def base():return {'schemaVersion':1,'scope':'standalone-fresh-domain-provisioning-probe-not-nineteen-stage-world-lifecycle','completed':False,'phase':'preparation','endpointOwnership':'not-observed','provisioning':'not-requested'}
class SignedStage(unittest.TestCase):
 def test_real_trusted_signature_index_package_regular_executable_chain(self):
  record=json.loads((HERE/'dependency.json').read_text());mapping={record['releaseURL']:CACHE/'InRelease','https://archive.ubuntu.com/ubuntu/dists/noble/'+record['packagesPath']:CACHE/'Packages.xz',record['packageURL']:CACHE/'strace.deb'}
  with tempfile.TemporaryDirectory()as temp:
   directory=Path(temp);result=signed_dependency(directory,KEYRING,lambda url:mapping[url].read_bytes())
   self.assertEqual(result['binarySHA256'],hashlib.sha256((directory/'strace').read_bytes()).hexdigest());self.assertEqual(stat.S_IMODE((directory/'strace').stat().st_mode),0o755)
   for f in directory.iterdir():self.assertEqual(stat.S_IMODE(f.stat().st_mode),0o755 if f.name=='strace'else 0o600)
 def test_altered_signed_content_refuses_before_external_execution(self):
  with tempfile.TemporaryDirectory()as temp:
   with self.assertRaisesRegex(ValueError,'digest-refused'):signed_dependency(Path(temp),KEYRING,lambda url:b'changed')
 def test_regular_fifo_symlink_size_and_private_guards(self):
  with tempfile.TemporaryDirectory()as temp:
   root=Path(temp);os.mkfifo(root/'fifo');(root/'link').symlink_to(root/'fifo');write(root/'file',b'x')
   for name in('fifo','link'):
    with self.assertRaises((ValueError,OSError)):regular(root/name)
   with self.assertRaises(ValueError):regular(root/'file',0)
   (root/'file').chmod(0o644)
   with self.assertRaises(ValueError):regular(root/'file',private=True)
class FixedCuration(unittest.TestCase):
 def test_only_fixed_summary_survives_no_target_path_or_causality(self):
  doc=base();doc['targetSyscalls']={'scope':'exact-private-settings-destination-within-single-provisioning-window','calls':{'rename':{'success':0,'failure':1,'unclassifiedResult':0,'errno':{'EPERM':1}}},'settingsCommitCause':'not-established','captureTruncated':False,'unmatchedDestination':1,'syncDescriptorUnattributed':1,'unparsedLines':1,'oversizedLines':0,'windowExcluded':0}
  result=project(doc);self.assertEqual(result['targetSyscalls']['calls']['rename']['errno'],{'EPERM':1});self.assertEqual(result['settingsCommitCause'],'not-established');self.assertNotIn('/private',json.dumps(result))
 def test_unknown_enum_key_guest_value_or_large_counter_is_refused(self):
  for key,value in(('phase','secret'),('endpointOwnership','/private/token'),('extra','secret'),('completed',1)):
   doc=base();doc[key]=value
   with self.assertRaises(ValueError):project(doc)
  doc=base();doc['targetSyscalls']={'scope':'exact-private-settings-destination-within-single-provisioning-window','calls':{},'settingsCommitCause':'not-established','captureTruncated':False,'unmatchedDestination':2**53,'syncDescriptorUnattributed':0,'unparsedLines':0,'oversizedLines':0,'windowExcluded':0}
  with self.assertRaises(ValueError):project(doc)
 def test_unavailable_summary_writes_explicit_failure_and_returns_failure(self):
  with tempfile.TemporaryDirectory()as temp:
   prior=dict(os.environ);os.environ['RUNNER_TEMP']=temp;os.environ.pop('ATOMIC_PROBE_OUTPUT',None)
   try:self.assertEqual(main(),1);safe=json.loads((Path(temp)/'atomic-settings-safe-summary.json').read_text());self.assertFalse(safe['completed']);self.assertEqual(safe['failureCategory'],'summary-unavailable-or-unvalidated');self.assertEqual(stat.S_IMODE((Path(temp)/'atomic-settings-safe-summary.json').stat().st_mode),0o600)
   finally:os.environ.clear();os.environ.update(prior)
 def test_completed_without_original_strict_readback_is_refused(self):
  doc=base();doc['completed']=True
  with self.assertRaises(ValueError):project(doc)
if __name__=='__main__':unittest.main()
