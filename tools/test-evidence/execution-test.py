#!/usr/bin/env python3
"""Actual trusted-controller regressions against disposable immutable checkouts."""

from copy import deepcopy
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock
import unittest
import venv

import execution

ENVIRONMENT = {"profile": "deterministic-controller-fixture-v1", "python": "fixture"}
PRIVATE_VARIABLES = (
    "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_ENV", "GITHUB_OUTPUT", "GITHUB_PATH", "GITHUB_STATE",
    "GITHUB_STEP_SUMMARY", "ACTIONS_RUNTIME_TOKEN", "ACTIONS_ID_TOKEN_REQUEST_TOKEN",
    "ACTIONS_ID_TOKEN_REQUEST_URL", "ACTIONS_RUNTIME_URL", "ACTIONS_RESULTS_URL",
)


def registry():
    suites = {}
    for name in ("first", "second"):
        suites[name] = {
            "command": ["python", f"tests/{name}.py"], "layer": "quick", "scope": "content",
            "environment": "host-qt5-qt6",
            "closure": {"kind": "repository", "inputs": [], "required": [f"tests/{name}.py"]},
        }
    return {"schema": 1, "control_inputs": ["tests/*.py"], "suites": suites}


class TrustedExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-trusted-execution-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "candidate"
        self.root.mkdir()
        self.receipt = Path(self.temporary.name) / "execution.json"
        self.junit = Path(self.temporary.name) / "execution.xml"
        self.registry = registry()
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Trusted execution fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.write(".gitignore", "build/\n__pycache__/\n")
        for name in ("first", "second"):
            self.write(f"tests/{name}.py", f'from pathlib import Path\np = Path("build/{name}")\np.parent.mkdir(exist_ok=True)\np.write_text("observed")\n')
        # These source-controlled declarations are hostile fixture inputs. The
        # trusted controller must never import either as its shared inventory.
        self.write("tests/run-project-tests.py", 'raise RuntimeError("candidate runner imported")\n')
        self.write(".github/test-suites.json", json.dumps({"suites": {}}))
        self.write("tests/platform-profile.json", json.dumps({"schema": 1, "platform": "shared", "suites": []}))
        self.commit()

    def git(self, *arguments):
        return subprocess.check_output(["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *arguments],
                                       cwd=self.root, text=True, stderr=subprocess.PIPE).strip()

    def write(self, relative, source):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "Immutable controller fixture")

    def execute(self, names=None, include_platform=False, runtime_side_effect=None):
        with mock.patch.object(execution.inputs, "load_registry", return_value=self.registry), \
                mock.patch.object(execution.runtime, "capture_host_environment", return_value=ENVIRONMENT,
                                  side_effect=runtime_side_effect):
            return execution.execute(self.root, names, include_platform=include_platform,
                                     junit=self.junit, receipt_path=self.receipt, timeout=10, host_timeout=10)

    def validate(self, receipt, require_all=True):
        return execution.validate_receipt(receipt, self.registry, execution.inputs.full_tree(self.root), require_all=require_all)

    def resign(self, receipt):
        receipt.pop("receipt_digest", None)
        receipt["receipt_digest"] = execution.digest(receipt)
        return receipt

    def test_real_commands_observed_despite_candidate_inventory_and_runner_omissions(self):
        status, receipt = self.execute()
        self.assertEqual(status, 0)
        self.assertEqual(set(receipt["results"]), {"first", "second"})
        self.assertEqual(receipt["conclusion"], "success")
        self.assertTrue(receipt["reusable"])
        self.assertEqual(json.loads(self.receipt.read_text()), receipt)
        self.assertTrue(self.junit.is_file())
        self.assertTrue(all((self.root / "build" / name).read_text() == "observed" for name in receipt["results"]))
        self.assertEqual(set(self.validate(receipt)), {"first", "second"})

    def test_requested_subset_runs_only_selected_trusted_common_suite(self):
        status, receipt = self.execute(["second"])
        self.assertEqual(status, 0)
        self.assertEqual(receipt["requested_suites"], ["second"])
        self.assertFalse((self.root / "build/first").exists())
        self.assertEqual(set(self.validate(receipt, require_all=False)), {"second"})
        with self.assertRaises(execution.ExecutionError):
            self.validate(receipt)

    def test_explicit_empty_shared_selection_executes_no_reused_suite(self):
        status, receipt = self.execute([])
        self.assertEqual(status, 0)
        self.assertEqual(receipt["requested_suites"], [])
        self.assertEqual(receipt["results"], {})
        self.assertEqual(self.validate(receipt, require_all=False), {})
        with self.assertRaises(execution.ExecutionError):
            self.validate(receipt)
        self.assertFalse((self.root / "build/first").exists())

    def test_failing_actual_suite_never_creates_successful_qualification(self):
        self.write("tests/first.py", "raise SystemExit(17)\n")
        self.commit()
        status, receipt = self.execute()
        self.assertNotEqual(status, 0)
        self.assertEqual(receipt["conclusion"], "failure")
        self.assertEqual(receipt["results"]["first"]["status"], "failed")
        self.assertEqual(receipt["results"]["second"]["status"], "passed")
        with self.assertRaises(execution.ExecutionError):
            self.validate(receipt)

    def test_receipt_cannot_drop_requested_suite_or_forge_its_fingerprint(self):
        _, receipt = self.execute()
        dropped = deepcopy(receipt)
        del dropped["results"]["second"]
        forged = deepcopy(receipt)
        forged["results"]["second"]["fingerprint"] = "sha256:" + "0" * 64
        narrowed = deepcopy(receipt)
        narrowed["requested_suites"] = ["first"]
        del narrowed["results"]["second"]
        for changed in (dropped, forged, narrowed):
            with self.subTest(changed=changed), self.assertRaises(execution.ExecutionError):
                self.validate(self.resign(changed))

    def test_unknown_duplicate_and_platform_names_cannot_select_shared_omissions(self):
        for names in (["unknown"], ["first", "first"]):
            with self.subTest(names=names), self.assertRaises(execution.ExecutionError):
                self.execute(names)

    def test_unknown_runtime_runs_all_and_cannot_claim_reusable_fingerprints(self):
        status, receipt = self.execute(["first"], runtime_side_effect=execution.runtime.RuntimeIdentityError("unsupported"))
        self.assertEqual(status, 0)
        self.assertEqual(set(receipt["results"]), {"first", "second"})
        self.assertFalse(receipt["reusable"])
        self.assertIsNone(receipt["environment"])
        self.assertTrue(all(item["fingerprint"] is None for item in receipt["results"].values()))
        self.validate(receipt)

    def test_candidate_source_changes_and_untracked_inputs_cannot_be_attested(self):
        self.write("tests/untracked.py", "raise RuntimeError('unexpected import input')\n")
        with self.assertRaises(execution.ExecutionError):
            self.execute()
        (self.root / "tests/untracked.py").unlink()
        self.write("tests/first.py", 'from pathlib import Path\nPath(__file__).write_text("changed\\n")\n')
        self.commit()
        with self.assertRaises(execution.ExecutionError):
            self.execute()
        self.assertFalse(self.receipt.exists())

    def test_runtime_changed_during_tests_cannot_issue_reusable_receipt(self):
        with self.assertRaises(execution.ExecutionError):
            self.execute(runtime_side_effect=[ENVIRONMENT, {"profile": "different"}])
        self.assertFalse(self.receipt.exists())

    def test_candidate_git_cleanup_and_token_isolation_match_capture_and_restore_parent(self):
        self.git("config", "maintenance.auto", "true")
        self.git("config", "gc.auto", "37")
        self.write("tests/first.py", """import json, os, subprocess
from pathlib import Path
names = PRIVATE_ENV_NAMES
observed = {name: name in os.environ for name in names}
observed['maintenance'] = subprocess.check_output(['git', 'config', '--get', 'maintenance.auto'], text=True).strip()
observed['gc'] = subprocess.check_output(['git', 'config', '--get', 'gc.auto'], text=True).strip()
observed['count'] = os.environ.get('GIT_CONFIG_COUNT')
observed['extra_key'] = 'GIT_CONFIG_KEY_7' in os.environ
observed['parameters'] = 'GIT_CONFIG_PARAMETERS' in os.environ
Path('build').mkdir(exist_ok=True)
Path('build/policy-observation.json').write_text(json.dumps(observed))
""".replace("PRIVATE_ENV_NAMES", repr(PRIVATE_VARIABLES)))
        self.commit()
        parent = {name: "synthetic-parent-only" for name in PRIVATE_VARIABLES}
        parent.update({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.name",
                       "GIT_CONFIG_VALUE_0": "Parent observation fixture", "GIT_CONFIG_KEY_7": "unused.parent",
                       "GIT_CONFIG_VALUE_7": "preserve", "GIT_CONFIG_PARAMETERS": "'gc.auto=38'",
                       "PATH": os.environ.get("PATH", os.defpath), "VIRTUAL_ENV": "unrelated-parent-prefix"})
        captures = []
        def capture():
            captures.append({name: os.environ.get(name) for name in parent})
            return ENVIRONMENT
        with mock.patch.dict(os.environ, parent), \
                mock.patch.object(execution.inputs, "load_registry", return_value=self.registry), \
                mock.patch.object(execution.runtime, "capture_host_environment", side_effect=capture):
            status, receipt = execution.execute(self.root, ["first"], receipt_path=self.receipt, timeout=10, host_timeout=10)
            self.assertEqual({name: os.environ.get(name) for name in parent}, parent)
        self.assertEqual(status, 0)
        self.assertTrue(receipt["reusable"])
        captured = {name: None for name in parent}
        captured.update({"GIT_CONFIG_COUNT": "2", "GIT_CONFIG_KEY_0": "maintenance.auto", "GIT_CONFIG_VALUE_0": "false",
                         "PATH": str(Path(sys.executable).parent) + os.pathsep + parent["PATH"],
                         "VIRTUAL_ENV": sys.prefix if sys.prefix != sys.base_prefix else None})
        self.assertEqual(captures, [captured, captured], "runtime capture must observe the same effective child environment")
        observed = json.loads((self.root / "build/policy-observation.json").read_text())
        self.assertEqual(observed.pop("maintenance"), "false")
        self.assertEqual(observed.pop("gc"), "0")
        self.assertEqual(observed.pop("count"), "2")
        self.assertFalse(any(observed.values()), "candidate cannot see credentials, Actions endpoints/command files or ambient Git overrides")

    def test_candidate_environment_restores_parent_when_process_launch_fails(self):
        controller = execution._runner()
        with mock.patch.dict(os.environ, {name: "synthetic-parent-only" for name in PRIVATE_VARIABLES}):
            before = dict(os.environ)
            with mock.patch.object(execution, "_runner", return_value=controller), \
                    mock.patch.object(controller, "run_command", side_effect=OSError("fixture launch failure")):
                with self.assertRaises(OSError):
                    self.execute(["first"])
            self.assertTrue(dict(os.environ) == before, "launch failure must restore the trusted parent environment")

    def test_env_python3_wrapper_uses_controller_venv_despite_ambient_system_python(self):
        if not Path("/usr/bin/python3").exists():
            self.skipTest("fixture requires the supported Linux system Python alias")
        prefix = Path(self.temporary.name) / "host-env"
        venv.EnvBuilder(with_pip=False, symlinks=True).create(prefix)
        site_packages = prefix / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
        (site_packages / "controller_only_fixture.py").write_text("VALUE = 'prepared-controller-env'\n")
        wrapper = Path(self.temporary.name) / "env-python-wrapper"
        wrapper.write_text("#!/usr/bin/env python3\nimport json, os, sys\nfrom controller_only_fixture import VALUE\n"
                           "print(json.dumps({'value': VALUE, 'same_prefix': sys.prefix == os.environ.get('VIRTUAL_ENV')}))\n")
        wrapper.chmod(0o755)
        parent = {"PATH": "/usr/bin:/bin", "VIRTUAL_ENV": "unrelated-parent-prefix"}
        with mock.patch.dict(os.environ, parent), mock.patch.object(execution.sys, "executable", str(prefix / "bin/python")), \
                mock.patch.object(execution.sys, "prefix", str(prefix)), \
                mock.patch.object(execution.runtime.site, "ENABLE_USER_SITE", False):
            ambient = subprocess.run([str(wrapper)], capture_output=True, text=True)
            self.assertNotEqual(ambient.returncode, 0, "ambient base Python must not see the venv-only fixture dependency")
            before = dict(os.environ)
            with self.assertRaisesRegex(RuntimeError, "fixture failure"):
                with execution.candidate_process_environment():
                    identity = execution.runtime._python_lookup_identity()
                    self.assertEqual(identity["mode"], "controller-virtualenv")
                    result = subprocess.run([str(wrapper)], capture_output=True, text=True, check=True)
                    self.assertEqual(json.loads(result.stdout), {"value": "prepared-controller-env", "same_prefix": True})
                    raise RuntimeError("fixture failure")
            self.assertEqual(dict(os.environ), before, "failure must restore PATH and VIRTUAL_ENV exactly")

    def test_private_process_environment_covers_the_sync_consumer_boundary(self):
        source = ast.parse((Path(execution.__file__).parent / "validate-sync.py").read_text())
        boundary = next(node.value for node in source.body if isinstance(node, ast.Assign)
                        and any(isinstance(target, ast.Name) and target.id == "_CANDIDATE_PRIVATE_ENVIRONMENT"
                                for target in node.targets))
        self.assertLessEqual(set(ast.literal_eval(boundary)), set(execution._CANDIDATE_PRIVATE_ENVIRONMENT),
                             "qualification children must receive at least the synchronization consumer's isolation")

    def test_validated_platform_suite_runs_separately_without_claiming_shared_proof(self):
        self.write("tests/platform.py", "print('real product fixture')\n")
        self.write("tests/platform-profile.json", json.dumps({"schema": 1, "platform": "android", "suites": [
            {"name": "product-fixture", "entrypoint": "tests/platform.py", "interpreter": "python"}]}))
        self.commit()
        status, receipt = self.execute(include_platform=True)
        self.assertEqual(status, 0)
        self.assertEqual(set(receipt["results"]), {"first", "second"})
        self.assertEqual(receipt["platform_results"], {"product-fixture": {
            "status": "passed", "command": ["python", "tests/platform.py"]}})
        self.validate(receipt)

    def test_invalid_platform_profile_fails_before_any_shared_suite_runs(self):
        cases = [
            {"schema": 1, "platform": "android", "suites": []},
            {"schema": True, "platform": "shared", "suites": []},
            {"schema": 1, "platform": "android", "suites": [{"name": "first", "entrypoint": "tests/first.py", "interpreter": "python"}]},
            {"schema": 1, "platform": "android", "suites": [{"name": "product", "entrypoint": "../outside.py", "interpreter": "python"}]},
        ]
        for value in cases:
            with self.subTest(value=value):
                self.write("tests/platform-profile.json", json.dumps(value))
                self.commit()
                with self.assertRaises(execution.ExecutionError):
                    self.execute(include_platform=True)
        self.assertFalse((self.root / "build/first").exists())

    def test_platform_entrypoint_cannot_replace_test_execution_with_interpreter_help(self):
        for interpreter, entrypoint in (("python", "--version"), ("bash", "--help")):
            with self.subTest(interpreter=interpreter):
                self.write(entrypoint, "exit 17\n" if interpreter == "bash" else "raise SystemExit(17)\n")
                self.write("tests/platform-profile.json", json.dumps({"schema": 1, "platform": "android", "suites": [
                    {"name": "product-fixture", "entrypoint": entrypoint, "interpreter": interpreter}]}))
                self.commit()
                with self.assertRaisesRegex(execution.ExecutionError, "interpreter option"):
                    self.execute(include_platform=True)
                self.assertFalse(self.receipt.exists())
                self.assertFalse((self.root / "build/first").exists())


