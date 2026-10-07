"""Pure source/real-test-body controls: no launch, trace or live /proc reads."""
import contextlib,hashlib,importlib.util,io,json,os,shutil,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
LAB=HERE.parent
ROOT=LAB.parents[1]
sys.path[:0]=[str(HERE),str(LAB)]
import operational_contracts as migration
import test_confined_launch as real

class MigrationControls(unittest.TestCase):
 def source(self):
  root=Path(tempfile.mkdtemp(prefix='gate-source-'));self.addCleanup(shutil.rmtree,root)
  for name in ('operational-gate-source.json','test_observer.py','test_tmpfile_contract.py','test_preflight_diagnostics.py','test_confined_launch.py'):
   shutil.copyfile(HERE/name,root/name)
  return root
 def suite(self):
  def named(name):
   case=unittest.FunctionTestCase(lambda:None);case.id=lambda:name;return case
  return unittest.TestSuite(named(name) for name in migration.REQUIRED)
 def test_authenticate_all_current_and_three_exact_full_histories(self):
  document=migration.authenticate_sources();self.assertEqual(len(document['current']),4)
  self.assertEqual(document['historical']['browser-client/lab/atomic-provisioning/test_observer.py']['sha256'],'0e5fc33e4664afa96c9371efd98de104bb2c52a5ca54359256b6145607dc96d9')
 def test_whole_current_mutation_refuses_even_with_original_assertions_present(self):
  r=self.source();p=r/'test_observer.py';p.write_bytes(p.read_bytes()+b'\n# changed\n')
  with self.assertRaisesRegex(ValueError,'operational-current-source-changed'):migration.authenticate_sources(r)
 def test_current_checksum_refresh_does_not_bypass_old_whole_hash(self):
  r=self.source();p=r/'test_observer.py';p.write_bytes(p.read_bytes().replace(b'timeout=8)',b'timeout=9)',1))
  q=r/'operational-gate-source.json';m=json.loads(q.read_text());row=m['current']['browser-client/lab/atomic-provisioning/test_observer.py'];row.update(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest());q.write_text(json.dumps(m))
  with self.assertRaisesRegex(ValueError,'operational-whole-history-changed'):migration.authenticate_sources(r)
 def test_missing_duplicate_and_historical_discovery_refuse(self):
  for change in ('missing','duplicate','historical'):
   suite=self.suite()
   if change=='missing':suite=unittest.TestSuite(list(suite)[1:])
   else:
    case=unittest.FunctionTestCase(lambda:None);case.id=lambda:migration.REQUIRED[0] if change=='duplicate' else migration.HISTORICAL[0];suite.addTest(case)
   with self.assertRaisesRegex(ValueError,'operational-gate-census-refused'):migration.admit_suite(suite)
 def test_failed_import_is_not_counted_as_valid_discovery(self):
  suite=self.suite();suite.addTest(unittest.defaultTestLoader.loadTestsFromName('nonexistent_reviewed_gate'))
  with self.assertRaisesRegex(ValueError,'operational-gate-census-refused'):migration.admit_suite(suite)
 def test_current_required_census_admits_without_running_any_body(self):self.assertEqual(len(migration.admit_suite(self.suite())),4)
 def test_skipped_case_is_failed_not_operational_success(self):
  case=unittest.FunctionTestCase(lambda: (_ for _ in ()).throw(unittest.SkipTest('bounded-authored-negative')))
  result=unittest.TextTestRunner(stream=io.StringIO(),resultclass=migration.StrictResult).run(unittest.TestSuite([case]));self.assertFalse(result.wasSuccessful());self.assertEqual(len(result.skipped),1)
 def run_real(self,row):
  case=real.ConfinedLaunchTests('test_fixed_denial_keeps_zero_caps_and_exclusive_temp_atomic_rename')
  completed=__import__('subprocess').CompletedProcess(['mocked-no-runtime'],0,json.dumps(row).encode(),b'')
  with patch.object(real,'base_command',return_value=['/usr/bin/bwrap','--cap-drop','ALL']),patch.object(real,'sealed_filter',return_value=791),patch.object(real.os,'close'),patch.object(real.os,'readlink',return_value='mocked-owned-namespace'),patch.object(real.subprocess,'run',return_value=completed) as run,patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}),contextlib.redirect_stdout(io.StringIO()):
   case.test_fixed_denial_keeps_zero_caps_and_exclusive_temp_atomic_rename()
  self.assertEqual(run.call_count,1);self.assertEqual(run.call_args.kwargs['timeout'],8);self.assertEqual(run.call_args.kwargs['pass_fds'],(791,))
 def good(self):return {**dict.fromkeys(real.KEYS,True),'scope':'CPU-proposed-launch-not-native-acceptance','profile':'signed-bwrap-child-enforce','operationErrno':'none'}
 def test_actual_filtered_operational_test_body_keeps_eight_seconds_and_one_call(self):self.run_real(self.good())
 def test_each_real_security_trace_filter_and_readback_predicate_is_mandatory(self):
  for key in ('zeroCapabilities','noNewPrivileges','userIsolated','ipcIsolated','tracedSync','atomicReadback','tmpfileDenied','openat2Denied','x32Denied'):
   with self.subTest(key=key),self.assertRaises(AssertionError):self.run_real({**self.good(),key:False})
 def test_local_unqualified_profile_cannot_pass_hosted_operational_body(self):
  with self.assertRaises(AssertionError):self.run_real({**self.good(),'profile':'local-unqualified'})
 def test_workflow_runs_explicit_census_without_relaunching_required_test(self):
  text=(ROOT/'.github/workflows/browser-client-atomic-settings.yml').read_text();self.assertEqual(text.count('python3 -B browser-client/lab/atomic-provisioning/operational_contracts.py'),1);self.assertNotIn('python3 -B -m unittest discover',text);self.assertIn("github.repository == 'noah-be/overte'",text);self.assertIn('steps.contracts.outcome ==',text)

if __name__=='__main__':unittest.main(verbosity=2)
