#!/usr/bin/env python3
"""Black-box regression tests for the project-suite CLI."""

from pathlib import Path
import contextlib
import importlib.util
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import xml.etree.ElementTree as ET


RUNNER = Path(__file__).with_name("run-project-tests.py")


class ProjectSuiteCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(RUNNER), *args], text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_quick_profile_excludes_native_build(self):
        result = self.run_cli("--list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("repository-health", result.stdout)
        self.assertIn("source-layout", result.stdout)
        self.assertIn("shared-script-behavior", result.stdout)
        self.assertIn("device-e2e-contracts", result.stdout)
        self.assertIn("documentation ", result.stdout)
        self.assertIn("repository-checks", result.stdout)
        self.assertIn("native-smoke", result.stdout)
        self.assertNotIn("native-ctest", result.stdout)

    def test_full_profile_includes_native_build(self):
        result = self.run_cli("--list", "--profile", "full")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("native-ctest", result.stdout)
        self.assertIn("documentation ", result.stdout)

    def test_host_profile_preserves_quick_coverage_without_duplicate_device_checks(self):
        spec = importlib.util.spec_from_file_location("project_runner_contract", RUNNER)
        runner = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {spec.name: runner}):
            spec.loader.exec_module(runner)
        platform = runner.Suite("fixture-platform", "quick", (sys.executable, "fixture.py"))
        with patch.object(runner, "SUITES", runner.SUITES + (platform,)):
            def selected(profile):
                return {item.name: item for item in runner.select(SimpleNamespace(
                    profile=profile, suite=[], platform_only=False))}
            quick, host, native = selected("quick"), selected("host"), selected("full")
        self.assertEqual(set(quick) - set(host), {"device-e2e-contracts", "native-smoke"})
        self.assertEqual(set(host) - set(quick), {"device-control-plane-full"})
        self.assertEqual(set(native), set(quick) | {"native-ctest"})
        self.assertIn("fixture-platform", host)
        self.assertIn("--require-qml", host["device-control-plane-full"].command)

        spec = importlib.util.spec_from_file_location(
            "control_plane_coverage", RUNNER.parent / "device/run_control_plane_tests.py")
        control = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(control)
        full = {name: (command, optional) for name, command, optional in control.commands("full")}
        full_python = full["python-self-tests"][0]
        self.assertIn("tests/run-unittest-suite.py", full_python)
        self.assertNotIn("--pattern", full_python, "Full discovery must cover every self-test module")
        full_directory = RUNNER.parent.parent / "tests/device/self_tests"
        full_files = set(full_directory.glob("test_*.py"))
        self.assertTrue(full_files)
        for name, command, optional in control.commands("quick"):
            if "--pattern" in command:
                self.assertIn("tests/device/self_tests", command)
                matched = set(full_directory.glob(command[command.index("--pattern") + 1]))
                self.assertTrue(matched, name)
                self.assertTrue(matched <= full_files, name)
            else:
                self.assertEqual(full[name], (command, optional), name)
        def normalized(command):
            return tuple(str((RUNNER.parent.parent / value).resolve()) if value.endswith(".py")
                         else value for value in command)
        self.assertEqual(normalized(quick["native-smoke"].command),
                         normalized(full["phone-spawn-gate"][0]))

    def test_mandatory_full_host_cli_propagates_failure_and_uses_its_own_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests/device").mkdir(parents=True)
            shutil.copyfile(RUNNER, root / "tests" / RUNNER.name)
            (root / "tests/platform-profile.json").write_text(json.dumps({
                "schema": 1, "platform": "shared", "suites": [],
            }))
            fixture = root / "tests/device/run_control_plane_tests.py"
            fixture.write_text("import json, sys\nfrom pathlib import Path\n"
                               "Path('arguments.json').write_text(json.dumps(sys.argv[1:]))\n"
                               "print('full-host-canary')\nsys.exit(1)\n")
            report = root / "result.xml"
            command = [sys.executable, str(root / "tests" / RUNNER.name),
                       "--suite", "device-control-plane-full", "--timeout", "1",
                       "--host-timeout", "2", "--junit", str(report)]
            failed = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
            self.assertIn("full-host-canary", failed.stderr)
            arguments = json.loads((root / "arguments.json").read_text())
            self.assertIn("--require-qml", arguments)
            self.assertEqual(arguments[arguments.index("--profile") + 1], "full")
            self.assertEqual(arguments[arguments.index("--timeout-seconds") + 1], "2")
            self.assertEqual(ET.parse(report).getroot().get("failures"), "1")
            fixture.write_text("import time\ntime.sleep(10)\n")
            timed_out = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(timed_out.returncode, 1)
            failure = ET.parse(report).find("testcase/failure")
            self.assertEqual(failure.get("message"), "timeout after 2s")

    @unittest.skipUnless(sys.platform == "linux", "parallel worker cleanup requires Linux")
    def test_nested_and_direct_host_cancellation_reaps_all_owned_processes(self):
        # Keep the actual project/control/worker entrypoints. Only replace the
        # selected device checks with a blocking test and a forbidden later step.
        for entrypoint in ("project", "control"):
            for interruption in (signal.SIGTERM, signal.SIGINT, None):
                with self.subTest(entrypoint=entrypoint, interruption=interruption), \
                        tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    (root / "tests/device").mkdir(parents=True)
                    (root / "cases").mkdir()
                    marker, later = root / "pids.json", root / "later-ran"
                    report = root / "result.xml"
                    shutil.copyfile(RUNNER, root / "tests" / RUNNER.name)
                    (root / "tests/platform-profile.json").write_text(json.dumps({
                        "schema": 1, "platform": "shared", "suites": [],
                    }))
                    control = root / "tests/device/run_control_plane_tests.py"
                    control.write_text(
                        "import importlib.util, sys\nfrom pathlib import Path\n"
                        f"spec = importlib.util.spec_from_file_location('control', "
                        f"{str(RUNNER.parent / 'device/run_control_plane_tests.py')!r})\n"
                        "module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)\n"
                        f"module.REPOSITORY = Path({str(root)!r})\n"
                        "module.commands = lambda *args: ["
                        f"('python-self-tests', [sys.executable, {str(RUNNER.with_name('run-unittest-suite.py'))!r}, "
                        f"{str(root / 'cases')!r}, '--jobs', '2'], False), "
                        "('must-not-run', [sys.executable, '-c', "
                        f"{('from pathlib import Path; Path(' + repr(str(later)) + ').touch()')!r}], False)]\n"
                        "raise SystemExit(module.main())\n")
                    (root / "cases/test_process_tree.py").write_text(textwrap.dedent("""
                        import json, os, pathlib, signal, subprocess, sys, time, unittest
                        class ProcessTree(unittest.TestCase):
                            def test_blocked_with_owned_children(self):
                                signal.signal(signal.SIGTERM, signal.SIG_IGN)
                                children = []
                                for detached in (False, True):
                                    child = subprocess.Popen([
                                        sys.executable, '-c',
                                        'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)',
                                    ], start_new_session=detached, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
                                    children.append(child.pid)
                                pathlib.Path(os.environ['CANCELLATION_TEST_MARKER']).write_text(json.dumps(
                                    [os.getpid(), os.getppid(), *children]))
                                time.sleep(60)
                    """))
                    timeout = "1" if interruption is None else "30"
                    command = ([sys.executable, str(root / "tests" / RUNNER.name),
                                "--suite", "device-control-plane-full", "--host-timeout", timeout]
                               if entrypoint == "project" else
                               [sys.executable, str(control), "--profile", "full",
                                "--timeout-seconds", timeout])
                    process = subprocess.Popen(
                        [*command, "--junit", str(report)], cwd=root, text=True,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        start_new_session=True,
                        env={**os.environ, "CANCELLATION_TEST_MARKER": str(marker)})
                    owned = []
                    try:
                        deadline = time.monotonic() + 5
                        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                            time.sleep(0.01)
                        self.assertTrue(marker.exists(), "test worker did not start")
                        owned = json.loads(marker.read_text())
                        if interruption is not None:
                            process.send_signal(interruption)
                        output, _ = process.communicate(timeout=8)
                        self.assertEqual(1 if interruption is None else 128 + interruption,
                                         process.returncode, output)
                        self.assertEqual("1", ET.parse(report).getroot().get("failures"))
                        if interruption is not None:
                            self.assertFalse(later.exists(), "cancelled runner launched another check")
                        for pid in owned:
                            self.assertFalse(Path(f"/proc/{pid}").exists(),
                                             f"runner left an owned process behind: {pid}")
                    finally:
                        for pid in [process.pid, *owned]:
                            try:
                                os.killpg(pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                            try:
                                os.kill(pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        process.communicate(timeout=5)

    def test_coverage_cli_propagates_real_assertion_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "src").mkdir()
            checker = root / "tests/project-coverage-test.py"
            shutil.copyfile(RUNNER.with_name("project-coverage-test.py"), checker)
            area = {"id": "fixture", "roots": ["src"], "automated": [], "native": [],
                    "hardware": ["audio-device-acceptance", "distributed-system-acceptance",
                                 "gpu-driver-acceptance"]}
            matrix = root / "tests/project-coverage.json"
            matrix.write_text(json.dumps({"schema": 1, "areas": [area]}))
            failed = subprocess.run([sys.executable, str(checker)], capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0, failed.stderr)
            self.assertIn("FAILED (failures=1)", failed.stderr)
            area["automated"] = ["fixture-check"]
            matrix.write_text(json.dumps({"schema": 1, "areas": [area]}))
            passed = subprocess.run([sys.executable, str(checker)], capture_output=True, text=True)
            self.assertEqual(passed.returncode, 0, passed.stderr)

    def test_explicit_suite_can_select_native_independently(self):
        result = self.run_cli("--list", "--suite", "native-ctest")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split()[0], "native-ctest")

    def test_device_control_plane_alias_selects_the_device_contract_suite(self):
        result = self.run_cli("--list", "--suite", "device-control-plane")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split()[0], "device-e2e-contracts")

    def test_unknown_suite_and_invalid_timeout_fail(self):
        unknown = self.run_cli("--list", "--suite", "missing")
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("unknown suites", unknown.stderr)
        timeout = self.run_cli("--timeout", "0")
        self.assertEqual(timeout.returncode, 2)
        for value in ("0", "1801"):
            self.assertEqual(self.run_cli("--host-timeout", value).returncode, 2)

    def test_unittest_entrypoint_rejects_empty_and_failing_selections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command = [sys.executable, str(RUNNER.with_name("run-unittest-suite.py")), str(root)]
            empty = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(empty.returncode, 0)
            self.assertIn("no test cases", empty.stderr)
            fixture = root / "test_regression.py"
            fixture.write_text("import unittest\nclass Regression(unittest.TestCase):\n"
                               "    def test_behavior(self):\n        self.fail('regression-canary')\n")
            failed = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("regression-canary", failed.stderr)
            fixture.write_text("import unittest\nclass Regression(unittest.TestCase):\n"
                               "    def test_behavior(self):\n        self.assertEqual(1 + 1, 2)\n")
            passed = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertIn("Ran 1 test", passed.stderr)

    def test_unittest_entrypoint_keeps_repository_root_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            helpers = root / "shared_helpers"
            helpers.mkdir()
            (helpers / "value.py").write_text("VALUE = 42\n")
            suite = root / "host-tests"
            suite.mkdir()
            (suite / "test_import.py").write_text(
                "import unittest\nfrom shared_helpers.value import VALUE\n"
                "class Regression(unittest.TestCase):\n"
                "    def test_import(self):\n        self.assertEqual(VALUE, 42)\n")
            result = subprocess.run([
                sys.executable, str(RUNNER.with_name("run-unittest-suite.py")), str(suite),
            ], cwd=root, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Ran 1 test", result.stderr)

    def test_new_host_regressions_fail_the_actual_registered_project_suite(self):
        # Execute the real registration/runner in a tiny workspace. Each selected
        # test deliberately fails, proving the command and JUnit cannot stay green.
        cases = {
            "device-result-schema": "tests/device/schema/test_regression.py",
            "device-jenkins": "tests/device/jenkins/test_regression.py",
            "desktop-input-protocol": "tests/device/adapters/desktop_oculix/test_wayland_libei_client.py",
            "performance-contracts": "tests/performance/schema/test_regression.py",
            "server-console-behavior": "server-console/test/open-url.test.js",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            for filename in (RUNNER.name, "run-unittest-suite.py"):
                shutil.copyfile(RUNNER.with_name(filename), root / "tests" / filename)
            (root / "tests/platform-profile.json").write_text(json.dumps({
                "schema": 1, "platform": "shared", "suites": [],
            }))
            for filename in ("open-url.test.js", "file-tail.test.js", "notification-compat.test.js"):
                path = root / "server-console/test" / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("require('node:test')('fixture', () => {});\n")
            for name, relative in cases.items():
                with self.subTest(suite=name):
                    fixture = root / relative
                    fixture.parent.mkdir(parents=True, exist_ok=True)
                    if fixture.suffix == ".py":
                        fixture.write_text("import unittest\nclass Regression(unittest.TestCase):\n"
                                           "    def test_behavior(self):\n        self.fail('regression-canary')\n")
                    else:
                        fixture.write_text("require('node:test')('fixture', () => {\n"
                                           "    throw new Error('regression-canary');\n});\n")
                    report = root / "result.xml"
                    result = subprocess.run([
                        sys.executable, str(root / "tests" / RUNNER.name), "--suite", name,
                        "--timeout", "10", "--junit", str(report),
                    ], capture_output=True, text=True, timeout=15)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertIn("regression-canary", result.stderr)
                    xml = ET.parse(report).getroot()
                    self.assertEqual(xml.get("tests"), "1")
                    self.assertEqual(xml.get("failures"), "1")
                    self.assertEqual(xml.find("testcase").get("name"), name)

    def test_full_host_gate_reports_artifact_assertions_and_empty_discovery_as_failures(self):
        spec = importlib.util.spec_from_file_location(
            "control_plane", RUNNER.parent / "device/run_control_plane_tests.py")
        control_plane = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(control_plane)
        # Use the real registered command and full runner, restricting unrelated
        # expensive checks so the regression needs neither Qt nor SPDX packages.
        selected = [item for item in control_plane.commands("full") if item[0] == "artifact-identity"]
        self.assertEqual(len(selected), 1)
        self.assertFalse(selected[0][2], "Artifact validation is mandatory, not an optional QML check")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            test_directory = root / "tests/device/schema/artifact-identity"
            test_directory.mkdir(parents=True)
            shutil.copyfile(RUNNER.with_name("run-unittest-suite.py"), root / "tests/run-unittest-suite.py")
            fixture = test_directory / "test_regression.py"
            fixture.write_text("import unittest\nclass Regression(unittest.TestCase):\n"
                               "    def test_behavior(self):\n        self.fail('artifact-canary')\n")
            for failure in ("artifact-canary", "no test cases"):
                with self.subTest(failure=failure):
                    if failure == "no test cases":
                        fixture.unlink()
                    report = root / "result.xml"
                    with patch.object(control_plane, "REPOSITORY", root), \
                            patch.object(control_plane, "commands", return_value=selected), \
                            patch.object(sys, "argv", ["control-plane", "--profile", "full",
                                                      "--junit", str(report)]), \
                            contextlib.redirect_stdout(io.StringIO()):
                        result = control_plane.main()
                    self.assertEqual(result, 1)
                    xml = ET.parse(report).getroot()
                    self.assertEqual(xml.get("failures"), "1")
                    self.assertEqual(xml.get("skipped"), "0")
                    self.assertIn(failure, xml.find("testcase/failure").text)


if __name__ == "__main__":
    unittest.main()