class ProtectedProducerOrderingTests(unittest.TestCase):
    @staticmethod
    def source_snapshot():
        # Actual materializer shape keeps profile outside the raw two-key map.
        merge, base, head = 'a'*40, 'b'*40, 'c'*40
        return {'profile': 'streamed-candidate-source-v1', 'digest': 'sha256:'+'1'*64,
            'identity': {'commit': merge, 'tree': 'f'*40},
            'git_context': {'commits': {
                merge: {'commit': merge, 'tree': 'f'*40, 'parents': [base,head]},
                base: {'commit': base, 'tree': 'd'*40, 'parents': []},
                head: {'commit': head, 'tree': 'e'*40, 'parents': []}}, 'shallow': []}}

    def test_root_selects_only_pristine_snapshot_and_materializes_once(self):
        # Pure control fixture: no UID changes, namespaces, cgroups or workloads.
        from types import SimpleNamespace
        import producer_workflow as producer
        events = []
        raw = Path('/raw-actions-checkout')
        environment = {'SUDO_UID': '1001', 'GITHUB_SHA': 'a'*40, 'ImageOS': 'ubuntu24',
                       'ImageVersion': 'fixture', 'RUNNER_ENVIRONMENT': 'github-hosted'}
        context = {'binding': {'merge_sha': 'a'*40}, 'run_id': 17, 'registry': {'suites': {}},
                   'refs': {'default': 'd'*40},
                   'profile': producer.FULL_PROFILE, 'profile_binding': None,
                   'selected': {'suites': [], 'full_host': True, 'include_platform': True}}
        snapshot = self.source_snapshot()
        destination = []
        def materialize(revision, path, *, repository):
            self.assertEqual(repository, raw)
            destination.append(path)
            events.append('materialize')
            return snapshot
        def select(path, *_):
            self.assertEqual(events, ['materialize'])
            self.assertEqual(path, destination[0])
            self.assertNotEqual(path, raw)
            events.append('select-pristine')
            return context
        actual_stat = os.stat
        def stat(path, *args, **kwargs):
            return SimpleNamespace(st_ino=123) if str(path).startswith('/proc/self/ns/') else actual_stat(path,*args,**kwargs)
        prepared = ((),None,None,None)
        patches = [mock.patch.object(producer,'PRODUCTION_READY',True),
              mock.patch.object(producer.sandbox,'ACTIVATION_READY',True),
              mock.patch.object(producer.attested,'load_policy',return_value={'fixture':'trusted isolated policy only'}),
              mock.patch.object(producer.os,'geteuid',return_value=0),
              mock.patch.object(producer.os,'stat',side_effect=stat),
              mock.patch.object(producer.signal,'signal'),
              mock.patch.object(producer,'_native',return_value=(17,18)),
              mock.patch.object(producer.host,'verify_account',return_value=(2001,2001)),
              mock.patch.object(producer.host,'prepare_delegation'),
              mock.patch.object(producer.shared,'prepared_tools',return_value=prepared),
              mock.patch.object(producer.shared,'identity_roots',return_value=()),
              mock.patch.object(producer.shared,'prepared_identity',return_value={}),
              mock.patch.object(producer.shared,'materialize_source',side_effect=materialize),
              mock.patch.object(producer,'prepare',side_effect=select),
              mock.patch.object(producer,'current_run',side_effect=lambda *_:events.append('native-job')),
              mock.patch.object(producer,'_descriptor',side_effect=lambda *_:events.append('descriptor')),
              mock.patch.object(producer.shared,'sources',return_value=[]),
              mock.patch.object(producer.shared,'project_policy',side_effect=lambda *_a,**kw:
                  self.assertEqual(kw, {'trusted_source': context['refs']['default']}) or {}),
              mock.patch.object(producer.sandbox,'_write_source'),
              mock.patch.object(producer.sandbox,'_files',return_value={}),
              mock.patch.object(producer.shared,'Batch', side_effect=lambda *args:batches.append(args)),
              mock.patch.object(producer,'protected_receipt',side_effect=lambda *_:events.append('actual-selected-run') or 'fake-only-result'),
              mock.patch.object(producer,'_bookend',side_effect=lambda *_:events.append('fresh-bookend'))]
        from contextlib import ExitStack
        batches=[]
        with ExitStack() as stack:
            for item in patches:stack.enter_context(item)
            adapter=SimpleNamespace(current=lambda _:({'merge_sha':'a'*40},{}))
            self.assertEqual(producer.shared_execution(raw,{},environment,adapter),'fake-only-result')
            self.assertEqual(events.count('materialize'),1)
            self.assertEqual(batches[0][1],destination[0])
            actual_git = batches[0][5]['git_context']
            self.assertEqual(actual_git, producer.git_context(snapshot))
            self.assertEqual(set(actual_git), {'profile','commits','shallow'})
            self.assertEqual(actual_git['profile'], snapshot['profile'])
            self.assertEqual(set(snapshot['git_context']), {'commits','shallow'})
            execution.validate_git_context(actual_git, 'a'*40, 'f'*40)
        self.assertEqual(events,['materialize','select-pristine','native-job','descriptor','actual-selected-run','fresh-bookend','native-job'])

    def test_retained_source_git_binding_fails_before_any_suite_callback(self):
        from contextlib import ExitStack
        from types import SimpleNamespace
        import producer_workflow as producer
        snapshot = self.source_snapshot()
        canonical = producer.git_context(snapshot)
        for defect in ('raw-two-key','profile','missing-parent','parent-order','tree','source'):
            binding = {'source':'a'*40,'git_context':deepcopy(canonical)}
            git = binding['git_context']
            if defect == 'raw-two-key':binding['git_context']=deepcopy(snapshot['git_context'])
            elif defect == 'profile':git['profile']='unreviewed-source-profile'
            elif defect == 'missing-parent':del git['commits']['b'*40]
            elif defect == 'parent-order':git['commits']['a'*40]['parents'].reverse()
            elif defect == 'tree':git['commits']['a'*40]['tree']='9'*40
            elif defect == 'source':binding['source']='b'*40
            context = {'profile':producer.FULL_PROFILE,'registry':registry(),
                'policy':SimpleNamespace(producer=SimpleNamespace(required_execution_schema=4)),
                'refs':{'default':'d'*40},'binding':{'merge_sha':'a'*40,'merge_tree':'f'*40},
                'git_context':canonical,'source_context':{},
                'plan':{'owners':{'shared-host':{'suites':['first','second'],'include_platform':False}}}}
            batch = SimpleNamespace(candidate=Path('/candidate'),snapshot=snapshot,policy=Path('/policy'),
                projection={},binding=binding)
            # Only capture is faked; the canonical Git validator stays real.
            # No complete source/native envelope or execution PASS is fabricated.
            with (self.subTest(defect=defect),ExitStack() as stack):
                stack.enter_context(mock.patch.object(producer.inputs,'full_tree',return_value={}))
                stack.enter_context(mock.patch.object(producer.ci_profile,'load_controller_projection',
                    return_value={'source_commit':'d'*40}))
                capture=stack.enter_context(mock.patch.object(producer.ci_profile,'capture_retained_source',
                    return_value={'binding':binding}))
                suites=stack.enter_context(mock.patch.object(producer.shared,'check_batch',
                    side_effect=AssertionError('candidate suites reached with malformed source binding')))
                with self.assertRaises(execution.ExecutionError) as caught:
                    producer.protected_receipt(batch,context,[],{})
                self.assertIs(type(caught.exception), execution.ExecutionError)
                self.assertNotIsInstance(caught.exception, producer.PreExecutionUnavailable)
                capture.assert_called_once()
                suites.assert_not_called()

    def test_canonical_retained_source_binding_reaches_suite_callback_without_minting_receipt(self):
        from types import SimpleNamespace
        import producer_workflow as producer
        snapshot=self.source_snapshot();canonical=producer.git_context(snapshot)
        binding={'source':'a'*40,'git_context':deepcopy(canonical)}
        context={'profile':producer.FULL_PROFILE,'registry':registry(),
            'policy':SimpleNamespace(producer=SimpleNamespace(required_execution_schema=4)),
            'refs':{'default':'d'*40},'binding':{'merge_sha':'a'*40,'merge_tree':'f'*40},
            'git_context':canonical,'source_context':{},
            'plan':{'owners':{'shared-host':{'suites':['first','second'],'include_platform':False}}}}
        batch=SimpleNamespace(candidate=Path('/candidate'),snapshot=snapshot,policy=Path('/policy'),
            projection={},binding=binding)
        class StopBeforeWorkload(Exception):pass
        with (mock.patch.object(producer.inputs,'full_tree',return_value={}),
              mock.patch.object(producer.ci_profile,'load_controller_projection',return_value={'source_commit':'d'*40}),
              mock.patch.object(producer.ci_profile,'capture_retained_source',return_value={'binding':binding}),
              mock.patch.object(producer.shared,'check_batch',side_effect=StopBeforeWorkload) as suites,
              self.assertRaises(StopBeforeWorkload)):
            producer.protected_receipt(batch,context,[],{})
        suites.assert_called_once()
        self.assertEqual(set(snapshot['git_context']),{'commits','shallow'})



if __name__ == "__main__":
    unittest.main()
