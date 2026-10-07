#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
import hashlib,json,os,subprocess,tempfile,unittest
from pathlib import Path
from target_projection import summarize
from probe import persistence_markers,sha
from observer import MAX_CAPTURE
HERE=Path(__file__).resolve().parent
class ExactTarget(unittest.TestCase):
 def test_known_absolute_destination_only_and_window(self):
  raw=b'123 1790890201.1 rename("secret-source", "/private/domain.json") = -1 EACCES (Permission denied)\n1790890201.2 renameat2(-100, "secret", -100, "/private/domain.json", 0) = 0\n1790890201.3 rename("source", "/other/domain.json") = -1 EPERM (Operation not permitted)\n1790890201.4 rename("source", "domain.json") = 0\n1790890199.4 rename("source", "/private/domain.json") = -1 ENOSPC (No space left on device)\n1790890201.5 fsync(234) = -1 EIO (Input/output error)\n'
  out=summarize(raw,'/private/domain.json',1790890200,1790890202)
  self.assertEqual(out['calls']['rename']['errno'],{'EACCES':1});self.assertEqual(out['calls']['renameat2']['success'],1)
  self.assertEqual(out['unmatchedDestination'],2);self.assertEqual(out['windowExcluded'],1);self.assertEqual(out['syncDescriptorUnattributed'],1)
  self.assertEqual(out['settingsCommitCause'],'not-established')
  for secret in('secret-source','/private','/other','234','123'):self.assertNotIn(secret,json.dumps(out))
 def test_literal_escaped_destination_and_recoverable_error_not_final_cause(self):
  target='/private/a"b.json';raw=('1790890201.1 linkat(-100, "/proc/self/fd/7", -100, '+json.dumps(target)+', AT_SYMLINK_FOLLOW) = -1 EEXIST (File exists)\n1790890201.2 rename("x", '+json.dumps(target)+') = 0\n').encode()
  out=summarize(raw,target,1790890200,1790890202);self.assertEqual(out['calls']['linkat']['errno'],{'EEXIST':1});self.assertEqual(out['calls']['rename']['success'],1);self.assertEqual(out['settingsCommitCause'],'not-established')
 def test_split_truncated_unknown_and_censoring_never_gain_causality(self):
  raw=b'1790890201.1 rename("secret", "/target" <unfinished ...>\n1790890201.2 <... rename resumed>) = -1 EPERM\n'+b'x'*16385+b'\n1790890201.3 rename("x", "/target") = -1 ESECRET (secret detail)\n'
  out=summarize(raw,'/target',1790890200,1790890202,capture_truncated=True)
  self.assertEqual(out['unparsedLines'],2);self.assertEqual(out['oversizedLines'],1);self.assertTrue(out['captureTruncated']);self.assertEqual(out['calls']['rename']['errno'],{'unrecognized-errno':1});self.assertNotIn('secret',json.dumps(out));self.assertEqual(out['settingsCommitCause'],'not-established')
 def test_size_and_window_bounds(self):
  for data,start,end in((b'x'*(MAX_CAPTURE+1),1,2),(b'',2,1),(b'',0,1)):
   with self.assertRaises(ValueError):summarize(data,'/target',start,end)
 def test_full_capture_marker_is_fixed_and_not_inferred_post_phase(self):
  out=persistence_markers(b'Could not commit writes to JSON settings file. Unable to persist settings.\n/private/token\n')
  self.assertEqual(out['commit-failed'],1);self.assertNotIn('/private',json.dumps(out));self.assertEqual(sum(out.values()),1)
 def test_executable_hash_accepts_original_root_owned_tool_without_mutation(self):
  native=Path('/usr/bin/unshare');self.assertEqual(sha(native,executable=True),hashlib.sha256(native.read_bytes()).hexdigest())
 def test_official_binary_and_package_provenance_are_pinned(self):
  record=json.loads((HERE/'dependency.json').read_text())
  self.assertEqual(sha(Path(os.environ.get('ATOMIC_DIAGNOSTIC_STRACE',str(HERE/'strace'))),executable=True),record['binarySHA256']);self.assertEqual(Path(os.environ.get('ATOMIC_DIAGNOSTIC_STRACE',str(HERE/'strace'))).stat().st_size,record['binaryBytes']);self.assertTrue(record['signatureValidated'])
if __name__=='__main__':unittest.main()
