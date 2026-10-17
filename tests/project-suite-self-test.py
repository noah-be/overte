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
        self.assertNotIn("shared-script-behavior", result.stdout)
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
        self.assertEqual(set(host) - set(quick), {
            "device-control-plane-full", "safe-landing-lifecycle",
            "embedded-web-policy", "embedded-web-qml", "account-auth-dispatch",
            "web-entity-visibility", "places-native-qml",
            "lod-preferences",
            "goto-dialog-script",
            "recorded-voice-native", "recorded-voice-qml", "snapshot-native", "snapshot-qml",
            "document-tree-native", "obj-material-native", "shared-script-behavior",
        })
        self.assertEqual(set(native), set(quick) | {"native-ctest", "shared-script-behavior"})
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
                                # Publish readiness only after complete identity
                                # bytes exist. exists() must never expose an
                                # empty file while the JSON writer is running.
                                marker = pathlib.Path(os.environ['CANCELLATION_TEST_MARKER'])
                                pending = marker.with_name(marker.name + '.pending')
                                pending.write_text(json.dumps([os.getpid(), os.getppid(), *children]))
                                pending.replace(marker)
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
                                             f"runner left an owned process behind: {pid}; output: {output}")
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

    @unittest.skipUnless(sys.platform == "linux", "forced descendant cleanup requires Linux")
    def test_forced_scheduler_exit_reaps_detached_children(self):
        # Stop the scheduler so cooperative cleanup is impossible. Its detached
        # child retains stdout: killing only the scheduler also leaves communicate
        # blocked. Exercise both real outer command owners without changing grace.
        blocked = (
            "import json,os,pathlib,signal,subprocess,sys,time; "
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],"
            "start_new_session=True); "
            "pathlib.Path(sys.argv[1]).write_text(json.dumps([os.getpid(),child.pid])); "
            "os.kill(os.getpid(),signal.SIGSTOP)"
        )
        for entrypoint in (RUNNER, RUNNER.parent / "device/run_control_plane_tests.py"):
            with self.subTest(entrypoint=entrypoint.name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                marker = root / "processes.json"
                driver = root / "driver.py"
                driver.write_text(textwrap.dedent(f"""
                    import importlib.util, os, signal, subprocess, sys
                    spec = importlib.util.spec_from_file_location('outer', {str(entrypoint)!r})
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = module
                    spec.loader.exec_module(module)
                    cancelled = []
                    signal.signal(signal.SIGTERM, lambda signum, frame: cancelled.append(signum))
                    code, output, message = module.run_command(
                        [sys.executable, '-c', {blocked!r}, {str(marker)!r}], 30, cancelled)
                    assert message == 'interrupted by signal 15', message
                    raise SystemExit(code)
                """))
                process = subprocess.Popen([sys.executable, str(driver)], text=True,
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           start_new_session=True)
                owned = []
                try:
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        if marker.exists():
                            try:
                                owned = json.loads(marker.read_text())
                            except json.JSONDecodeError:
                                continue
                            state = Path(f"/proc/{owned[0]}/stat").read_text().split(") ", 1)[1].split()[0]
                            if state == "T":
                                break
                        time.sleep(0.01)
                    else:
                        self.fail('fixture scheduler did not stop')
                    process.send_signal(signal.SIGTERM)
                    output, _ = process.communicate(timeout=8)
                    self.assertEqual(process.returncode, 128 + signal.SIGTERM, output)
                    for pid in owned:
                        self.assertFalse(Path(f"/proc/{pid}").exists(),
                                         f"forced cleanup left process {pid}: {output}")
                finally:
                    for pid in [*owned, process.pid]:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    process.communicate(timeout=5)

    @unittest.skipUnless(sys.platform == "linux", "Linux process ownership prerequisites")
    def test_command_owner_refuses_foreign_children_or_threads_before_launch(self):
        for entrypoint in (RUNNER, RUNNER.parent / "device/run_control_plane_tests.py"):
            for occupied in ("child", "thread"):
                with self.subTest(entrypoint=entrypoint.name, occupied=occupied), \
                        tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    marker = root / "must-not-launch"
                    driver = root / "driver.py"
                    canary = f"from pathlib import Path; Path({str(marker)!r}).touch()"
                    driver.write_text(textwrap.dedent(f"""
                        import ctypes, importlib.util, subprocess, sys, threading, unittest
                        from pathlib import Path
                        spec = importlib.util.spec_from_file_location('outer', {str(entrypoint)!r})
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[spec.name] = module
                        spec.loader.exec_module(module)
                        child = None
                        thread = None
                        event = threading.Event()
                        libc = ctypes.CDLL(None)
                        before = ctypes.c_int()
                        assert libc.prctl(37, ctypes.byref(before), 0, 0, 0) == 0
                        if {occupied!r} == 'child':
                            child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        else:
                            thread = threading.Thread(target=event.wait)
                            thread.start()
                        try:
                            with unittest.TestCase().assertRaisesRegex(
                                    RuntimeError, 'child-free single-threaded process'):
                                module.run_command([sys.executable, '-c', {canary!r}], 5, [])
                            assert not Path({str(marker)!r}).exists(), 'refused command was launched'
                            after = ctypes.c_int()
                            assert libc.prctl(37, ctypes.byref(after), 0, 0, 0) == 0
                            assert before.value == after.value, 'refusal changed subreaper ownership'
                            if child is not None:
                                assert child.poll() is None, 'refusal killed the foreign child'
                            if thread is not None:
                                assert thread.is_alive(), 'refusal interfered with the foreign thread'
                        finally:
                            if child is not None:
                                child.kill()
                                child.wait(timeout=2)
                            event.set()
                            if thread is not None:
                                thread.join(timeout=2)
                    """))
                    result = subprocess.run([sys.executable, str(driver)], capture_output=True,
                                            text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertFalse(marker.exists())

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
            shutil.copyfile(RUNNER.parent / "device/run_artifact_identity.py",
                            root / "tests/device/run_artifact_identity.py")
            (root / "provenance").mkdir()
            (root / "tools/sbom").mkdir(parents=True)
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


class ArtifactIdentityConfinementTests(unittest.TestCase):
    def command(self):
        spec = importlib.util.spec_from_file_location(
            "artifact_control_plane", RUNNER.parent / "device/run_control_plane_tests.py")
        control = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(control)
        selected = [command for name, command, _ in control.commands("full")
                    if name == "artifact-identity"]
        self.assertEqual(len(selected), 1)
        return selected[0]

    @contextlib.contextmanager
    def fixture(self, body):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "repository"
            directory = root / "tests/device/schema/artifact-identity"
            directory.mkdir(parents=True)
            for relative in ("provenance", "tools/sbom", "ios/ci", ".git/objects"):
                (root / relative).mkdir(parents=True)
            shutil.copyfile(RUNNER.with_name("run-unittest-suite.py"),
                            root / "tests/run-unittest-suite.py")
            confined = RUNNER.parent / "device/run_artifact_identity.py"
            if confined.exists():
                shutil.copyfile(confined, root / "tests/device/run_artifact_identity.py")
            secret = root / "ios/ci/qt-checkpoint-artifact.py"
            secret.write_text("private-cache-byte-canary\n")
            (root / ".git/objects/source-canary").write_text("private-cache-byte-canary\n")
            (directory / "test_boundary.py").write_text(textwrap.dedent(body))
            yield parent, root

    def execute(self, root, command=None, environment=None):
        return subprocess.run(command or self.command(), cwd=root, capture_output=True,
                              text=True, timeout=30, env=environment)

    def artifact_module(self):
        spec = importlib.util.spec_from_file_location("artifact_stat_boundary",
            RUNNER.parent / "device/run_artifact_identity.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_source_read_accepts_only_atime_movement(self):
        module = self.artifact_module()
        real_fstat = os.fstat
        observed = []

        class AtimeOnly:
            def __init__(self, value): self.value = value
            def __getattr__(self, name):
                value = getattr(self.value, name)
                return value + (1 if name == 'st_atime' else 1_000_000_000
                                if name == 'st_atime_ns' else 0)
            def __eq__(self, other):
                # Match the complete-stat inequality caused by a real read's
                # access-time change; no content or stable field is changed.
                return False

        def accessed(descriptor):
            value = real_fstat(descriptor)
            view = AtimeOnly(value)
            for name in ('st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_uid',
                         'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns'):
                self.assertEqual(getattr(view, name), getattr(value, name))
            self.assertNotEqual(view.st_atime_ns, value.st_atime_ns)
            observed.append(value)
            return view

        with self.fixture('') as (_, root):
            with patch.object(module.os, 'fstat', side_effect=accessed):
                entries = module.source_files(root)
            self.assertTrue(entries)
            self.assertTrue(observed)

    def test_source_read_rejects_actual_private_content_mutation(self):
        module = self.artifact_module()
        real_fstat = os.fstat
        with self.fixture('') as (_, root):
            target = root / 'provenance/actual_reader.py'
            target.write_bytes(b'ordinary private source\n')
            before = target.stat()
            reads = []

            def mutate_after_read(descriptor):
                value = real_fstat(descriptor)
                if (value.st_dev, value.st_ino) == (before.st_dev, before.st_ino):
                    reads.append(value)
                    if len(reads) == 2:
                        target.write_bytes(b'actual changed private source and size\n')
                        value = real_fstat(descriptor)
                return value

            with patch.object(module.os, 'fstat', side_effect=mutate_after_read):
                with self.assertRaises(ValueError): module.source_files(root)
            self.assertEqual(len(reads), 2)
            self.assertEqual(target.read_bytes(), b'actual changed private source and size\n')

    def test_full_device_parent_and_only_artifact_child_have_fixed_startup(self):
        spec = importlib.util.spec_from_file_location("artifact_project_registry", RUNNER)
        registry = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {spec.name: registry}):
            spec.loader.exec_module(registry)
        suite = next(item for item in registry.SUITES if item.name == "device-control-plane-full")
        self.assertEqual(suite.command[:8], (sys.executable, "-I", "-S", "-B",
            "tests/device/run_control_plane_tests.py", "--profile", "full", "--require-qml"))
        self.assertEqual(self.command(), [sys.executable, "-I", "-S", "-B",
                                         "tests/device/run_artifact_identity.py"])
        spec = importlib.util.spec_from_file_location("artifact_other_children",
            RUNNER.parent / "device/run_control_plane_tests.py")
        control = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(control)
        commands = {name: command for name, command, _ in control.commands("full")}
        self.assertEqual(commands["python-self-tests"][:3],
            [sys.executable, "tests/run-unittest-suite.py", "tests/device/self_tests"])

    def test_real_artifact_child_cannot_read_cache_git_or_outer_source_alias(self):
        body = """
            from pathlib import Path
            import os, unittest
            class Boundary(unittest.TestCase):
                def test_real_kernel_view(self):
                    for path in ('/work/ios/ci/qt-checkpoint-artifact.py',
                                 '/work/.git/objects/source-canary',
                                 '/proc/self/root/work/ios/ci/qt-checkpoint-artifact.py',
                                 '/overte-policy/tools/test-evidence/runtime.py',
                                 os.environ.get('OVERTE_OUTER_SOURCE_CANARY', '')):
                        if path:
                            with self.assertRaises(OSError): Path(path).read_bytes()
                    with self.assertRaises(OSError):
                        (Path(__file__).resolve().parents[4] / 'tests/run-unittest-suite.py').write_text('write-canary')
        """
        with self.fixture(body) as (_, root):
            # The actual outer host path is also deliberately supplied in a
            # candidate environment variable. clearenv must discard it, and the
            # full source mount must be absent independently of that discard.
            path = root / "tests/device/schema/artifact-identity/test_boundary.py"
            with path.open("a") as stream:
                stream.write("\n    def test_absolute_outer_alias(self):\n"
                             "        with self.assertRaises(OSError):\n"
                             f"            Path({str(root / 'ios/ci/qt-checkpoint-artifact.py')!r}).read_bytes()\n")
            environment = dict(os.environ, OVERTE_OUTER_SOURCE_CANARY=str(
                root / "ios/ci/qt-checkpoint-artifact.py"))
            result = self.execute(root, environment=environment)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Ran 2 tests", result.stderr)
            self.assertIn("ArtifactIdentity confined-v1", result.stdout)

    def test_cli_uses_no_site_startup_and_real_package_resources_with_312_venv_layout(self):
        body = """
            import os, subprocess, sys, unittest
            from pathlib import Path
            class Boundary(unittest.TestCase):
                def test_cli(self):
                    self.assertTrue(sys.flags.isolated)
                    self.assertTrue(sys.flags.no_site)
                    self.assertNotIn('ARTIFACT_PTH_EXECUTED', os.environ)
                    process = subprocess.run([sys.executable,
                        '/work/tools/sbom/verify-artifact-identity.py'],
                        capture_output=True, text=True, timeout=5)
                    self.assertEqual(process.returncode, 0, process.stderr)
                    self.assertEqual(process.stdout.strip(), 'real-resource')
        """
        with self.fixture(body) as (parent, root):
            environment = parent / "venv"
            (environment / "bin").mkdir(parents=True)
            interpreter = environment / "bin/python"
            interpreter.symlink_to(Path(sys.executable).resolve())
            (environment / "pyvenv.cfg").write_text(
                f"home = {Path(sys.base_prefix) / 'bin'}\ninclude-system-site-packages = false\n")
            # Construct the layout directly; do not run pip, site or a private
            # environment installer. This covers -S's pre-3.14 prefix behavior.
            version = f"python{sys.version_info.major}.{sys.version_info.minor}"
            for library in ("lib", "lib64"):
                packages = environment / library / version / "site-packages"
                package = packages / "artifact_fixture_resource"
                package.mkdir(parents=True)
                (package / "__init__.py").write_text("")
                (package / "payload.txt").write_text("real-resource")
                (package / "source-alias.txt").symlink_to(root / "ios/ci/qt-checkpoint-artifact.py")
                (packages / "must-not-run.pth").write_text(
                    "import os; os.environ['ARTIFACT_PTH_EXECUTED']='true'\n")
                (packages / "sitecustomize.py").write_text(
                    "raise RuntimeError('site startup must not execute')\n")
            (root / "tools/sbom/verify-artifact-identity.py").write_text(
                "import os, sys\nfrom importlib.resources import files\n"
                "assert sys.flags.isolated and sys.flags.no_site\n"
                "assert 'ARTIFACT_PTH_EXECUTED' not in os.environ\n"
                "try: files('artifact_fixture_resource').joinpath('source-alias.txt').read_bytes()\n"
                "except OSError: pass\n"
                "else: raise AssertionError('prepared resource escaped to candidate source')\n"
                "print(files('artifact_fixture_resource').joinpath('payload.txt').read_text())\n")
            command = self.command()
            command[0] = str(interpreter)
            result = self.execute(root, command=command)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Ran 1 test", result.stderr)

    def test_source_symlink_cannot_expose_cache_bytes_or_start_a_workload(self):
        body = """
            import unittest
            class Boundary(unittest.TestCase):
                def test_must_not_start(self): self.fail('source-alias-workload-started')
        """
        with self.fixture(body) as (_, root):
            (root / "provenance/source_alias.py").symlink_to(
                root / "ios/ci/qt-checkpoint-artifact.py")
            result = self.execute(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("source-alias-workload-started", result.stdout + result.stderr)
            self.assertIn("confined execution unavailable", result.stderr)

    def test_python_cli_alias_rejects_an_unlisted_script_before_its_body(self):
        body = """
            import subprocess, sys, unittest
            from pathlib import Path
            class Boundary(unittest.TestCase):
                def test_child(self):
                    script = Path(__file__).resolve().parents[4] / 'tools/sbom/unlisted.py'
                    process = subprocess.run([sys.executable, str(script)],
                        capture_output=True, text=True, timeout=5)
                    self.assertNotEqual(process.returncode, 0)
                    self.assertNotIn('unlisted-body-executed', process.stdout + process.stderr)
        """
        with self.fixture(body) as (_, root):
            (root / "tools/sbom/unlisted.py").write_text("print('unlisted-body-executed')\n")
            result = self.execute(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Ran 1 test", result.stderr)


class DevicePythonFailureDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "control_plane_failure_diagnostic", RUNNER.parent / "device/run_control_plane_tests.py")
        self.control = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.control)

    def aggregate(self, names):
        return {"schema": 1, "selected": len(names), "loaded": 0, "ran": 0, "skipped": 0,
                "failed_modules": len(names), "workers": 2,
                "modules": [{"module": name, "selected_ids": [name + ".Case.test_behavior"],
                             "result": None, "exit_code": 1, "error": "not printed"}
                            for name in names]}

    def test_final_module_diagnostic_survives_later_groups_and_preserves_failure_and_junit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "build/test-results/device-self-tests.json"
            names = ["test_first", "test_second"]
            def command(*unused):
                if not report.exists():
                    report.parent.mkdir(parents=True)
                    report.write_text(json.dumps(self.aggregate(names)))
                    return 1, "private traceback must stay out of final diagnostic", "exit code 1"
                return 0, "later group output", ""
            args = SimpleNamespace(profile="full", self_test_jobs=2, timeout_seconds=900,
                                   require_qml=True, junit=root / "device.xml")
            output = io.StringIO()
            with (patch.object(self.control, "REPOSITORY", root),
                  patch.object(self.control, "commands", return_value=[
                      ("python-self-tests", ["fixture"], False), ("later-group", ["fixture"], False)]),
                  patch.object(self.control, "run_command", side_effect=command),
                  contextlib.redirect_stdout(output)):
                result = self.control.run_checks(args, [])
            line = output.getvalue().splitlines()[-1]
            value = json.loads(line)
            self.assertEqual(result, 1)
            self.assertIn('Device control plane failed groups: ["python-self-tests"]', output.getvalue())
            self.assertIn("PASSED  later-group", output.getvalue())
            self.assertEqual(value["modules"], names)
            self.assertEqual((value["failed"], value["omitted"], value["report"]), (2, 0, "ok"))
            self.assertFalse(value["truncated"])
            self.assertLessEqual(len(line.encode("ascii")), 450)
            self.assertIn(line, output.getvalue()[-512:])
            self.assertNotIn("traceback", line)
            xml = ET.parse(args.junit).getroot()
            self.assertEqual((xml.get("tests"), xml.get("failures"), xml.get("skipped")), ("2", "1", "0"))
            self.assertIn("private traceback", xml.find("testcase/failure").text)

    def test_bounded_names_and_unsafe_or_missing_reports_cannot_emit_arbitrary_data(self):
        item = {"message": "timeout after 900s", "durationSeconds": 12.3456}
        cases = ("valid", "no-failed-modules", "serial", "missing", "symlink", "hardlink", "fifo", "oversize",
                 "invalid-json", "nested-json", "bad-shape", "wrong-count", "stale", "parent-symlink")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                report = root / "build/test-results/device-self-tests.json"
                report.parent.mkdir(parents=True)
                started = time.time_ns()
                names = ["test_" + str(index) + "_" + "x" * 60 for index in range(8)]
                report.write_text(json.dumps(self.aggregate(names)))
                if case == "no-failed-modules":
                    value = self.aggregate(names)
                    value["failed_modules"] = 0
                    for row in value["modules"]:
                        row.update(result={"schema": 1, "successful": True}, exit_code=0, error="")
                    report.write_text(json.dumps(value))
                elif case == "serial":
                    started = None
                elif case == "missing":
                    report.unlink()
                elif case == "symlink":
                    private = root / "private.json"
                    report.replace(private)
                    report.symlink_to(private)
                elif case == "hardlink":
                    os.link(report, root / "alias.json")
                elif case == "fifo":
                    report.unlink()
                    os.mkfifo(report)
                elif case == "oversize":
                    with report.open("wb") as stream:
                        stream.truncate(4 * 1024 * 1024 + 1)
                elif case == "invalid-json":
                    report.write_text("private trace is not JSON")
                elif case == "nested-json":
                    report.write_text("[" * 2000 + "0" + "]" * 2000)
                elif case == "bad-shape":
                    report.write_text(json.dumps({"modules": "private trace"}))
                elif case == "wrong-count":
                    value = self.aggregate(names)
                    value["failed_modules"] = 1
                    report.write_text(json.dumps(value))
                elif case == "stale":
                    os.utime(report, ns=(1, 1))
                elif case == "parent-symlink":
                    actual = root / "actual-results"
                    report.parent.rename(actual)
                    (root / "build/test-results").symlink_to(actual, target_is_directory=True)
                with patch.object(self.control, "REPOSITORY", root):
                    line = self.control.python_failure_diagnostic(item, started)
                value = json.loads(line)
                self.assertLessEqual(len(line.encode("ascii")), 450)
                self.assertEqual((value["message"], value["seconds"]), ("timeout", 12.346))
                self.assertNotIn("private", line)
                if case == "valid":
                    self.assertEqual((value["report"], value["failed"], value["omitted"]), ("ok", 8, 4))
                    self.assertEqual(len(value["modules"]), 4)
                    self.assertTrue(value["truncated"])
                    self.assertTrue(all(len(name) <= 48 for name in value["modules"]))
                elif case == "no-failed-modules":
                    self.assertEqual((value["report"], value["failed"], value["omitted"]), ("ok", 0, 0))
                    self.assertEqual(value["modules"], [])
                    self.assertFalse(value["truncated"])
                else:
                    self.assertEqual(value["report"], "unavailable")
                    self.assertIsNone(value["failed"])
                    self.assertIsNone(value["omitted"])
                    self.assertEqual(value["modules"], [])


if __name__ == "__main__":
    unittest.main()
