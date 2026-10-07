# SPDX-License-Identifier: Apache-2.0
"""Fixed managed composition source contracts; no service or namespace launch."""
import ast,hashlib,json,sys,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
LAB=HERE.parent
sys.path.insert(0,str(LAB))
import probe
import test_manage_state as host
import test_kernel_audit_integration as audit

SEVEN=('manage.py','native_admin.py','guest_permissions.py','provisioning_diagnostics.py','host_tools.py','chrome_browser.py','native_launch.py')
FINAL={'manage.py':'53cd7fcce5887c993bc724ce3e391c4c7d0975f338ed1c96a1adfdbe7c9bdb95','native_launch.py':'5358a62e101c2fc8fc94063b6ec617a9a221b93b6778f59fc80cac2171ccc581','atomic-provisioning/probe.py':'67d90f5598f05ef50af1098d33854cb64165b315874aa449003119adc03364e1'}
def sha(b):return hashlib.sha256(b).hexdigest()
def methods(p):
 text=p.read_text();lines=text.splitlines(True)
 return {cl.name+'.'+n.name:sha(''.join(lines[n.lineno-1:n.end_lineno]).encode()) for cl in ast.parse(text).body if isinstance(cl,ast.ClassDef)for n in cl.body if isinstance(n,ast.FunctionDef)and n.name.startswith('test_')}
def cases(suite):
 for c in suite:
  if isinstance(c,unittest.TestSuite):yield from cases(c)
  else:yield c
class Composition(unittest.TestCase):
 def test_exact_three_complete_reviewed_sources_and_literal_seven(self):
  for n,h in FINAL.items():self.assertEqual(sha((LAB/n).read_bytes()),h,n)
  self.assertEqual(probe.SOURCE_DEPENDENCIES,frozenset(SEVEN));probe.verify_reviewed_sources(LAB)
 def test_host_route_keeps_all_original84_and_added10_once(self):
  records=list(cases(unittest.defaultTestLoader.loadTestsFromModule(host)))
  ids=[c.id()for c in records];self.assertEqual(len(ids),94);self.assertEqual(len(set(ids)),94)
  expected={'ManagedState':12,'ManagedLaunchRecords':4,'OwnedSupervisor':1,'GuestReadback':6,'ProvisioningDiagnostics':11,'StopContracts':12,'SessionBoundary':2,'ParentGuards':11,'NativePrivilege':4,'AdmitRetirement':1,'Registered':11,'PythonBoundary':4,'OwnedCPU':3,'RealParent':2}
  actual={type(c).__name__:sum(type(d)is type(c)for d in records)for c in records}
  self.assertEqual({name: count for name, count in actual.items() if name in expected},expected)
  self.assertEqual(sum(actual[name] for name in expected),84)
  self.assertEqual({name: count for name, count in actual.items() if name not in expected},{'ManagedAncestry':9,'ManagedAncestryOwnedCPU':1})
 def test_original_host_and_real_bwrap_assertions_remain_byte_exact(self):
  record=json.loads((LAB/'fixtures/managed-lifetime-original-bodies.json').read_text())
  for file,key in(('test_manage_state.py','originalHostMethods'),('test_native_launch.py','originalNativeMethods')):
   current=methods(LAB/file)
   for name,h in record[key].items():self.assertEqual(current[name],h,name)
  text=(LAB/'test_native_launch.py').read_text();self.assertIn('time.monotonic() + 2.5',text)
 def test_fixed_historical_helper_is_not_a_current_runtime_source(self):
  old=(LAB/'fixtures/native-launch-original-fda.py').read_bytes()
  self.assertEqual(sha(old),'c7bd9635f970e4b936231fb76d4b526e4b4fc11a8b591f6c44afb78833d2a3bd')
  self.assertNotEqual(sha(old),probe.reviewed_source_pins()['native_launch.py'])
  for name in('manage.py','atomic-provisioning/probe.py','native_launch.py'):
   self.assertNotIn('fixtures/native-launch-original-fda.py',(LAB/name).read_text())
 def test_permanent_controls_read_canonical_sources_and_no_private_producer_tree(self):
  names=('stop','parent_guard','registered_wrapper','python_boundary','owned_cpu','parent_owned_cpu')
  for n in names:
   text=(LAB/('test_managed_'+n+'.py')).read_text()
   self.assertNotIn('/home/user/tmp/',text);self.assertNotIn("HERE/'after/",text)
  self.assertIn("HERE/'manage.py'",(LAB/'test_managed_stop.py').read_text())
  self.assertIn("HERE/'native_launch.py'",(LAB/'test_managed_parent_guard.py').read_text())
 def test_known_operational_workflow_history_refuses_unknown_missing_duplicate_delta(self):
  text=(LAB.parents[1]/'.github/workflows/browser-client-atomic-settings.yml').read_text()
  old=audit.reviewed_workflow_history(text)
  self.assertEqual(sha(old.encode()),'f0ff79cf3ae08b7215994e90612a778479b12661de6bf1a43865f048cfb942e6')
  anchor='python3 -B browser-client/lab/atomic-provisioning/operational_contracts.py'
  for changed in(text+'\n# unknown\n',text.replace(anchor,'',1),text+anchor+'\n'):
   with self.assertRaises(ValueError):audit.reviewed_workflow_history(changed)
 def test_atomic_workflow_covers_each_fixed_seven_dependency_exactly_once(self):
  text=(LAB.parents[1]/'.github/workflows/browser-client-atomic-settings.yml').read_text()
  tree=text.split('  workflow_dispatch:',1)[0]
  for name in SEVEN:self.assertEqual(tree.count("      - 'browser-client/lab/"+name+"'\n"),1,name)
  for name in SEVEN:
   line="      - 'browser-client/lab/"+name+"'\n"
   for changed in(text.replace(line,'',1),text+line):
    with self.assertRaises(ValueError):audit.reviewed_workflow_history(changed)
if __name__=='__main__':unittest.main()
