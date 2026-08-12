#!/usr/bin/env python3

import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import tempfile
import subprocess
import sys
import time
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "macos" / "ci" / "runner-telemetry.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("macos_runner_telemetry", TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeCollector:
    def __init__(self, samples):
        self.samples = iter(samples)
        self.directory_requests = []

    def sample(self, include_directories=False):
        self.directory_requests.append(include_directories)
        metrics, directories = next(self.samples)
        return metrics, directories if include_directories else {}


class RunnerTelemetryTest(unittest.TestCase):
    def invoke_phase(self, root: Path, code: str, *, inactivity: float = 1.0,
                     extra: list[str] | None = None,
                     extra_env: dict[str, str] | None = None,
                     timeout: float = 6.0) -> tuple[subprocess.CompletedProcess[str], list[dict]]:
        log = root / "phase.jsonl"
        env = os.environ.copy()
        env.update(extra_env or {})
        completed = subprocess.run(
            [sys.executable, str(TOOL), "--log", str(log),
             "--phase", "test-phase", "--sample-interval", "0.05",
             "--publish-interval", "0.1", "--directory-interval", "0.05",
             "--inactivity-timeout", str(inactivity),
             "--monitor-failure-timeout", "0.3", "--term-grace", "0.1",
             *(extra or []), "--", sys.executable, "-c", code],
            capture_output=True, text=True, timeout=timeout, check=False, env=env,
        )
        records = [json.loads(line) for line in log.read_text().splitlines()]
        return completed, records

    def test_aggregates_five_second_samples_into_thirty_second_reports(self):
        module = load_tool()
        clock_values = iter([0, 0, 1, 5, 6, 10, 11, 15, 16, 20, 21, 25, 26, 30])
        collector = FakeCollector([
            ({"cpu_activity_pct": value, "ram_available_pct": 50,
              "disk_free_mib": 9000, "swap_used_pct": 0}, {})
            for value in (10, 20, 30, 40, 50, 60, 70)
        ])
        records = []
        module.run(collector, lambda event, **fields: records.append((event, fields)),
                   5, 30, 300, 4096, 10, 80, max_samples=7,
                   clock=lambda: next(clock_values), sleep=lambda _seconds: None)
        reports = [fields for event, fields in records if event == "report"]
        self.assertEqual(len(reports), 1)
        cpu = reports[0]["metrics"]["cpu_activity_pct"]
        self.assertEqual(cpu, {"current": 70.0, "min": 10.0, "max": 70.0, "avg": 40.0})
        self.assertEqual(reports[0]["samples"], 7)
        self.assertEqual(collector.directory_requests,
                         [True, False, False, False, False, False, False])

    def test_threshold_transitions_are_immediate_and_do_not_repeat(self):
        module = load_tool()
        samples = [
            ({"disk_free_mib": 3000, "ram_available_pct": 5, "swap_used_pct": 90}, {}),
            ({"disk_free_mib": 2000, "ram_available_pct": 4, "swap_used_pct": 91}, {}),
            ({"disk_free_mib": 8000, "ram_available_pct": 50, "swap_used_pct": 0}, {}),
        ]
        records = []
        ticks = iter(range(20))
        module.run(FakeCollector(samples), lambda event, **fields: records.append((event, fields)),
                   5, 30, 300, 4096, 10, 80, max_samples=3,
                   clock=lambda: next(ticks), sleep=lambda _seconds: None)
        thresholds = [fields for event, fields in records if event == "threshold"]
        self.assertEqual(len(thresholds), 6)
        self.assertEqual({row["state"] for row in thresholds}, {"active", "recovered"})

    def test_emitter_appends_flushes_and_contains_no_sensitive_context(self):
        module = load_tool()
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "telemetry.jsonl"
            log.write_text('{"existing":true}\n')
            log.chmod(0o666)
            stream = io.StringIO()
            emitter = module.Emitter(log, stream)
            os.environ["SIGNING_TOKEN"] = "do-not-leak"
            try:
                emitter("report", metrics={"cpu_activity_pct": {"current": 12}})
            finally:
                os.environ.pop("SIGNING_TOKEN", None)
            lines = log.read_text().splitlines()
            self.assertEqual(json.loads(lines[0]), {"existing": True})
            self.assertEqual(json.loads(lines[1])["macos_runner_telemetry"], "report")
            self.assertEqual(stream.getvalue(), lines[1] + "\n")
            self.assertNotIn("do-not-leak", log.read_text())
            self.assertNotIn(str(ROOT), log.read_text())
            self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_directory_labels_are_bounded_and_paths_are_never_reported(self):
        module = load_tool()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "payload").write_bytes(b"x" * 1024)
            collector = module.Collector(root, {"build-cache": root})
            with mock.patch.object(module, "_command", return_value=""):
                metrics, sizes = collector.sample(include_directories=True)
            self.assertIn("build-cache", sizes)
            serialized = json.dumps({"metrics": metrics, "directory_mib": sizes})
            self.assertNotIn(str(root), serialized)
            self.assertTrue(module.SAFE_LABEL.fullmatch("build-cache"))
            self.assertFalse(module.SAFE_LABEL.fullmatch("secret/path"))

    def test_memory_parsers_are_hermetic(self):
        module = load_tool()
        outputs = {
            ("sysctl", "-n", "hw.pagesize"): "4096\n",
            ("sysctl", "-n", "hw.memsize"): "1073741824\n",
            ("vm_stat",): "Pages free: 1000.\nPages inactive: 2000.\nPages speculative: 100.\n",
            ("sysctl", "-n", "vm.swapusage"): "total = 1024.00M used = 256.00M free = 768.00M\n",
            ("memory_pressure", "-Q"): "System-wide memory free percentage: 42%\n",
        }
        with mock.patch.object(module, "_command", side_effect=lambda command: outputs[tuple(command)]):
            result = module._mac_memory()
        self.assertEqual(result["swap_used_pct"], 25)
        self.assertEqual(result["memory_free_pct"], 42)
        self.assertGreater(result["ram_available_mib"], 0)

    def test_supervisor_preserves_child_exit_code_and_never_logs_command(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "runner.jsonl"
            secret = "never-print-this-command-secret"
            result = subprocess.run(
                [sys.executable, str(TOOL), "--log", str(log),
                 "--sample-interval", "0.01", "--publish-interval", "0.02",
                 "--directory-interval", "0.03", "--",
                 sys.executable, "-c", "import sys;sys.exit(37)", secret],
                capture_output=True, text=True, timeout=5, check=False,
            )
            self.assertEqual(result.returncode, 37, result.stdout + result.stderr)
            combined = result.stdout + result.stderr + log.read_text()
            self.assertNotIn(secret, combined)
            self.assertNotIn("sys.exit", combined)

    def test_phase_supervisor_preserves_signalled_child_status(self):
        with tempfile.TemporaryDirectory() as directory:
            result, records = self.invoke_phase(
                Path(directory),
                "import os,signal; os.kill(os.getpid(), signal.SIGTERM)",
            )
            self.assertEqual(result.returncode, 128 + signal.SIGTERM,
                             result.stdout + result.stderr)
            self.assertEqual(records[-1]["exit_code"], 128 + signal.SIGTERM)

    def test_launch_failure_is_127_and_does_not_log_command(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "phase.jsonl"
            secret = "missing-secret-executable"
            result = subprocess.run(
                [sys.executable, str(TOOL), "--log", str(log),
                 "--phase", "launch", "--", str(root / secret)],
                capture_output=True, text=True, timeout=3, check=False,
            )
            self.assertEqual(result.returncode, 127, result.stdout + result.stderr)
            combined = result.stdout + result.stderr + log.read_text()
            self.assertNotIn(secret, combined)
            records = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(records[-1]["reason"], "launch_failure")

    def test_active_cpu_prevents_false_inactivity_abort_and_heartbeats(self):
        with tempfile.TemporaryDirectory() as directory:
            result, records = self.invoke_phase(
                Path(directory),
                "import time; end=time.monotonic()+0.55\nwhile time.monotonic()<end: pass",
                inactivity=0.15,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            heartbeats = [row for row in records
                          if row["macos_runner_telemetry"] == "heartbeat"]
            self.assertTrue(heartbeats)
            self.assertTrue(any("cpu" in row["progress_sources"] for row in heartbeats))
            self.assertTrue(any(
                row["metrics"].get("phase_cpu_activity_pct", {}).get("max", 0) > 0
                for row in heartbeats
            ))

    def test_live_output_prevents_false_inactivity_abort(self):
        with tempfile.TemporaryDirectory() as directory:
            result, records = self.invoke_phase(
                Path(directory),
                # Keep the producer alive across several report intervals.
                # A six-by-70ms window was too narrow on loaded macOS hosts:
                # the reader thread could observe the data only after the last
                # heartbeat even though supervision itself remained healthy.
                "import time\nfor _ in range(12): print('working', flush=True); time.sleep(.1)",
                inactivity=0.25,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            heartbeats = [row for row in records
                          if row["macos_runner_telemetry"] == "heartbeat"]
            self.assertTrue(any("output" in row["progress_sources"] for row in heartbeats))
            self.assertIn("working", result.stdout)

    def test_active_phase_hits_controlled_wall_limit_before_outer_ci_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diagnostics = root / "diagnostics"
            # Keep the wall-limit test hermetic on macOS.  The system `sample`
            # command intentionally records for several seconds per process,
            # which is useful in production but would exceed this test's
            # six-second outer guard before the supervisor can terminate the
            # synthetic active child.
            fake_bin = root / "bin"
            fake_bin.mkdir()
            sample = fake_bin / "sample"
            sample.write_text("#!/bin/sh\nprintf 'bounded test sample\\n'\n")
            sample.chmod(0o755)
            result, records = self.invoke_phase(
                root,
                "import time; end=time.monotonic()+5\nwhile time.monotonic()<end: pass",
                inactivity=2,
                extra=["--max-runtime", "0.25", "--diagnostics-dir", str(diagnostics)],
                extra_env={
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                },
            )
            self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
            self.assertTrue(any(row["macos_runner_telemetry"] == "timed_out"
                                for row in records))
            self.assertEqual(records[-1]["reason"], "wall_timeout")
            self.assertTrue(list(diagnostics.glob("stall-*.json")))

    def test_wall_limit_remains_a_timeout_if_child_exits_during_diagnostics(self):
        module = load_tool()

        class SlowDiagnosticsCollector:
            def sample(self, include_directories=False):
                return ({"disk_free_mib": 9000, "ram_available_pct": 50,
                         "swap_used_pct": 0}, {})

        records = []
        with mock.patch.object(module, "_collect_phase_diagnostics",
                               side_effect=lambda *_args: time.sleep(0.2)):
            result = module.supervise(
                [sys.executable, "-c", "import time; time.sleep(.15)"],
                SlowDiagnosticsCollector(),
                lambda event, **fields: records.append((event, fields)),
                "timeout-race", 0.01, 0.02, 1.0, 2.0, 1.0, 0.05,
                4096, 10, 80, None, max_runtime=0.05,
            )
        self.assertEqual(result, 124)
        self.assertEqual(records[-1][1]["reason"], "wall_timeout")

    def test_watched_filesystem_growth_prevents_false_inactivity_abort(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            watched = root / "watched"
            watched.mkdir()
            log = root / "phase.jsonl"
            code = (
                "import pathlib,sys,time\nroot=pathlib.Path(sys.argv[1])\n"
                "for i in range(12):\n"
                "    (root / f'part-{i}').write_bytes(b'x'*8192)\n"
                "    time.sleep(.1)\n"
            )
            result = subprocess.run(
                [sys.executable, str(TOOL), "--log", str(log),
                 "--phase", "filesystem", "--sample-interval", "0.05",
                 "--publish-interval", "0.1", "--directory-interval", "0.05",
                 "--inactivity-timeout", "0.25", "--monitor-failure-timeout", "0.5",
                 "--term-grace", "0.1", "--watch", f"payload={watched}", "--",
                 sys.executable, "-c", code, str(watched)],
                capture_output=True, text=True, timeout=6, check=False,
            )
            records = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            heartbeats = [row for row in records
                          if row["macos_runner_telemetry"] == "heartbeat"]
            self.assertTrue(any("filesystem" in row["progress_sources"]
                                for row in heartbeats))
            self.assertNotIn(str(watched), log.read_text())

    def test_inactive_phase_is_killed_after_private_sanitized_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diagnostics = root / "diagnostics"
            fake_bin = root / "bin"
            fake_bin.mkdir()
            sample = fake_bin / "sample"
            sample.write_text(
                "#!/bin/sh\nprintf 'Path: /Users/runner/private token=leaked-value "
                "super-private-password\\n'\n"
            )
            sample.chmod(0o755)
            result, records = self.invoke_phase(
                root,
                "import time; time.sleep(5)",
                inactivity=0.15,
                extra=["--diagnostics-dir", str(diagnostics)],
                extra_env={
                    "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                    "API_TOKEN": "leaked-value",
                    "SIGNING_PASSWORD": "super-private-password",
                },
            )
            self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
            self.assertTrue(any(row["macos_runner_telemetry"] == "stalled"
                                for row in records))
            self.assertEqual(records[-1]["reason"], "inactivity")
            process_images = list(diagnostics.glob("stall-*.json"))
            samples = list(diagnostics.glob("sample-*.txt"))
            self.assertEqual(len(process_images), 1)
            self.assertTrue(samples)
            diagnostic_text = "".join(path.read_text() for path in [*process_images, *samples])
            self.assertNotIn("command", process_images[0].read_text())
            self.assertNotIn("/Users/runner", diagnostic_text)
            self.assertNotIn("leaked-value", diagnostic_text)
            self.assertNotIn("super-private-password", diagnostic_text)
            self.assertTrue(all(path.stat().st_mode & 0o777 == 0o600
                                for path in [*process_images, *samples]))

    def test_monitor_failure_uses_distinct_exit_without_false_stall(self):
        module = load_tool()

        class StaticCollector:
            def sample(self, include_directories=False):
                return ({"disk_free_mib": 9000, "ram_available_pct": 50,
                         "swap_used_pct": 0}, {})

        records = []
        with mock.patch.object(module, "_process_snapshot", side_effect=OSError):
            result = module.supervise(
                [sys.executable, "-c", "import time; time.sleep(2)"],
                StaticCollector(),
                lambda event, **fields: records.append((event, fields)),
                "monitor-test", 0.02, 0.05, 1.0, 0.1, 0.12, 0.05,
                4096, 10, 80, None,
            )
        self.assertEqual(result, 125)
        events = [event for event, _fields in records]
        self.assertIn("monitor_error", events)
        self.assertIn("monitor_failed", events)
        self.assertNotIn("stalled", events)
        self.assertEqual(records[-1][1]["reason"], "monitor_failure")

    def test_compiler_watchdog_channel_is_private_append_only_and_live(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            live_log = root / "compiler.jsonl"
            diagnostics = root / "compiler-diagnostics"
            live_log.write_text("existing-checkpoint\n")
            live_log.chmod(0o666)
            marker = "compiler-live-bypass-marker"
            code = (
                "import os,pathlib,time; "
                "live=pathlib.Path(os.environ['OVERTE_COMPILER_WATCHDOG_LOG']); "
                "diag=pathlib.Path(os.environ['OVERTE_COMPILER_WATCHDOG_DIAGNOSTICS']); "
                "assert diag.exists(); "
                f"open(live,'a',buffering=1).write('{marker}\\n'); "
                "time.sleep(.2)"
            )
            result, records = self.invoke_phase(
                root,
                code,
                inactivity=1,
                extra=["--compiler-live-log", str(live_log),
                       "--compiler-diagnostics-dir", str(diagnostics)],
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(marker, result.stdout)
            self.assertEqual(live_log.read_text().splitlines(),
                             ["existing-checkpoint", marker])
            self.assertEqual(live_log.stat().st_mode & 0o777, 0o600)
            self.assertEqual(diagnostics.stat().st_mode & 0o777, 0o700)
            serialized = "\n".join(json.dumps(row) for row in records)
            self.assertNotIn(str(live_log), serialized)
            self.assertNotIn(str(diagnostics), serialized)

    def test_compiler_live_tail_failure_does_not_start_unobservable_phase(self):
        module = load_tool()

        class StaticCollector:
            def sample(self, include_directories=False):
                return ({}, {})

        records = []
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            module.subprocess, "Popen", side_effect=OSError
        ) as popen:
            result = module.supervise(
                [sys.executable, "-c", "raise SystemExit(99)"], StaticCollector(),
                lambda event, **fields: records.append((event, fields)),
                "tail-test", 5, 30, 300, 900, 120, 10, 4096, 10, 80,
                None, Path(directory) / "compiler.jsonl", None,
            )
        self.assertEqual(result, 125)
        self.assertEqual(popen.call_count, 1)
        self.assertEqual(records[-1][1]["reason"], "live_tail_failure")

    @unittest.skipUnless(hasattr(os, "killpg"), "requires POSIX process groups")
    def test_forwarded_term_kills_complete_ignoring_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            leader_file = root / "leader.pid"
            child_file = root / "child.pid"
            log = root / "phase.jsonl"
            code = (
                "import os,pathlib,signal,subprocess,sys,time; "
                "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); "
                "subprocess.Popen([sys.executable,'-c',"
                "'import os,pathlib,signal,sys,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                "pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(30)',"
                "sys.argv[2]]); time.sleep(30)"
            )
            process = subprocess.Popen(
                [sys.executable, str(TOOL), "--log", str(log), "--phase", "signals",
                 "--sample-interval", "0.05", "--publish-interval", "0.1",
                 "--directory-interval", "0.1", "--inactivity-timeout", "10",
                 "--monitor-failure-timeout", "1", "--term-grace", "0.1", "--",
                 sys.executable, "-c", code, str(leader_file), str(child_file)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            leader_pid = self._wait_for_pid(leader_file)
            child_pid = self._wait_for_pid(child_file)
            try:
                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=4)
                self.assertEqual(process.returncode, 128 + signal.SIGTERM,
                                 stdout + stderr)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=2)
            self._assert_process_gone(leader_pid)
            self._assert_process_gone(child_pid)

    def _wait_for_pid(self, path: Path) -> int:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                value = path.read_text().strip()
                if value.isdigit():
                    return int(value)
            except FileNotFoundError:
                pass
            time.sleep(0.02)
        self.fail(f"PID file was not populated: {path.name}")

    def _assert_process_gone(self, pid: int) -> None:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            state = subprocess.run(
                ["ps", "-o", "stat=", "-p", str(pid)], capture_output=True,
                text=True, check=False,
            ).stdout.strip()
            if not state or state.startswith("Z"):
                return
            time.sleep(0.02)
        self.fail(f"process {pid} survived signal escalation")


if __name__ == "__main__":
    unittest.main()
