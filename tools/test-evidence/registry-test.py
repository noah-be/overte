#!/usr/bin/env python3
"""Real-registry regressions for execution inventory and import-resolution inputs."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import py_compile
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("registry_review_inputs", Path(__file__).with_name("inputs.py"))
INPUTS = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(INPUTS)
ENVIRONMENT = {"contract": "isolated-import-resolution-fixture-v1"}


class RegistryInventoryTests(unittest.TestCase):
    def test_registry_matches_every_common_host_command_and_layer(self):
        registry = INPUTS.load_registry(ROOT / ".github/test-suites.json")
        spec = importlib.util.spec_from_file_location("registry_project_runner", ROOT / "tests/run-project-tests.py")
        runner = importlib.util.module_from_spec(spec)
        assert spec.loader
        with mock.patch.dict(sys.modules, {spec.name: runner}):
            spec.loader.exec_module(runner)
        platform_names = {suite.name for suite in runner.PLATFORM_SUITES}
        arguments = type("Arguments", (), {"platform_only": False, "suite": [], "profile": "host"})()
        common = {suite.name: suite for suite in runner.select(arguments) if suite.name not in platform_names}
        self.assertEqual(set(registry["suites"]), set(common))
        for name, suite in common.items():
            with self.subTest(suite=name):
                command = ["python" if value == sys.executable else value for value in suite.command]
                self.assertEqual(registry["suites"][name]["command"], command)
                self.assertEqual(registry["suites"][name]["layer"], suite.layer)


class GitImportFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-registry-resolution-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Registry dependency fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "maintenance.auto", "false")
        self.git("config", "gc.auto", "0")
        self.registry = INPUTS.load_registry(ROOT / ".github/test-suites.json")

    def git(self, *arguments):
        return subprocess.check_output(
            ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", *arguments],
            cwd=self.root, text=True, stderr=subprocess.PIPE,
        ).strip()

    def write(self, path, content):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    def prepare_suite(self, name, expected_kind="patterns"):
        definition = self.registry["suites"][name]
        self.assertEqual(definition["closure"]["kind"], expected_kind)
        for path in definition["closure"]["required"]:
            self.write(path, "fixture\n")
        selected = deepcopy(self.registry)
        selected["suites"] = {name: selected["suites"][name]}
        return selected

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "Record immutable import-resolution fixture")
        return INPUTS.full_tree(self.root)

    def assert_requires_execution(self, registry, name, parent, candidate):
        fingerprint = INPUTS.suite_fingerprint(registry, name, parent, ENVIRONMENT)
        self.assertNotEqual(
            fingerprint, INPUTS.suite_fingerprint(registry, name, candidate, ENVIRONMENT),
            "actual registry must bind candidate module-resolution changes",
        )
        proof = {name: {"status": "passed", "fingerprint": fingerprint}}
        plan = INPUTS.plan_reuse(registry, parent, candidate, proof, ENVIRONMENT, ENVIRONMENT)
        self.assertEqual(plan["reused"], [])
        self.assertEqual(plan["required"], [name])


class ImportResolutionIdentityTests(GitImportFixture, unittest.TestCase):
    def test_added_python_shadow_module_invalidates_unchanged_test_entrypoint(self):
        name = "python-test-runner"
        registry = self.prepare_suite(name)
        entry = "tests/unittest-runner-test.py"
        self.write(entry, "import pathlib\nprint(pathlib.Path)\n")
        parent = self.commit()
        command = [sys.executable, str(self.root / entry)]
        self.assertEqual(subprocess.run(command, cwd=self.root, capture_output=True).returncode, 0)
        self.write("tests/pathlib.py", 'raise RuntimeError("candidate-import-shadow")\n')
        candidate = self.commit()
        result = subprocess.run(command, cwd=self.root, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("candidate-import-shadow", result.stderr)
        self.assertEqual(parent[entry], candidate[entry])
        self.assert_requires_execution(registry, name, parent, candidate)

    @unittest.skipUnless(shutil.which("node"), "Node is required for package ancestry behavior")
    def test_added_ancestor_package_type_invalidates_unchanged_node_entrypoint(self):
        name = "server-console-behavior"
        for package in ("package.json", "server-console/package.json", "server-console/test/package.json"):
            with self.subTest(package=package):
                registry = self.prepare_suite(name)
                entry = "server-console/test/open-url.test.js"
                self.write(entry, 'require("node:assert/strict").equal(1, 1);\n')
                for candidate_package in ("package.json", "server-console/package.json", "server-console/test/package.json"):
                    (self.root / candidate_package).unlink(missing_ok=True)
                parent = self.commit()
                command = ["node", str(self.root / entry)]
                self.assertEqual(subprocess.run(command, cwd=self.root, capture_output=True).returncode, 0)
                self.write(package, json.dumps({"type": "module"}))
                candidate = self.commit()
                result = subprocess.run(command, cwd=self.root, text=True, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("require is not defined", result.stderr)
                self.assertEqual(parent[entry], candidate[entry])
                self.assert_requires_execution(registry, name, parent, candidate)

    def test_importable_native_and_python_metadata_changes_invalidate_proof(self):
        name = "python-test-runner"
        registry = self.prepare_suite(name)
        parent = self.commit()
        for path in ("tests/unknown.py", "tests/cache/unknown.pyc", "tests/unknown.pyo",
                     "tests/unknown.so", "tests/unknown.pyd", "tests/unknown.pth"):
            with self.subTest(path=path):
                self.write(path, "changed module-resolution input\n")
                candidate = self.commit()
                self.assert_requires_execution(registry, name, parent, candidate)
                (self.root / path).unlink()

    def test_native_include_search_roots_cannot_hide_new_system_header_shadows(self):
        # These unchanged harnesses search candidate -I roots before system/Qt
        # headers. Until positive AND negative header resolution is bound, the
        # full repository is their necessary conservative input closure.
        cases = (
            ("lod-preferences", "QCoreApplication"),
            ("web-entity-visibility", "QCoreApplication"),
            ("recorded-voice-native", "atomic"),
            ("performance-contracts", "atomic"),
            ("goto-dialog-script", "interface/src/scripting/QObject"),
        )
        for name, shadow in cases:
            with self.subTest(suite=name, shadow=shadow):
                registry = self.prepare_suite(name, expected_kind="repository")
                (self.root / shadow).unlink(missing_ok=True)
                parent = self.commit()
                entrypoint = registry["suites"][name]["command"][1]
                self.write(shadow, '#error candidate header search resolution changed\n')
                candidate = self.commit()
                self.assertEqual(parent[entrypoint], candidate[entrypoint])
                self.assertNotIn(shadow, parent)
                self.assertIn(shadow, candidate)
                self.assert_requires_execution(registry, name, parent, candidate)
                (self.root / shadow).unlink()


class ReviewedImportInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = INPUTS.load_registry(ROOT / ".github/test-suites.json")
        # Source reviews can legitimately become stale, or a future checkout
        # can contain aliases that disable evidence entirely. Test policy
        # behavior with immutable regular-file fixtures, not a requirement that
        # every future repository tree remains eligible for this optimization.
        cls.tree = {path: {"mode": "100644", "type": "blob", "sha": "f" * 40}
                    for suite in cls.registry["suites"].values() for path in suite["closure"]["required"]}

    def fingerprint(self, name, tree):
        return INPUTS.suite_fingerprint(self.registry, name, tree, ENVIRONMENT)

    def test_unreviewed_suites_keep_global_python_controls(self):
        candidate = self.tree | {"android/phone/tools/unrelated-helper.py": {
            "mode": "100644", "type": "blob", "sha": "a" * 40}}
        for name, suite in self.registry["suites"].items():
            if "python_imports" in suite:
                continue
            with self.subTest(suite=name):
                self.assertNotEqual(self.fingerprint(name, self.tree), self.fingerprint(name, candidate))

    def test_stale_review_metadata_remains_valid_with_repository_fallback(self):
        registry = deepcopy(self.registry)
        name = "documentation-contracts"
        registry["suites"][name]["python_imports"]["reviewed"] = "sha256:" + "0" * 64
        parent = INPUTS.suite_fingerprint(registry, name, self.tree, ENVIRONMENT)
        candidate = self.tree | {"outside/data.txt": {"mode": "100644", "type": "blob", "sha": "a" * 40}}
        # Stale optimization metadata is supported, not a CI failure requiring
        # every future Python change to bless a new review digest.
        self.assertNotEqual(parent, INPUTS.suite_fingerprint(registry, name, candidate, ENVIRONMENT))

    def test_historical_or_changed_import_graph_uses_repository_data_closure(self):
        for name, suite in self.registry["suites"].items():
            if "python_imports" not in suite:
                continue
            with self.subTest(suite=name):
                parent = deepcopy(self.tree)
                # A historical child may contain a matching parent/candidate
                # driver that imports outside the current reviewed graph.
                parent[suite["command"][1]]["sha"] = "b" * 40
                candidate = parent | {"unreviewed/data.txt": {
                    "mode": "100644", "type": "blob", "sha": "c" * 40}}
                self.assertNotEqual(self.fingerprint(name, parent), self.fingerprint(name, candidate))

    def test_ancestor_node_package_controls_remain_global_after_python_review(self):
        name = "embedded-web-qml"
        for path in ("package.json", "tests/package.json", "tests/device/contracts/web/package.json"):
            with self.subTest(path=path):
                candidate = self.tree | {path: {"mode": "100644", "type": "blob", "sha": "d" * 40}}
                self.assertNotEqual(self.fingerprint(name, self.tree), self.fingerprint(name, candidate))

    def test_invalid_review_metadata_cannot_silently_narrow_inputs(self):
        for value in ({}, {"roots": [], "reviewed": "sha256:" + "a" * 64},
                      {"roots": ["tests/**"], "reviewed": "sha256:" + "a" * 64},
                      {"roots": ["../tests"], "reviewed": "sha256:" + "a" * 64},
                      {"roots": ["tests"], "reviewed": "unknown"},
                      {"roots": ["outside"], "reviewed": "sha256:" + "a" * 64}):
            registry = deepcopy(self.registry)
            registry["suites"]["documentation-contracts"]["python_imports"] = value
            with self.subTest(value=value), self.assertRaises(INPUTS.InputError):
                INPUTS.suite_fingerprint(registry, "documentation-contracts", self.tree, ENVIRONMENT)

    def test_nonstandard_python_entrypoint_cannot_escape_reviewed_module_inventory(self):
        registry = deepcopy(self.registry)
        definition = registry["suites"]["documentation-contracts"]
        path = "tests/extensionless-driver"
        definition["command"] = ["python", path]
        definition["closure"]["inputs"].append(path)
        definition["closure"]["required"].append(path)
        tree = self.tree | {path: {"mode": "100644", "type": "blob", "sha": "a" * 40}}
        # Such an entrypoint is executable Python but is not part of the
        # reviewed .py module inventory. It needs a separate source review model.
        with self.assertRaises(INPUTS.InputError):
            INPUTS.suite_fingerprint(registry, "documentation-contracts", tree, ENVIRONMENT)


class ReviewedImportGitTests(GitImportFixture, unittest.TestCase):
    NAME = "embedded-web-qml"
    DIRECTORY = "tests/device/contracts/web"
    ENTRY = DIRECTORY + "/test_embedded_web_qml.py"

    def prepare_review(self, source, files=None):
        registry = self.prepare_suite(self.NAME)
        self.write(self.ENTRY, source)
        for path, content in (files or {}).items():
            self.write(self.DIRECTORY + "/" + path, content)
        parent = self.commit()
        imports = registry["suites"][self.NAME]["python_imports"]
        imports["reviewed"] = INPUTS.python_import_digest(parent, imports["roots"])
        return registry, parent

    def run_entry(self):
        return subprocess.run([sys.executable, str(self.root / self.ENTRY)], cwd=self.root,
                              text=True, capture_output=True)

    def assert_unreviewed_graph_binds_external_data(self, registry, parent):
        path = self.root / "outside/new-import-data.txt"
        previous = path.read_text() if path.exists() else ""
        self.write("outside/new-import-data.txt", previous + "read by an unreviewed module\n")
        self.assert_requires_execution(registry, self.NAME, parent, self.commit())

    def test_unrelated_android_helper_reuses_immutable_reviewed_fixture_proof(self):
        registry, parent = self.prepare_review("import pathlib\nprint(pathlib.Path)\n")
        fingerprint = INPUTS.suite_fingerprint(registry, self.NAME, parent, ENVIRONMENT)
        self.write("android/phone/tools/unrelated-helper.py", "print('unrelated helper')\n")
        candidate = self.commit()
        self.assertEqual(fingerprint, INPUTS.suite_fingerprint(registry, self.NAME, candidate, ENVIRONMENT))
        proof = {self.NAME: {"status": "passed", "fingerprint": fingerprint}}
        self.assertEqual(INPUTS.plan_reuse(registry, parent, candidate, proof, ENVIRONMENT, ENVIRONMENT)["reused"], [self.NAME])

    def test_new_regular_package_shadows_stdlib_and_cannot_establish_narrow_proof(self):
        registry, parent = self.prepare_review("import pathlib\nprint(pathlib.Path)\n")
        self.assertEqual(self.run_entry().returncode, 0)
        self.write(self.DIRECTORY + "/pathlib/__init__.py", 'raise RuntimeError("new-package-shadow")\n')
        candidate = self.commit()
        result = self.run_entry()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("new-package-shadow", result.stderr)
        self.assertEqual(parent[self.ENTRY], candidate[self.ENTRY])
        self.assert_requires_execution(registry, self.NAME, parent, candidate)
        self.assert_unreviewed_graph_binds_external_data(registry, candidate)

    def test_namespace_package_changes_are_inputs(self):
        registry, parent = self.prepare_review("from ambient_ns import helper\nprint(helper.VALUE)\n",
                                               {"ambient_ns/helper.py": "VALUE = 42\n"})
        self.assertEqual(self.run_entry().returncode, 0)
        self.write(self.DIRECTORY + "/ambient_ns/__init__.py", 'raise RuntimeError("namespace-changed")\n')
        candidate = self.commit()
        self.assertIn("namespace-changed", self.run_entry().stderr)
        self.assert_requires_execution(registry, self.NAME, parent, candidate)
        self.assert_unreviewed_graph_binds_external_data(registry, candidate)

    def test_changed_driver_explicit_import_root_keeps_transitive_external_data(self):
        registry, parent = self.prepare_review("print('reviewed driver')\n")
        self.write(self.ENTRY, "import sys\nsys.path.insert(0, 'unowned')\nimport helper\nprint(helper.VALUE)\n")
        self.write("unowned/helper.py", "from pathlib import Path\nVALUE = Path('unowned/config.txt').read_text()\n")
        self.write("unowned/config.txt", "first external input\n")
        historical = self.commit()
        self.assert_requires_execution(registry, self.NAME, parent, historical)
        self.assertEqual(self.run_entry().stdout.strip(), "first external input")
        self.write("unowned/config.txt", "changed external input\n")
        candidate = self.commit()
        self.assertEqual(historical[self.ENTRY], candidate[self.ENTRY])
        self.assertEqual(self.run_entry().stdout.strip(), "changed external input")
        self.assert_requires_execution(registry, self.NAME, historical, candidate)

    def test_sourceless_bytecode_and_native_extension_change_actual_resolution(self):
        for suffix in (".pyc", ".so"):
            with self.subTest(suffix=suffix):
                for path in (self.root / self.DIRECTORY).glob("pathlib.*"):
                    path.unlink()
                registry, parent = self.prepare_review("import pathlib\nprint(pathlib.Path)\n")
                self.assertEqual(self.run_entry().returncode, 0)
                path = self.root / self.DIRECTORY / ("pathlib" + suffix)
                if suffix == ".pyc":
                    source = self.root / "compile-source.py"
                    source.write_text('raise RuntimeError("sourceless-shadow")\n', encoding="utf-8")
                    py_compile.compile(str(source), cfile=str(path), doraise=True)
                    source.unlink()
                else:
                    path.write_bytes(b"invalid native module: actual import must fail")
                self.git("add", "--force", path.relative_to(self.root).as_posix())
                candidate = self.commit()
                self.assertNotEqual(self.run_entry().returncode, 0)
                self.assert_requires_execution(registry, self.NAME, parent, candidate)
                self.assert_unreviewed_graph_binds_external_data(registry, candidate)

    def test_imported_helper_deletion_rename_and_mode_change_invalidate_proof(self):
        registry, parent = self.prepare_review("from helper import VALUE\nprint(VALUE)\n", {"helper.py": "VALUE = 42\n"})
        revision = self.git("rev-parse", "HEAD")
        helper = self.root / self.DIRECTORY / "helper.py"
        for change in ("delete", "rename", "mode"):
            with self.subTest(change=change):
                self.git("reset", "--hard", revision)
                self.git("clean", "-fdx")
                if change == "delete":
                    helper.unlink()
                elif change == "rename":
                    helper.rename(helper.with_name("renamed.py"))
                else:
                    helper.chmod(0o755)
                candidate = self.commit()
                self.assertEqual(parent[self.ENTRY], candidate[self.ENTRY])
                self.assert_requires_execution(registry, self.NAME, parent, candidate)
                self.assert_unreviewed_graph_binds_external_data(registry, candidate)

    def test_symlink_or_gitlink_import_directory_cannot_hide_external_modules(self):
        registry, parent = self.prepare_review("import pathlib\n")
        fingerprint = INPUTS.suite_fingerprint(registry, self.NAME, parent, ENVIRONMENT)
        proof = {self.NAME: {"status": "passed", "fingerprint": fingerprint}}
        for kind in ("symlink", "gitlink"):
            with self.subTest(kind=kind):
                if kind == "symlink":
                    (self.root / self.DIRECTORY / "linked_package").symlink_to("../../../../../outside")
                    candidate = self.commit()
                    (self.root / self.DIRECTORY / "linked_package").unlink()
                else:
                    self.git("add", "-A")
                    revision = self.git("rev-parse", "HEAD")
                    self.git("update-index", "--add", "--cacheinfo", "160000," + revision + "," + self.DIRECTORY + "/vendor")
                    self.git("commit", "-qm", "Record unproven package gitlink")
                    candidate = INPUTS.full_tree(self.root)
                with self.assertRaises(INPUTS.InputError):
                    INPUTS.suite_fingerprint(registry, self.NAME, candidate, ENVIRONMENT)
                self.assertEqual(INPUTS.plan_reuse(registry, parent, candidate, proof, ENVIRONMENT, ENVIRONMENT)["reused"], [])

    def test_sparse_checkout_has_same_inventory_and_fingerprint_as_full_tree(self):
        registry, parent = self.prepare_review("import pathlib\n")
        self.write(".github/fixture.json", "{}\n")
        parent = self.commit()
        with tempfile.TemporaryDirectory(prefix="overte-import-sparse-") as temporary:
            sparse = Path(temporary) / "candidate"
            subprocess.run(["git", "clone", "--quiet", "--no-checkout", str(self.root), str(sparse)],
                           check=True, capture_output=True)
            for command in (("sparse-checkout", "init", "--cone"), ("sparse-checkout", "set", ".github"),
                            ("checkout", "--quiet", "HEAD")):
                subprocess.run(["git", *command], cwd=sparse, check=True, capture_output=True)
            self.assertFalse((sparse / self.ENTRY).exists())
            tree = INPUTS.full_tree(sparse)
            self.assertEqual(tree, parent)
            self.assertEqual(INPUTS.suite_fingerprint(registry, self.NAME, parent, ENVIRONMENT),
                             INPUTS.suite_fingerprint(registry, self.NAME, tree, ENVIRONMENT))


if __name__ == "__main__":
    unittest.main()
