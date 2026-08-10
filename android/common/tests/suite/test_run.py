import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import time
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

import run


class SuiteRunnerTest(unittest.TestCase):
    def test_catalog_has_unique_suites_and_known_tier(self):
        fast = run.load_suites(run.DEFAULT_CATALOG, "fast")
        self.assertGreater(len(fast), 0)
        self.assertEqual(len(fast), len({suite["id"] for suite in fast}))

    def test_android_vr_tier_has_one_bounded_integration_gate(self):
        suites = run.load_suites(run.DEFAULT_CATALOG, "android-vr")
        identifiers = {suite["id"] for suite in suites}
        self.assertEqual(identifiers, {
            "shell-syntax-contract",
            "python-syntax-contract",
            "android-project-module-inventory",
            "android-vr-native-policies",
            "android-vr-pico-runtime",
            "phone-robolectric-launcher",
        })
        pico = next(suite for suite in suites
                    if suite["id"] == "android-vr-pico-runtime")
        self.assertEqual(["tests/android-vr-pico-runtime-test.sh"], pico["command"])
        self.assertLessEqual(pico["timeoutSeconds"], 300)
        native = next(suite for suite in suites
                      if suite["id"] == "android-vr-native-policies")
        self.assertEqual(["tests/native/run-native-tests.sh", "android-vr"],
                         native["command"])

    def test_catalog_rejects_unknown_tier(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            catalog.write_text(json.dumps({"schemaVersion": 1, "suites": [{
                "id": "bad", "kind": "jvm", "description": "bad tier",
                "command": ["true"], "tiers": ["typo"]
            }]}))
            with self.assertRaisesRegex(ValueError, "invalid tiers"):
                run.load_suites(catalog, "fast")

    def test_catalog_rejects_invalid_execution_controls(self):
        base = {"schemaVersion": 1, "suites": [{
            "id": "bad", "kind": "jvm", "description": "invalid execution control",
            "command": ["true"], "tiers": ["fast"]
        }]}
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "catalog.json"
            base["suites"][0]["timeoutSeconds"] = 0
            catalog.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid timeoutSeconds"):
                run.load_suites(catalog, "fast")
            base["suites"][0]["timeoutSeconds"] = 10
            base["suites"][0]["optionalWhenToolMissing"] = "yes"
            catalog.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "invalid optionalWhenToolMissing"):
                run.load_suites(catalog, "fast")

    def test_junit_report_records_failure_skip_and_output_safely(self):
        results = [
            {"id": "pass", "kind": "jvm", "status": "passed", "reason": "",
             "returncode": 0, "duration": 0.1, "output": "ok <safe>"},
            {"id": "fail", "kind": "native", "status": "failed", "reason": "",
             "returncode": 3, "duration": 0.2, "output": "bad & bounded\x00control"},
            {"id": "skip", "kind": "qml", "status": "skipped", "reason": "no\x01tool",
             "returncode": 127, "duration": 0.0, "output": ""},
        ]
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.xml"
            run.write_report(results, report, "fast")
            root = ET.parse(report).getroot()
        self.assertEqual("3", root.attrib["tests"])
        self.assertEqual("1", root.attrib["failures"])
        self.assertEqual("1", root.attrib["skipped"])
        self.assertEqual("bad & bounded\ufffdcontrol",
                         root.find("testcase[@name='fail']/failure").text)
        self.assertEqual("no\ufffdtool", root.find("testcase[@name='skip']/skipped").attrib["message"])

    def test_junit_output_is_bounded_and_preserves_head_and_tail(self):
        output = "HEAD" + ("x" * (run.MAX_REPORT_OUTPUT_BYTES * 2)) + "TAIL"
        bounded = run.bounded_report_output(output)
        self.assertLessEqual(len(bounded.encode("utf-8")), run.MAX_REPORT_OUTPUT_BYTES)
        self.assertTrue(bounded.startswith("HEAD"))
        self.assertTrue(bounded.endswith("TAIL"))
        self.assertIn("output truncated", bounded)

    def test_parallel_junit_writers_publish_one_complete_report_without_temp_leaks(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "TEST-parallel.xml"

            def publish(index):
                run.write_report([{
                    "id": f"writer-{index}", "kind": "infrastructure",
                    "status": "passed", "reason": "", "returncode": 0,
                    "duration": 0.01, "output": f"output-{index}",
                }], destination, "fast")

            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(publish, range(32)))

            root = ET.parse(destination).getroot()
            self.assertEqual("1", root.attrib["tests"])
            self.assertRegex(root.find("testcase").attrib["name"], r"^writer-\d+$")
            self.assertEqual([], list(Path(directory).glob("*.tmp")))
            self.assertEqual([], list(Path(directory).glob(".*.tmp")))

    @unittest.skipUnless(os.name == "posix", "process-group cleanup is POSIX-specific")
    def test_timeout_kills_parent_and_term_resistant_child_and_keeps_output(self):
        with tempfile.TemporaryDirectory() as directory:
            child_pid_file = Path(directory) / "child.pid"
            child = (
                "import os,signal,time;"
                f"open({str(child_pid_file)!r},'w').write(str(os.getpid()));"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                "print('child-ready',flush=True);"
                "os.close(1);os.close(2);"
                "time.sleep(60)"
            )
            parent = (
                "import subprocess,sys,time;"
                f"subprocess.Popen([sys.executable,'-c',{child!r}]);"
                "print('parent-ready',flush=True);"
                "time.sleep(60)"
            )
            with self.assertRaises(subprocess.TimeoutExpired) as raised:
                run.run_command([sys.executable, "-c", parent], 1, cwd=Path(directory))
            output = raised.exception.output
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            self.assertIn("parent-ready", output)
            self.assertIn("child-ready", output)
            child_pid = int(child_pid_file.read_text(encoding="utf-8"))
            deadline = time.monotonic() + 3
            while Path(f"/proc/{child_pid}").exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertFalse(Path(f"/proc/{child_pid}").exists(),
                             f"timed-out child process {child_pid} leaked")

    def test_timeout_bytes_are_xml_safe_and_written_atomically(self):
        timeout = subprocess.TimeoutExpired(["fixture"], 1, output=b"partial\x00bytes")
        with tempfile.TemporaryDirectory() as directory:
            root_dir = Path(directory)
            catalog = root_dir / "catalog.json"
            report_dir = root_dir / "reports"
            catalog.write_text(json.dumps({"schemaVersion": 1, "suites": [{
                "id": "timeout", "kind": "infrastructure", "description": "hang",
                "command": ["fixture"], "tiers": ["fast"], "timeoutSeconds": 1,
            }]}), encoding="utf-8")
            argv = ["run.py", "fast", "--catalog", str(catalog),
                    "--report-dir", str(report_dir)]
            with mock.patch("sys.argv", argv), mock.patch.object(
                    run, "run_command", side_effect=timeout):
                self.assertEqual(1, run.main())
            report = report_dir / "TEST-android-fast.xml"
            self.assertFalse(report.with_suffix(".xml.tmp").exists())
            root = ET.parse(report).getroot()
        failure = root.find("testcase[@name='timeout']/failure")
        self.assertIn("partial\ufffdbytes", failure.text)
        self.assertIn("timed out", failure.text)

    def test_qml_suite_declares_missing_tool_as_optional(self):
        qml = next(suite for suite in run.load_suites(run.DEFAULT_CATALOG, "fast")
                   if suite["id"] == "qml-components")
        self.assertTrue(qml["optionalWhenToolMissing"])

    def test_mutation_tiers_publish_distinct_json_reports(self):
        quick = run.load_suites(run.DEFAULT_CATALOG, "mutation")[0]["command"]
        extended = run.load_suites(run.DEFAULT_CATALOG, "mutation-extended")[0]["command"]
        self.assertNotIn("--report", quick)
        self.assertIn("--report", extended)
        self.assertTrue(any(part.endswith("critical-policies-extended.json")
                            for part in extended))

    def test_optional_suite_spawn_error_is_not_misreported_as_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog.json"
            report_dir = root / "reports"
            catalog.write_text(json.dumps({"schemaVersion": 1, "suites": [{
                "id": "optional", "kind": "qml", "description": "fixture",
                "command": ["missing-wrapper"], "tiers": ["fast"],
                "optionalWhenToolMissing": True,
            }]}), encoding="utf-8")
            argv = ["run.py", "fast", "--catalog", str(catalog),
                    "--report-dir", str(report_dir)]
            with mock.patch("sys.argv", argv), mock.patch.object(
                    run, "run_command", side_effect=OSError("not executable")):
                self.assertEqual(1, run.main())
            suite = ET.parse(report_dir / "TEST-android-fast.xml").getroot()
        self.assertEqual("1", suite.attrib["failures"])
        self.assertEqual("0", suite.attrib["skipped"])

    def test_main_gives_each_suite_an_external_temporary_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            android_root = root / "android"
            android_root.mkdir()
            external_temp = root / "external-temp"
            catalog = root / "catalog.json"
            report_dir = root / "reports"
            catalog.write_text(json.dumps({"schemaVersion": 1, "suites": [{
                "id": "fixture", "kind": "infrastructure", "description": "fixture",
                "command": ["fixture"], "tiers": ["fast"],
            }]}), encoding="utf-8")
            observed = {}

            def execute(command, timeout, *, cwd, env):
                temporary = Path(env["TMPDIR"])
                self.assertTrue(temporary.is_dir())
                self.assertTrue(temporary.is_relative_to(external_temp))
                self.assertFalse(temporary.is_relative_to(android_root))
                observed["temporary"] = temporary
                return subprocess.CompletedProcess(command, 0, "ok\n")

            argv = ["run.py", "fast", "--catalog", str(catalog),
                    "--report-dir", str(report_dir)]
            with mock.patch("sys.argv", argv), mock.patch.object(
                    run, "ANDROID_ROOT", android_root), mock.patch.object(
                    run, "SUITE_TEMP_PARENT", external_temp), mock.patch.object(
                    run, "run_command", side_effect=execute), mock.patch.dict(
                    os.environ, {"TMPDIR": "/tmp"}):
                self.assertEqual(0, run.main())

            self.assertFalse(observed["temporary"].exists())

    def test_incomplete_report_replaces_stale_success_before_first_suite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog.json"
            report_dir = root / "reports"
            report = report_dir / "TEST-android-fast.xml"
            catalog.write_text(json.dumps({"schemaVersion": 1, "suites": [{
                "id": "fixture", "kind": "infrastructure", "description": "fixture",
                "command": ["fixture"], "tiers": ["fast"],
            }]}), encoding="utf-8")
            report_dir.mkdir()
            report.write_text('<testsuite tests="1" failures="0"/>', encoding="utf-8")

            def execute(command, timeout, *, cwd, env):
                pending = ET.parse(report).getroot()
                self.assertEqual("1", pending.attrib["failures"])
                failure = pending.find("testcase[@name='suite-run-incomplete']/failure")
                self.assertIsNotNone(failure)
                self.assertIn("0 of 1 suites completed", failure.text)
                return subprocess.CompletedProcess(command, 0, "ok\n")

            argv = ["run.py", "fast", "--catalog", str(catalog),
                    "--report-dir", str(report_dir)]
            with mock.patch("sys.argv", argv), mock.patch.object(
                    run, "run_command", side_effect=execute):
                self.assertEqual(0, run.main())
            final = ET.parse(report).getroot()
            self.assertEqual("0", final.attrib["failures"])
            self.assertIsNotNone(final.find("testcase[@name='fixture']"))

    def test_interrupted_first_suite_leaves_red_incomplete_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog.json"
            report_dir = root / "reports"
            catalog.write_text(json.dumps({"schemaVersion": 1, "suites": [{
                "id": "fixture", "kind": "infrastructure", "description": "fixture",
                "command": ["fixture"], "tiers": ["fast"],
            }]}), encoding="utf-8")
            argv = ["run.py", "fast", "--catalog", str(catalog),
                    "--report-dir", str(report_dir)]
            with mock.patch("sys.argv", argv), mock.patch.object(
                    run, "run_command", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    run.main()
            pending = ET.parse(report_dir / "TEST-android-fast.xml").getroot()
            self.assertEqual("1", pending.attrib["failures"])
            self.assertIsNotNone(
                pending.find("testcase[@name='suite-run-incomplete']/failure"))

    def test_intermediate_report_stays_red_until_two_suites_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog.json"
            report_dir = root / "reports"
            report = report_dir / "TEST-android-fast.xml"
            catalog.write_text(json.dumps({"schemaVersion": 1, "suites": [
                {"id": "first", "kind": "infrastructure", "description": "first",
                 "command": ["first"], "tiers": ["fast"]},
                {"id": "second", "kind": "infrastructure", "description": "second",
                 "command": ["second"], "tiers": ["fast"]},
            ]}), encoding="utf-8")
            calls = 0

            def execute(command, timeout, *, cwd, env):
                nonlocal calls
                pending = ET.parse(report).getroot()
                sentinel = pending.find("testcase[@name='suite-run-incomplete']/failure")
                self.assertIsNotNone(sentinel)
                self.assertEqual("1", pending.attrib["failures"])
                self.assertIn(f"{calls} of 2 suites completed", sentinel.text)
                if calls == 1:
                    self.assertIsNotNone(pending.find("testcase[@name='first']"))
                    self.assertEqual("2", pending.attrib["tests"])
                calls += 1
                return subprocess.CompletedProcess(command, 0, "ok\n")

            argv = ["run.py", "fast", "--catalog", str(catalog),
                    "--report-dir", str(report_dir)]
            with mock.patch("sys.argv", argv), mock.patch.object(
                    run, "run_command", side_effect=execute):
                self.assertEqual(0, run.main())
            self.assertEqual(2, calls)
            final = ET.parse(report).getroot()
            self.assertEqual("2", final.attrib["tests"])
            self.assertEqual("0", final.attrib["failures"])
            self.assertIsNone(final.find("testcase[@name='suite-run-incomplete']"))
            self.assertIsNotNone(final.find("testcase[@name='first']"))
            self.assertIsNotNone(final.find("testcase[@name='second']"))

    def test_interrupt_after_partial_success_leaves_progress_sentinel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog.json"
            report_dir = root / "reports"
            report = report_dir / "TEST-android-fast.xml"
            catalog.write_text(json.dumps({"schemaVersion": 1, "suites": [
                {"id": "first", "kind": "infrastructure", "description": "first",
                 "command": ["first"], "tiers": ["fast"]},
                {"id": "second", "kind": "infrastructure", "description": "second",
                 "command": ["second"], "tiers": ["fast"]},
            ]}), encoding="utf-8")
            calls = 0

            def execute(command, timeout, *, cwd, env):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise KeyboardInterrupt
                return subprocess.CompletedProcess(command, 0, "first passed\n")

            argv = ["run.py", "fast", "--catalog", str(catalog),
                    "--report-dir", str(report_dir)]
            with mock.patch("sys.argv", argv), mock.patch.object(
                    run, "run_command", side_effect=execute):
                with self.assertRaises(KeyboardInterrupt):
                    run.main()
            pending = ET.parse(report).getroot()
            self.assertEqual("2", pending.attrib["tests"])
            self.assertEqual("1", pending.attrib["failures"])
            self.assertIsNotNone(pending.find("testcase[@name='first']"))
            sentinel = pending.find("testcase[@name='suite-run-incomplete']/failure")
            self.assertIn("1 of 2 suites completed", sentinel.text)

    def test_empty_tier_replaces_stale_report_with_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog.json"
            report_dir = root / "reports"
            report_dir.mkdir()
            report = report_dir / "TEST-android-fast.xml"
            report.write_text('<testsuite tests="1" failures="0"/>', encoding="utf-8")
            catalog.write_text(json.dumps({"schemaVersion": 1, "suites": []}),
                               encoding="utf-8")
            argv = ["run.py", "fast", "--catalog", str(catalog),
                    "--report-dir", str(report_dir)]
            with mock.patch("sys.argv", argv):
                self.assertEqual(2, run.main())
            failed = ET.parse(report).getroot()
            self.assertEqual("1", failed.attrib["failures"])
            self.assertIsNotNone(failed.find("testcase[@name='empty-tier']/failure"))

    def test_list_is_read_only_even_with_existing_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog.json"
            report_dir = root / "reports"
            report_dir.mkdir()
            report = report_dir / "TEST-android-fast.xml"
            previous = b'<testsuite name="previous" tests="1" failures="0"/>'
            report.write_bytes(previous)
            catalog.write_text(json.dumps({"schemaVersion": 1, "suites": [{
                "id": "fixture", "kind": "infrastructure", "description": "fixture",
                "command": ["fixture"], "tiers": ["fast"],
            }]}), encoding="utf-8")
            argv = ["run.py", "fast", "--list", "--catalog", str(catalog),
                    "--report-dir", str(report_dir)]
            with mock.patch("sys.argv", argv):
                self.assertEqual(0, run.main())
            self.assertEqual(previous, report.read_bytes())
            self.assertFalse((report_dir / ".TEST-android-fast.xml.lock").exists())

    @unittest.skipUnless(os.name == "posix", "flock fixture is POSIX-specific")
    def test_report_lifecycle_lock_has_bounded_contention_and_persists_inode(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "TEST-android-fast.xml"
            lock_path = report.parent / f".{report.name}.lock"
            with run.report_lifecycle_lock(report, 1):
                started = time.monotonic()
                with self.assertRaisesRegex(TimeoutError, "after 0.05 seconds"):
                    with run.report_lifecycle_lock(report, 0.05):
                        self.fail("contending report writer acquired the lock")
                self.assertLess(time.monotonic() - started, 0.5)
            self.assertTrue(lock_path.is_file())
            with run.report_lifecycle_lock(report, 0):
                pass

    @unittest.skipUnless(os.name == "posix", "flock fixture is POSIX-specific")
    def test_main_lock_timeout_is_configurable_and_starts_no_suite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "catalog.json"
            report_dir = root / "reports"
            report = report_dir / "TEST-android-fast.xml"
            catalog.write_text(json.dumps({"schemaVersion": 1, "suites": [{
                "id": "fixture", "kind": "infrastructure", "description": "fixture",
                "command": ["fixture"], "tiers": ["fast"],
            }]}), encoding="utf-8")
            argv = ["run.py", "fast", "--catalog", str(catalog),
                    "--report-dir", str(report_dir)]
            with run.report_lifecycle_lock(report, 1):
                with mock.patch("sys.argv", argv), mock.patch.object(
                        run, "run_command") as execute, mock.patch.dict(
                            os.environ,
                            {"OVERTE_SUITE_REPORT_LOCK_TIMEOUT_SECONDS": "0.01"}):
                    self.assertEqual(2, run.main())
            execute.assert_not_called()

    def test_invalid_catalog_always_produces_a_junit_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "broken.json"
            report_dir = root / "reports"
            catalog.write_text("{not-json", encoding="utf-8")
            argv = ["run.py", "fast", "--catalog", str(catalog),
                    "--report-dir", str(report_dir)]
            with mock.patch("sys.argv", argv):
                self.assertEqual(2, run.main())
            report = report_dir / "TEST-android-fast.xml"
            suite = ET.parse(report).getroot()
        self.assertEqual("1", suite.attrib["tests"])
        self.assertEqual("1", suite.attrib["failures"])
        self.assertIsNotNone(suite.find("testcase[@name='catalog-validation']/failure"))


if __name__ == "__main__":
    unittest.main()
