#!/usr/bin/env python3
"""Real-registry regressions for execution inventory and import-resolution inputs."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
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


class ImportResolutionIdentityTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
