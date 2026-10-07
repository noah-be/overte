# SPDX-License-Identifier: Apache-2.0
"""Actual current dependency bytes, old-pin counterfactual and refusal controls."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import probe

HERE=Path(__file__).resolve().parent
SOURCE=HERE.parent
NAMES=('manage.py','native_admin.py','guest_permissions.py','provisioning_diagnostics.py','host_tools.py','chrome_browser.py','native_launch.py')

DIAGNOSTIC_ANCHORS=(('', "FIXED_FAILURES=frozenset(('probe-path-not-canonical','fresh-probe-directory-required',\n 'probe-directory-not-private-owned','probe-reviewed-source-changed',\n 'fresh-probe-registry-required','fresh-probe-config-required','fresh-probe-admin-required',\n 'original-initialization-boundary-changed','probe-runtime-directory-refused',\n 'reviewed-packaged-native-input-changed','probe-output-refused','owned-endpoint-not-confirmed',\n 'input-path-not-canonical','input-not-owned-regular','input-not-private',\n 'input-size-or-executable-invalid','input-size-invalid','launch-schema-invalid',\n 'launch-path-invalid','launch-executable-hash-mismatch','launch-executable-kind-invalid',\n 'launch-environment-invalid','launch-environment-code-override','launch-inherited-home-changed'))\n\ndef failure_observation(error):\n # Fixed source-owned exception tags only; no exception prose or paths escape.\n category='unclassified'\n if type(error)is ValueError and len(error.args)==1 and type(error.args[0])is str and error.args[0]in FIXED_FAILURES:\n  category=error.args[0]\n return {'scope':'owned-probe-failure-observation-not-causality','refusal':category}\n"), (" except (OSError,ValueError,RuntimeError,subprocess.SubprocessError,KeyError,TypeError,UnicodeError) as error:\n  out['failureCategory']='fixed-probe-refusal' if isinstance(error,ValueError) else 'owned-process-or-source-readback-refused'\n  raise\n finally:\n  if process is not None:\n   if process.poll()is None:process.send_signal(signal.SIGTERM)\n   try:process.wait(timeout=2.5)\n   except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)\n   out['observerStopped']=process.poll()is not None\n   out['completed']=out['completed']and out['observerStopped']\n   try:\n    trace_summary=json.loads(checked_regular(Path(output)/'summary.json',65536,private=True));out['observer']=trace_summary\n    native_data=checked_regular(Path(output)/'native-output.private.log',MAX_CAPTURE,private=True)\n    out['fullCapturePersistenceMarkers']=persistence_markers(native_data)\n    out['persistenceLogWindowLimit']='includes-startup-and-post; pipe-drain-can-lag-post-return'\n    if trace_summary['nativeOutputTruncated'] or any(out['fullCapturePersistenceMarkers'].values()):out['completed']=False\n    if 'start'in locals()and 'end'in locals()and end>=start:\n     data=checked_regular(Path(output)/'atomic-syscalls.private.log',MAX_CAPTURE,private=True)\n     out['targetSyscalls']=summarize(data,doc['settings'],start,end,capture_truncated=trace_summary['trace']['truncated'])\n     out['nativeCommitFailureCorrelatedWithExactDestinationFailure']=out['provisioning'].get('persistence',{}).get('outcome')=='commit-failed'and any(row['failure']for row in out['targetSyscalls']['calls'].values())\n     # This is correlation; an intermediate recoverable link/rename failure is\n     # not automatically the terminal Qt commit cause.\n   except (OSError,ValueError,KeyError):out['observerSummary']='unavailable-or-unclassified'\n  if safe_output:exclusive(Path(output)/'probe-summary.json',(json.dumps(out,indent=2)+'\\n').encode())\n return out\n\ndef main():\n p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo-root',required=True);p.add_argument('--lab-root',required=True);p.add_argument('--private-output',required=True);a=p.parse_args()\n try:r=run(a.repo_root,a.lab_root,a.private_output)\n except (OSError,ValueError,RuntimeError,subprocess.SubprocessError,KeyError,TypeError,UnicodeError):print('standalone-owned-probe-refused',file=sys.stderr);return 1", " except (OSError,ValueError,RuntimeError,subprocess.SubprocessError,KeyError,TypeError,UnicodeError) as error:\n  out['failureCategory']='fixed-probe-refusal' if isinstance(error,ValueError) else 'owned-process-or-source-readback-refused'\n  raise\n finally:\n  if process is not None:\n   if process.poll()is None:process.send_signal(signal.SIGTERM)\n   try:process.wait(timeout=2.5)\n   except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)\n   out['observerStopped']=process.poll()is not None\n   out['completed']=out['completed']and out['observerStopped']\n   try:\n    trace_summary=json.loads(checked_regular(Path(output)/'summary.json',65536,private=True));out['observer']=trace_summary\n    native_data=checked_regular(Path(output)/'native-output.private.log',MAX_CAPTURE,private=True)\n    out['fullCapturePersistenceMarkers']=persistence_markers(native_data)\n    out['persistenceLogWindowLimit']='includes-startup-and-post; pipe-drain-can-lag-post-return'\n    if trace_summary['nativeOutputTruncated'] or any(out['fullCapturePersistenceMarkers'].values()):out['completed']=False\n    if 'start'in locals()and 'end'in locals()and end>=start:\n     data=checked_regular(Path(output)/'atomic-syscalls.private.log',MAX_CAPTURE,private=True)\n     out['targetSyscalls']=summarize(data,doc['settings'],start,end,capture_truncated=trace_summary['trace']['truncated'])\n     out['nativeCommitFailureCorrelatedWithExactDestinationFailure']=out['provisioning'].get('persistence',{}).get('outcome')=='commit-failed'and any(row['failure']for row in out['targetSyscalls']['calls'].values())\n     # This is correlation; an intermediate recoverable link/rename failure is\n     # not automatically the terminal Qt commit cause.\n   except (OSError,ValueError,KeyError):out['observerSummary']='unavailable-or-unclassified'\n  if safe_output:exclusive(Path(output)/'probe-summary.json',(json.dumps(out,indent=2)+'\\n').encode())\n return out\n\ndef main():\n p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo-root',required=True);p.add_argument('--lab-root',required=True);p.add_argument('--private-output',required=True);a=p.parse_args()\n try:r=run(a.repo_root,a.lab_root,a.private_output)\n except (OSError,ValueError,RuntimeError,subprocess.SubprocessError,KeyError,TypeError,UnicodeError) as error:\n  print('ATOMIC_PROBE_FAILURE:'+json.dumps(failure_observation(error),sort_keys=True,separators=(',',':')),file=sys.stderr)\n  print('standalone-owned-probe-refused',file=sys.stderr);return 1"))

# Exact four reviewed17e9 observation hunks reverse to the current six-source probe.
ENVIRONMENT_ANCHORS=(('from observer import checked_regular,validated_launch,MAX_CAPTURE,child_death_guard\n', 'from observer import checked_regular,validated_launch,MAX_CAPTURE,MAX_ENV_ENTRIES,child_death_guard\n'), (" 'launch-environment-invalid','launch-environment-code-override','launch-inherited-home-changed'))\n", " 'launch-environment-invalid','launch-environment-code-override','launch-inherited-home-changed',\n 'launch-record-size-invalid'))\n"), ('', "def environment_shape(environment):\n # Observe existing schema bounds without publishing a variable name or value.\n if type(environment)is not dict:raise ValueError('launch-environment-invalid')\n strings=all(type(key)is str and type(value)is str for key,value in environment.items())\n return {'scope':'owned-native-environment-schema-observation','entries':len(environment),\n  'entryBoundExceeded':len(environment)>MAX_ENV_ENTRIES,'typesValid':strings,\n  'keyBoundExceeded':any(type(key)is str and (not key or len(key)>128)for key in environment),\n  'valueBoundExceeded':any(type(value)is str and len(value)>8192 for value in environment.values()),\n  'nulObserved':any(type(key)is str and type(value)is str and '\\0'in key+value for key,value in environment.items())}\n\n"), (' validated_launch(document)\n', " try:validated_launch(document)\n except ValueError as error:\n  if type(error)is ValueError and error.args==('launch-environment-invalid',):\n   print('ATOMIC_PROBE_ENVIRONMENT:'+json.dumps(environment_shape(env),sort_keys=True,separators=(',',':')),file=sys.stderr)\n  raise\n"))

def recover_managed_source(source):
 # CPU history only: exact declared seven->six full-text reversal; no runtime fallback.
 spec=json.loads((HERE/'fixtures/managed-seven-probe-recovery.json').read_text())
 for anchor in reversed(spec['anchors']):
  if source.count(anchor['after'])!=1:raise ValueError('changed-probe-diagnostic-source')
  source=source.replace(anchor['after'],anchor['before'],1)
 if hashlib.sha256(source.encode()).hexdigest()!=spec['beforeSHA256']:
  raise ValueError('changed-probe-diagnostic-source')
 return source

def original_diagnostic_source(source):
 source=recover_managed_source(source)
 for before,after in (*ENVIRONMENT_ANCHORS,*DIAGNOSTIC_ANCHORS):
  if source.count(after)!=1:raise ValueError('changed-probe-diagnostic-source')
  source=source.replace(after,before,1)
 return source

class SourceCoherence(unittest.TestCase):
 def test_all_six_current_reviewed_source_bytes_match_frozen_metadata(self):
  probe.verify_reviewed_sources(SOURCE)
  pins=json.loads((HERE/'source-pins.json').read_text())
  self.assertEqual(set(pins),set(NAMES))
  for name in NAMES:
   self.assertEqual(hashlib.sha256((SOURCE/name).read_bytes()).hexdigest(),pins[name])

 def test_previous_manage_pin_refuses_actual_current_source_before_any_port_or_process(self):
  pins=json.loads((HERE/'source-pins.json').read_text())
  pins['manage.py']='9671e9e35b34cdbeef55a3cc37d8f9e0f0a921caeafc5c47b6fa3c579d444a3b'
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);(root/'source-pins.json').write_text(json.dumps(pins))
   with patch.object(probe,'HERE',root),patch.object(probe,'free_ports')as ports,patch.object(probe.subprocess,'Popen')as child:
    with self.assertRaisesRegex(ValueError,'probe-reviewed-source-changed'):probe.verify_reviewed_sources(SOURCE)
   ports.assert_not_called();child.assert_not_called()

 def test_mutation_of_each_dependency_refuses_without_auto_updating_pins(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp)
   for name in NAMES:(root/name).write_bytes((SOURCE/name).read_bytes())
   for name in NAMES:
    original=(root/name).read_bytes();(root/name).write_bytes(original+b'\n# authored mutation\n')
    with self.subTest(name=name),self.assertRaisesRegex(ValueError,'probe-reviewed-source-changed'):
     probe.verify_reviewed_sources(root)
    (root/name).write_bytes(original)
   probe.verify_reviewed_sources(root)

 def test_missing_extra_invalid_digest_and_overlong_metadata_refuse(self):
  good=json.loads((HERE/'source-pins.json').read_text())
  missing=dict(good);missing.pop('manage.py')
  extra={**good,'../outside.py':'0'*64}
  for bad in [missing,extra,{**good,'manage.py':False},{**good,'manage.py':'A'*64},{**good,'manage.py':'0'*63}]:
   with tempfile.TemporaryDirectory()as tmp:
    root=Path(tmp);(root/'source-pins.json').write_text(json.dumps(bad))
    with patch.object(probe,'HERE',root),self.assertRaisesRegex(ValueError,'probe-reviewed-source-schema'):
     probe.verify_reviewed_sources(SOURCE)
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp);(root/'source-pins.json').write_bytes(b' '*4097)
   with patch.object(probe,'HERE',root),self.assertRaises(ValueError):probe.verify_reviewed_sources(SOURCE)

 def test_source_and_metadata_symlinks_do_not_enter_the_full_byte_check(self):
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp)
   for name in NAMES:(root/name).write_bytes((SOURCE/name).read_bytes())
   (root/'manage.py').unlink();(root/'manage.py').symlink_to(SOURCE/'manage.py')
   with self.assertRaisesRegex(ValueError,'input-path-not-canonical'):probe.verify_reviewed_sources(root)
   (root/'source-pins.json').symlink_to(HERE/'source-pins.json')
   with patch.object(probe,'HERE',root),self.assertRaisesRegex(ValueError,'input-path-not-canonical'):
    probe.verify_reviewed_sources(SOURCE)

 def test_actual_preparation_refuses_old_five_schema_and_changed_chrome_before_import_or_ports(self):
  good=json.loads((HERE/'source-pins.json').read_text())
  with tempfile.TemporaryDirectory()as tmp:
   root=Path(tmp)
   repo,lab,output,metadata=(root/name for name in ('repo','lab','output','metadata'))
   for directory in (repo/'browser-client/lab',lab,output,metadata):directory.mkdir(parents=True,mode=0o700)
   source=repo/'browser-client/lab'
   for name in NAMES:(source/name).write_bytes((SOURCE/name).read_bytes())
   for missing in (True,False):
    pins=dict(good)
    if missing:pins.pop('chrome_browser.py')
    else:(source/'chrome_browser.py').write_bytes((SOURCE/'chrome_browser.py').read_bytes()+b'\n# unknown launcher mutation\n')
    (metadata/'source-pins.json').write_text(json.dumps(pins))
    with self.subTest(missing=missing),patch.object(probe,'HERE',metadata),patch.object(probe,'free_ports')as ports,patch.object(probe.importlib.util,'spec_from_file_location')as importing,patch.object(probe.subprocess,'Popen')as child:
     with self.assertRaisesRegex(ValueError,'probe-reviewed-source-schema'if missing else 'probe-reviewed-source-changed'):probe.prepare(repo,lab,output)
     ports.assert_not_called();importing.assert_not_called();child.assert_not_called()

 def test_exact_original_probe_recovered_after_only_reviewed_validation_factor(self):
  amended=original_diagnostic_source((HERE/'probe.py').read_text())
  start=amended.index('def verify_reviewed_sources(source):')
  end=amended.index('def prepare(repo,lab,output):',start)
  restored=amended[:start]+amended[end:]
  original=" pins=json.loads((HERE/'source-pins.json').read_text())\n for name,value in pins.items():\n  if sha(source/name)!=value:raise ValueError('probe-reviewed-source-changed')\n"
  self.assertEqual(restored.count(' verify_reviewed_sources(source)\n'),1)
  restored=restored.replace(' verify_reviewed_sources(source)\n',original)
  storage=" exclusive(lab/'runtime/admin.json',(json.dumps({'username':'browser-lab-admin','password':cred['token']})+'\\n').encode())\n"
  anchor=" app=lab/'appimage/squashfs-root';server=lab/'server/opt/overte'\n"
  self.assertEqual(restored.count(anchor),1)
  restored=restored.replace(anchor,storage+anchor)
  self.assertEqual(restored.encode(),(HERE/'fixtures/probe-source-before.py.txt').read_bytes())


 def test_exact_diagnostic_recovery_refuses_malformed_unknown_and_duplicate_additions(self):
  source=(HERE/'probe.py').read_text()
  self.assertEqual(hashlib.sha256(original_diagnostic_source(source).encode()).hexdigest(),'3fa1ca93eddf241272aa9d8369ce3ac4a6a1eaaad811a2869d668af335fedc78')
  for old,new in [('FIXED_FAILURES=', 'UNKNOWN_FAILURES='), ("print('ATOMIC_PROBE_FAILURE:'", "print('private-secret:'"), ('type(error)is ValueError', 'isinstance(error,Exception)')]:
   self.assertIn(old,source)
   with self.subTest(alteration=old),self.assertRaisesRegex(ValueError,'changed-probe-diagnostic-source'):
    original_diagnostic_source(source.replace(old,new,1))
  with self.assertRaisesRegex(ValueError,'changed-probe-diagnostic-source'):
   original_diagnostic_source(source+DIAGNOSTIC_ANCHORS[0][1])


 def test_exact_environment_recovery_refuses_unknown_bound_marker_and_duplicate_block(self):
  source=(HERE/'probe.py').read_text()
  for old,new in [('MAX_CAPTURE,MAX_ENV_ENTRIES,','MAX_CAPTURE,UNKNOWN_BOUND,'),('launch-record-size-invalid','private-unreviewed-tag'),('ATOMIC_PROBE_ENVIRONMENT:','PRIVATE_ENVIRONMENT:')]:
   self.assertIn(old,source)
   with self.subTest(alteration=old),self.assertRaisesRegex(ValueError,'changed-probe-diagnostic-source'):
    original_diagnostic_source(source.replace(old,new,1))
  with self.assertRaisesRegex(ValueError,'changed-probe-diagnostic-source'):
   original_diagnostic_source(source+ENVIRONMENT_ANCHORS[2][1])

if __name__=='__main__':unittest.main()
